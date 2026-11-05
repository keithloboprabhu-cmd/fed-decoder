"""Evaluate Ask against evals/ask_suite.yaml and write evals/ask_report.md.

    make eval-ask                                  # current agent
    python evals/ask_eval.py --label before --agent-root /path/to/old/checkout --no-report

Current facts are checked against ground truth computed at eval time from the same live tools
(fed_leadership, fomc_calendar, get_meeting, bls_latest, fred_series, treasury_yields); nothing is
hard-coded. Rubric items are scored by an LLM judge from a different provider than the one that
answered. Each question is scored on correctness, grounding, citations, length (<= 120 words) and
latency. Pass bar: 100% on current leadership and the current rate, >= 90% overall, median
latency under 6 s.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--agent-root", help="import the agent from another checkout (for a before/after comparison)")
ap.add_argument("--label", default="after")
ap.add_argument("--only", help="comma-separated question ids")
ap.add_argument("--no-report", action="store_true")
ap.add_argument("--pause", type=float, default=3.0, help="seconds between questions (free-tier rate limits)")
ap.add_argument("--rejudge", help="re-score the judged items of a saved run (no new answers) and rewrite the report")
ARGS = ap.parse_args()

AGENT_ROOT = Path(ARGS.agent_root).resolve() if ARGS.agent_root else ROOT
sys.path.insert(0, str(AGENT_ROOT))
if AGENT_ROOT != ROOT:
    sys.path.insert(1, str(ROOT))

import yaml  # noqa: E402

from fed_decoder.chat import agent  # noqa: E402  (the agent under test)

# Ground truth always comes from the current tools, whichever agent is being tested.
sys.path.insert(0, str(ROOT))
import importlib  # noqa: E402

_live = importlib.import_module("fed_decoder.chat.live") if AGENT_ROOT == ROOT else None
if _live is None:  # old checkout has no live module: load ours by path
    import importlib.util

    spec = importlib.util.spec_from_file_location("current_live", ROOT / "fed_decoder" / "chat" / "live.py")
    _live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_live)  # type: ignore[union-attr]
from fed_decoder.chat import tools as _tools  # noqa: E402
from fed_decoder.llm.router import generate  # noqa: E402

SUITE = ROOT / "evals" / "ask_suite.yaml"
RUNS = ROOT / "evals" / "runs"
REPORT = ROOT / "evals" / "ask_report.md"
CITE_EXEMPT = {"scope"}


# ---------------------------------------------------------------- dynamic ground truth
def _last(name: str) -> str:
    return name.replace(",", "").split()[-1]


def _lead() -> dict:
    r = _live.fed_leadership()
    if "error" in r:
        raise RuntimeError(r["error"])
    return r


def _board_title(title: str) -> list[list[str]]:
    m = next(x for x in _lead()["board_of_governors"] if x["title"] == title)
    return [[_last(m["name"])]]


def _date_forms(iso: str) -> list[str]:
    d = date.fromisoformat(iso)
    return [f"{d:%B} {d.day}", f"{d:%b} {d.day}", f"{d:%b}. {d.day}", iso, f"{d.month}/{d.day}", f"{d:%B} {d.day - 1}-{d.day}",
            f"{d:%B} {d.day - 1}–{d.day}", f"{d:%B} {d.day - 1} to {d.day}"]


def _meeting(d: str) -> dict:
    """Archive facts for a date ('latest' resolved here so older checkouts work too)."""
    if d == "latest":
        from fed_decoder.data import store

        d = str(store.statements()["meeting_date"].max().date())
    return _tools.get_meeting(d)


def _num(x: float) -> list[float]:
    return [round(float(x), 2)]


TRUTH = {
    "chair": lambda: {"groups": [[_last(_lead()["chair"])]], "min": 1},
    "vice_chair": lambda: {"groups": _board_title("Vice Chair"), "min": 1},
    "vice_chair_supervision": lambda: {"groups": _board_title("Vice Chair for Supervision"), "min": 1},
    "governors": lambda: {"groups": [[_last(m["name"])] for m in _lead()["board_of_governors"]], "min": 6},
    "voters": lambda: {"groups": [[_last(m["name"])] for m in _lead()["fomc_voters_this_year"]], "min": 11},
    "bank_voters": lambda: {"groups": [[_last(m["name"])] for m in _lead()["fomc_voters_this_year"] if m["affiliation"] != "Board of Governors"], "min": 4},
    "target_range": lambda: (lambda m: {"numbers": [_num(m["target_range_percent"][0]), _num(m["target_range_percent"][1])]})(_meeting("latest")),
    "cpi_yoy": lambda: {"numbers": [sorted({v for v in (_live.bls_latest("cpi").get("yoy_pct"), _live.fred_series("CPIAUCSL").get("yoy_pct")) if v is not None})]},
    "unemployment": lambda: {"numbers": [sorted({v for v in (_live.bls_latest("unemployment").get("latest", {}).get("value"),
                                                             _live.fred_series("UNRATE").get("latest", {}).get("value")) if v is not None})]},
    "next_meeting": lambda: {"groups": [_date_forms(_live.fomc_calendar()["upcoming"][0]["date"])], "min": 1},
    "next_sep": lambda: {"groups": [_date_forms(next(m["date"] for m in _live.fomc_calendar()["upcoming"] if m["sep"]))], "min": 1},
    "ten_year": lambda: {"numbers": [sorted({v for v in (_live.treasury_yields().get("yields_pct", {}).get("10-year"),
                                                         _live.fred_series("DGS10").get("latest", {}).get("value")) if v is not None})]},
}


def numbers_in(text: str) -> list[float]:
    t = text.replace("¼", ".25").replace("½", ".5").replace("¾", ".75")
    t = re.sub(r"(\d)\s*-\s*1/4", r"\1.25", t)
    t = re.sub(r"(\d)\s*-\s*1/2", r"\1.5", t)
    t = re.sub(r"(\d)\s*-\s*3/4", r"\1.75", t)
    return [float(x) for x in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d])", t.replace(",", ""))]


def check_truth(text: str, truth: dict) -> tuple[bool, str]:
    low = text.lower()
    if "numbers" in truth:
        nums = numbers_in(text)
        miss = [alts for alts in truth["numbers"] if not any(abs(n - a) < 0.051 for n in nums for a in alts)]
        return (not miss and bool(truth["numbers"])), (f"missing {miss}" if miss else "ok")
    hit = [g for g in truth["groups"] if any(x.lower() in low for x in g)]
    ok = len(hit) >= truth["min"]
    return ok, "ok" if ok else f"matched {len(hit)}/{truth['min']} of {[g[0] for g in truth['groups']]}"


DIRECTION = {"cut": ("cut", "lower", "reduc", "eas"), "hike": ("rais", "hike", "increas", "lift"),
             "hold": ("held", "hold", "maintain", "unchanged", "steady", "kept", "paus")}


def check_corpus(text: str, item: dict) -> tuple[bool, str]:
    m = _meeting(item["date"])
    lo, hi = m["target_range_percent"]
    nums = numbers_in(text)
    probs = []
    if item.get("only_dissenters"):
        lo = hi = 0.0  # a follow-up that only asks who dissented
    for v in {lo, hi} - {0.0}:
        if not any(abs(n - v) < 0.051 for n in nums):
            probs.append(f"range {lo}-{hi} not stated")
            break
    if not item.get("no_direction") and not item.get("only_dissenters") and not any(w in text.lower() for w in DIRECTION[m["decision"]]):
        probs.append(f"direction '{m['decision']}' not stated")
    if item.get("dissenters"):
        names = [_last(n) for n in m["dissenters"]]
        missing = [n for n in names if n.lower() not in text.lower()]
        if missing:
            probs.append(f"dissenters missing {missing}")
    return not probs, "; ".join(probs) or "ok"


# ---------------------------------------------------------------- judge
JUDGE = """You are grading an answer from a Federal Reserve explainer. Today is {today}.
The answer was written from live official sources, so current names, roles, dates and figures in it
may be newer than your training data (for example, the Fed chair changed in 2026). Do NOT mark
anything wrong because it differs from your memory. Grade ONLY the listed points.
Question: {q}
Answer: {a}
The answer passes only if ALL of these hold:
{points}
Reply with JSON only: {{"pass": true or false, "failed": ["<points that fail>"]}}"""


def judge(q: str, a: str, points: list[str], answered_by: str) -> tuple[bool | None, str, str]:
    order = ["groq", "gemini"] if answered_by == "gemini" else ["gemini", "groq"]
    msg = [{"role": "user", "content": JUDGE.format(today=date.today().isoformat(), q=q, a=a[:2500],
                                                    points="\n".join(f"- {p}" for p in points))}]
    for prov in order:
        r = generate(msg, providers=[prov], purpose="judge", temperature=0.0)
        if r is None:
            continue
        m = re.search(r"\{.*\}", r.text or "", re.S)
        try:
            v = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            v = None
        if isinstance(v, dict) and "pass" in v:
            same = " (same-provider judge: other provider unavailable)" if prov == answered_by else ""
            return bool(v["pass"]), "; ".join(v.get("failed") or []) + same, prov
    return None, "judge unavailable", ""


# ---------------------------------------------------------------- run
def words(text: str) -> int:
    return len(re.findall(r"\b[\w'’.%$-]+\b", re.sub(r"\]\([^)]*\)", "]", text or "")))


def run_item(cat: str, item: dict) -> dict:
    turns = item.get("turns") or [item["q"]]
    history: list[dict] = []
    t_total = 0.0
    a = None
    for t in turns:
        t0 = time.time()
        try:
            a = agent.answer(t, history=history, use_cache=False)
        except TypeError:  # older agent signature
            a = agent.answer(t, history=history)
        t_total = time.time() - t0  # latency of the scored (last) turn
        history += [{"role": "user", "content": t}, {"role": "assistant", "content": a.text}]
    q = turns[-1]
    text = a.text + ("\n" + a.saved if getattr(a, "saved", "") else "")
    status = getattr(a, "status", None) or ("declined" if a.provider == "guard" else "ok")
    sources = getattr(a, "sources", []) or []
    res = {"id": item["id"], "category": cat, "question": " → ".join(turns), "provider": a.provider, "model": getattr(a, "model", ""),
           "status": status, "text": a.text, "saved": getattr(a, "saved", ""), "sources": [s["url"] for s in sources],
           "tools": [c["name"] for c in a.tool_calls], "latency_s": round(t_total, 2), "words": words(a.text), "key": item.get("key")}
    chk = item["check"]
    answered = status == "ok" and a.provider not in ("none",)
    judged_by = ""
    if chk in ("live", "referent"):
        ok, why = check_truth(a.text, TRUTH[item["fn"]]()) if answered else (False, f"no answer ({status})")
    elif chk == "corpus":
        ok, why = check_corpus(a.text, item) if answered else (False, f"no answer ({status})")
    elif chk == "decline":
        if status == "declined" or a.provider == "guard":
            ok, why = True, "declined by scope check"
        elif answered:
            ok, why, judged_by = judge(q, a.text, ["politely declines (no investment advice / off-topic)", "suggests or offers a related on-topic question or explanation"], a.provider)
        else:
            ok, why = False, f"no answer ({status})"
    else:  # rubric, adversarial
        bad = [s for s in item.get("must_not", []) if s.lower() in a.text.lower()]
        if bad:
            ok, why = False, f"contains forbidden text {bad}"
        elif not answered:
            ok, why = False, f"no answer ({status})"
        else:
            ok, why, judged_by = judge(q, a.text, item["points"], a.provider)
    res["correct"] = ok
    res["why"] = why
    res["judge"] = judged_by
    res["grounded"] = status in ("ok", "declined") and a.provider != "none"
    res["cited"] = cat in CITE_EXEMPT or bool(sources)
    res["concise"] = res["words"] <= 120
    res["pass"] = bool(ok) and res["grounded"] and res["cited"] and res["concise"]
    return res


def rejudge(path: Path) -> int:
    """Re-run only the LLM judge on a saved run's rubric, adversarial and decline items."""
    run = json.loads(path.read_text())
    suite = {it["id"]: it for its in yaml.safe_load(SUITE.read_text()).values() for it in its}
    for r in run["results"]:
        it = suite.get(r["id"])
        if it and it["check"] == "corpus" and r.get("status") == "ok" and r.get("provider") != "none":
            ok, why = check_corpus(r["text"], it)  # archive checks are code: re-run with the current suite
            r["correct"], r["why"] = ok, why
            r["pass"] = bool(ok) and r["grounded"] and r["cited"] and r["concise"]
            continue
        if not it or it["check"] not in ("rubric", "adversarial", "decline") or r.get("status") != "ok" or r.get("provider") in ("guard", "none"):
            continue
        q = (it.get("turns") or [it.get("q")])[-1]
        bad = [x for x in it.get("must_not", []) if x.lower() in r["text"].lower()]
        if bad:
            ok, why, by = False, f"contains forbidden text {bad}", ""
        else:
            pts = it.get("points") or ["politely declines (no investment advice / off-topic)", "suggests or offers a related on-topic question or explanation"]
            ok, why, by = judge(q, r["text"], pts, r["provider"])
        r["correct"], r["why"], r["judge"] = ok, why, by
        r["pass"] = bool(ok) and r["grounded"] and r["cited"] and r["concise"]
        print(r["id"], "PASS" if r["pass"] else "fail", why[:90], flush=True)
    run["summary"] = summarize(run["results"])
    run["rejudged"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    path.write_text(json.dumps(run, indent=1, ensure_ascii=False))
    if run.get("label") == "after":
        write_report(path)
    return 0


def main() -> int:
    if ARGS.rejudge:
        return rejudge(Path(ARGS.rejudge))
    suite = yaml.safe_load(SUITE.read_text())
    only = set(ARGS.only.split(",")) if ARGS.only else None
    items = [(cat, it) for cat, its in suite.items() for it in its if not only or it["id"] in only]
    results = []
    for i, (cat, it) in enumerate(items):
        try:
            r = run_item(cat, it)
        except Exception as e:  # noqa: BLE001
            r = {"id": it["id"], "category": cat, "question": it.get("q") or " → ".join(it["turns"]), "correct": False, "pass": False,
                 "why": f"eval error {type(e).__name__}: {e}", "latency_s": None, "words": 0, "grounded": False, "cited": False,
                 "concise": False, "status": "error", "provider": "", "key": it.get("key"), "text": ""}
        results.append(r)
        print(f"[{i + 1}/{len(items)}] {r['id']} {'PASS' if r['pass'] else 'fail'} {r.get('provider', '')}/{r.get('model', '')} "
              f"{r.get('latency_s')}s {r.get('words')}w :: {r['why'][:90]}", flush=True)
        time.sleep(ARGS.pause)
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M")
    out = RUNS / f"ask_{ARGS.label}_{stamp}.json"
    summary = summarize(results)
    out.write_text(json.dumps({"label": ARGS.label, "run_at": stamp, "agent_root": str(AGENT_ROOT), "summary": summary, "results": results},
                              indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))
    print("saved", out)
    if not ARGS.no_report:
        write_report(out)
    return 0 if summary["meets_bar"] else 1


def summarize(results: list[dict]) -> dict:
    n = len(results)
    lat = [r["latency_s"] for r in results if r.get("latency_s") is not None and r.get("status") not in ("declined",)]
    cats = {}
    for r in results:
        c = cats.setdefault(r["category"], {"n": 0, "pass": 0, "correct": 0})
        c["n"] += 1
        c["pass"] += bool(r["pass"])
        c["correct"] += bool(r["correct"])
    lead = [r for r in results if r.get("key") == "leadership"]
    rate = [r for r in results if r.get("key") == "rate"]
    s = {
        "n": n,
        "pass_rate": round(sum(bool(r["pass"]) for r in results) / n, 3) if n else 0,
        "correct_rate": round(sum(bool(r["correct"]) for r in results) / n, 3) if n else 0,
        "grounded_rate": round(sum(bool(r["grounded"]) for r in results) / n, 3) if n else 0,
        "cited_rate": round(sum(bool(r["cited"]) for r in results) / n, 3) if n else 0,
        "concise_rate": round(sum(bool(r["concise"]) for r in results) / n, 3) if n else 0,
        "leadership_correct": f"{sum(bool(r['correct']) for r in lead)}/{len(lead)}",
        "rate_correct": f"{sum(bool(r['correct']) for r in rate)}/{len(rate)}",
        "median_latency_s": round(statistics.median(lat), 1) if lat else None,
        "p90_latency_s": round(sorted(lat)[int(len(lat) * 0.9) - 1], 1) if len(lat) >= 10 else None,
        "unavailable": sum(r.get("status") == "unavailable" for r in results),
        "silent_fallback": sum(r.get("provider") == "rules" for r in results),
        "providers": {p: sum(r.get("provider") == p for r in results) for p in sorted({r.get("provider", "") for r in results})},
        "by_category": cats,
    }
    s["meets_bar"] = (all(r["correct"] for r in lead + rate) and s["pass_rate"] >= 0.9
                      and s["median_latency_s"] is not None and s["median_latency_s"] < 6)
    return s


def write_report(after_path: Path) -> None:
    after = json.loads(after_path.read_text())
    befores = sorted(RUNS.glob("ask_before_*.json"))
    before = json.loads(befores[-1].read_text()) if befores else None
    a, b = summarize(after["results"]), (summarize(before["results"]) if before else None)

    def row(label, key, fmt=lambda v: f"{v * 100:.0f}%"):
        bv = fmt(b[key]) if b and b.get(key) is not None else "—"
        av = fmt(a[key]) if a.get(key) is not None else "—"
        return f"| {label} | {bv} | {av} |"

    lines = [
        "# Ask evaluation",
        "",
        f"Suite: `evals/ask_suite.yaml` ({a['n']} questions). Run {after['run_at']} UTC with `make eval-ask`. "
        "Current facts are checked against ground truth fetched at eval time from the same live tools; rubric items are graded by an "
        "LLM judge from the other provider. \"Before\" is the previous agent (commit 8f59111) on the same suite and the same day.",
        "",
        "| | Before | After |",
        "|---|---|---|",
        row("Pass (correct, grounded, cited, ≤120 words)", "pass_rate"),
        row("Correct", "correct_rate"),
        row("Grounded (passed the number check, or a scope refusal)", "grounded_rate"),
        row("Sources shown", "cited_rate"),
        row("≤ 120 words", "concise_rate"),
        f"| Current leadership correct | {b['leadership_correct'] if b else '—'} | {a['leadership_correct']} |",
        f"| Current rate correct | {b['rate_correct'] if b else '—'} | {a['rate_correct']} |",
        f"| Median latency | {str(b['median_latency_s']) + ' s' if b else '—'} | {a['median_latency_s']} s |",
        f"| Silent fallbacks (canned text shown as if it were an answer) | {b.get('silent_fallback', '—') if b else '—'} | {a.get('silent_fallback', 0)} |",
        f"| Honest \"AI unavailable\" notices | {b['unavailable'] if b else '—'} | {a['unavailable']} |",
        "",
        f"**Bar:** 100% on current leadership and rate, ≥ 90% overall, median latency under 6 s. "
        f"**{'Met' if a['meets_bar'] else 'Not met'}.**",
        "",
        "## By category (after)",
        "",
        "| Category | Pass | Correct |",
        "|---|---|---|",
    ]
    for c, v in a["by_category"].items():
        lines.append(f"| {c} | {v['pass']}/{v['n']} | {v['correct']}/{v['n']} |")
    lines += ["", f"Answered by: {', '.join(f'{k or 'none'} {v}' for k, v in a['providers'].items())}.", "",
              "## Every question (after)", "", "| id | Result | Provider | Latency | Words | Why |", "|---|---|---|---|---|---|"]
    for r in after["results"]:
        flags = []
        if not r["correct"]:
            flags.append("wrong")
        if not r["grounded"]:
            flags.append("ungrounded")
        if not r["cited"]:
            flags.append("no source")
        if not r["concise"]:
            flags.append(f">{120}w")
        res = "pass" if r["pass"] else "FAIL: " + ", ".join(flags)
        lines.append(f"| {r['id']} | {res} | {r.get('model') or r.get('provider') or '—'} | {r.get('latency_s')} s | {r.get('words')} | "
                     f"{str(r.get('why', '')).replace('|', '/')[:120]} |")
    REPORT.write_text("\n".join(lines) + "\n")
    print("wrote", REPORT)


if __name__ == "__main__":
    raise SystemExit(main())
