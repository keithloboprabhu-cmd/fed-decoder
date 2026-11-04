"""Fed Decoder evals. One command:

    python evals/run.py                 # everything that can run with the keys you have
    python evals/run.py --n-llm 20      # size of LLM-call subsets (consistency, judge, comparison)
    python evals/run.py --offline       # no API calls at all

Writes evals/report.md (and evals/results.json). LLM outputs are cached in
evals/runs/ so a rerun does not spend free-tier quota twice. All calls go
through the provider rate limiters, so this stays inside per-minute caps.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from fed_decoder import config
from fed_decoder.analysis import forecast as forecast_mod
from fed_decoder.analysis import impact
from fed_decoder.analysis import tone as tone_mod
from fed_decoder.cards.builder import build_llm_card, validate_card
from fed_decoder.cards.context import build_context, render_context
from fed_decoder.cards.rules import extract_decision
from fed_decoder.cards.store import all_cards
from fed_decoder.chat import agent
from fed_decoder.data import store
from fed_decoder.llm import guardrail, router

EVAL_DIR = ROOT / "evals"
RUNS = EVAL_DIR / "runs"
SEED = 7


# ---------------------------------------------------------------- helpers
def have(provider: str) -> bool:
    return router.get_provider(provider).available()


def cached_run(key: str, fn):
    """Cache any LLM-dependent result under evals/runs/<key>.json."""
    RUNS.mkdir(parents=True, exist_ok=True)
    p = RUNS / f"{key}.json"
    if p.exists():
        return json.loads(p.read_text())
    out = fn()
    if out is not None:
        p.write_text(json.dumps(out, default=str, indent=1))
    return out


def card_for(date, provider: str | None, include_diff: bool = True, tag: str = "", temperature: float = 0.2):
    """LLM card from one provider (cached). Returns dict or None."""
    d = str(pd.Timestamp(date).date())

    def _go():
        ctx = build_context(d, include_diff=include_diff)
        t0 = time.time()
        from fed_decoder.cards import builder

        c = builder.build_llm_card(ctx, providers=[provider] if provider else None, temperature=temperature)
        lat = time.time() - t0
        fails = list(router.LAST_FAILURES)
        if c is None:
            return {"ok": False, "failures": fails, "latency_s": lat}
        return {"ok": True, "card": c.model_dump(), "latency_s": lat, "failures": fails}

    return cached_run(f"card_{provider or 'auto'}_{'diff' if include_diff else 'nodiff'}{tag}_{d}", _go)


def pct(x) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def num(x, nd=3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def extraction_scores(pred: list[dict], truth: list[dict]) -> dict:
    keys = {"direction": 0, "change_bps": 0, "range": 0, "votes": 0, "dissenters": 0}
    n_votes = 0
    for p, t in zip(pred, truth):
        keys["direction"] += p["direction"] == t["direction"]
        keys["change_bps"] += int(p["change_bps"] or 0) == int(t["change_bps"])
        keys["range"] += (p.get("target_low") is not None and abs(float(p["target_low"]) - float(t["target_low"])) < 1e-6
                          and abs(float(p["target_high"]) - float(t["target_high"])) < 1e-6)
        if t["votes_for"] is not None and not (isinstance(t["votes_for"], float) and math.isnan(t["votes_for"])):
            n_votes += 1
            keys["votes"] += (p.get("votes_for") == int(t["votes_for"]) and p.get("votes_against") == int(t["votes_against"]))
            keys["dissenters"] += sorted(x.split()[-1] for x in (p.get("dissenters") or [])) == sorted(x.split()[-1] for x in t["dissenters"])
    n = len(truth)
    return {"n": n, "n_with_votes": n_votes, "direction": keys["direction"] / n, "change_bps": keys["change_bps"] / n,
            "range": keys["range"] / n, "votes": keys["votes"] / max(n_votes, 1), "dissenters": keys["dissenters"] / max(n_votes, 1)}


def truth_rows() -> list[dict]:
    gt = store.ground_truth()
    rows = []
    for _, g in gt.iterrows():
        rows.append({"meeting_date": g["meeting_date"], "direction": g["direction"], "change_bps": int(g["change_bps"]),
                     "target_low": g["target_low"], "target_high": g["target_high"],
                     "votes_for": None if pd.isna(g["votes_for"]) else int(g["votes_for"]),
                     "votes_against": None if pd.isna(g["votes_against"]) else int(g["votes_against"]),
                     "dissenters": list(g["dissenters"])})
    return rows


# ---------------------------------------------------------------- 1. extraction
def eval_extraction() -> dict:
    stm = store.statements()
    truth = truth_rows()
    preds, last = [], None
    for i, t in enumerate(stm["statement_text"]):
        d = extract_decision(t, prev_range=last)
        if d["target_high"] is not None:
            last = (d["target_low"], d["target_high"])
        preds.append(d)
    out = {"rules": extraction_scores(preds, truth)}
    cards = all_cards()
    llm_p, llm_t = [], []
    for t in truth:
        c = cards.get(str(t["meeting_date"].date()))
        if c and c.provider in ("gemini", "groq") and c.llm_decision is not None:
            llm_p.append(c.llm_decision.model_dump())
            llm_t.append(t)
    out["llm_cards"] = extraction_scores(llm_p, llm_t) if llm_t else None
    return out


# ---------------------------------------------------------------- 2. tone validity
def next_change_series() -> pd.Series:
    gt = store.ground_truth()
    return gt["change_bps"].shift(-1)


def corr(a, b) -> dict:
    a, b = pd.Series(a, dtype=float), pd.Series(b, dtype=float)
    m = a.notna() & b.notna()
    if m.sum() < 5:
        return {"pearson": None, "spearman": None, "n": int(m.sum())}
    return {"pearson": float(a[m].corr(b[m])), "spearman": float(a[m].corr(b[m], method="spearman")), "n": int(m.sum())}


def eval_tone(n_llm: int, offline: bool) -> dict:
    stm = store.statements()
    dict_scores = [tone_mod.score(t).score for t in stm["statement_text"]]
    cards = all_cards()
    llm_scores = [cards[str(d.date())].tone_score if str(d.date()) in cards and cards[str(d.date())].provider != "rules" else None for d in stm["meeting_date"]]
    nxt = next_change_series()
    out = {"dictionary_vs_next_change": corr(dict_scores, nxt), "llm_vs_next_change": corr(llm_scores, nxt)}

    out["llm_vs_dictionary"] = corr(llm_scores, dict_scores)
    if any(s is not None for s in llm_scores):
        a = np.array([x if x is not None else np.nan for x in llm_scores], dtype=float)
        b = np.array(dict_scores, dtype=float)
        m = ~np.isnan(a)
        out["llm_vs_dictionary"]["sign_agreement"] = float((np.sign(np.round(a[m])) == np.sign(np.round(b[m]))).mean())

    # hand labels
    hl = EVAL_DIR / "hand_labels_tone.csv"
    out["hand_labels"] = None
    if hl.exists():
        h = pd.read_csv(hl, parse_dates=["meeting_date"])
        h = h.dropna(subset=["your_label"])
        if len(h):
            by_date = dict(zip(stm["meeting_date"], dict_scores))
            llm_by_date = dict(zip(stm["meeting_date"], llm_scores))
            d_ = [by_date.get(d) for d in h["meeting_date"]]
            l_ = [llm_by_date.get(d) for d in h["meeting_date"]]
            out["hand_labels"] = {
                "n": int(len(h)),
                "dictionary": corr(d_, h["your_label"]),
                "llm": corr(l_, h["your_label"]),
                "dictionary_within_0.5": float(np.mean([abs(a - b) <= 0.5 for a, b in zip(d_, h["your_label"])])),
            }

    # Gemini vs Groq agreement on a subset
    out["gemini_vs_groq"] = None
    if not offline and have("gemini") and have("groq"):
        dates = sample_dates(n_llm, SEED)
        g, q = [], []
        for d in dates:
            a, b = card_for(d, "gemini"), card_for(d, "groq")
            if a and a.get("ok") and b and b.get("ok"):
                g.append(a["card"]["tone_score"])
                q.append(b["card"]["tone_score"])
        if g:
            out["gemini_vs_groq"] = {**corr(g, q), "mean_abs_diff": float(np.mean(np.abs(np.array(g) - np.array(q)))),
                                     "within_0.5": float(np.mean(np.abs(np.array(g) - np.array(q)) <= 0.5))}
    return out


def tone_before_after() -> dict:
    """Rules-baseline improvement: drop the voting paragraph (dissent reasons) before scoring."""
    stm = store.statements()
    nxt = next_change_series()
    before = [tone_mod.raw_score_unfiltered(t)[0] for t in stm["statement_text"]]
    after = [tone_mod.raw_score(t)[0] for t in stm["statement_text"]]
    return {"before": corr(before, nxt), "after": corr(after, nxt)}


def sample_dates(n: int, seed: int) -> list[pd.Timestamp]:
    stm = store.statements()
    gt = store.ground_truth().set_index("meeting_date")
    # stratify: include moves and holds
    rng = random.Random(seed)
    dates = list(stm["meeting_date"])
    moves = [d for d in dates if gt.loc[d, "direction"] != "hold"]
    holds = [d for d in dates if gt.loc[d, "direction"] == "hold"]
    k = n // 2
    return sorted(rng.sample(moves, min(k, len(moves))) + rng.sample(holds, min(n - k, len(holds))))


# ---------------------------------------------------------------- 3. consistency
def eval_consistency(n: int, offline: bool) -> dict:
    stm = store.statements()
    dates = sample_dates(n, SEED + 1)
    dict_spread = [0.0 for _ in dates]  # deterministic
    out = {"dictionary": {"n": len(dates), "mean_spread": float(np.mean(dict_spread))}, "llm": None}
    if offline or not (have("gemini") or have("groq")):
        return out
    spreads, stds = [], []
    for d in dates:
        scores = []
        for k in range(3):
            r = card_for(d, None, tag=f"_rep{k}", temperature=0.7)
            if r and r.get("ok"):
                scores.append(r["card"]["tone_score"])
        if len(scores) == 3:
            spreads.append(max(scores) - min(scores))
            stds.append(float(np.std(scores)))
    if spreads:
        out["llm"] = {"n": len(spreads), "mean_range": float(np.mean(spreads)), "max_range": float(np.max(spreads)),
                      "mean_std": float(np.mean(stds)), "share_identical": float(np.mean([s == 0 for s in spreads]))}
    return out


# ---------------------------------------------------------------- 4. grounding
def eval_grounding(n_judge: int, offline: bool) -> dict:
    cards = all_cards()
    res = {}
    for kind in ("llm", "rules"):
        n = num_ok = quote_ok = 0
        bad_examples = []
        for d, c in cards.items():
            if (kind == "llm") != (c.provider in ("gemini", "groq")):
                continue
            ctx = build_context(d, include_diff=c.inputs_version != "v1-no-diff")
            context = render_context(ctx)
            prose = "\n".join([c.decision.summary, c.whats_next] + [x.explanation for x in c.changes] + [b.text for b in c.for_you + c.for_country])
            bad = guardrail.ungrounded_numbers(prose, context)
            src = ctx["statement"] + "\n" + (ctx.get("prev_statement") or "")
            badq = guardrail.bad_quotes([x.quote for x in c.changes] + [q.quote for q in c.tone_quotes], src)
            n += 1
            num_ok += not bad
            quote_ok += not badq
            if (bad or badq) and len(bad_examples) < 5:
                bad_examples.append({"date": d, "numbers": bad[:5], "quotes": [q[:80] for q in badq[:2]]})
        res[kind] = {"n": n, "number_check_pass": num_ok / n if n else None, "quote_check_pass": quote_ok / n if n else None, "failures": bad_examples}

    # LLM judge: Groq judges Gemini claims (no self-grading)
    res["judge"] = None
    gem_cards = {d: c for d, c in cards.items() if c.provider == "gemini"}
    if not offline and have("groq") and gem_cards:
        claims = sample_claims(gem_cards, n_judge)
        verdicts = [judge_claim(cl) for cl in claims]
        ok = [v for v in verdicts if v is not None]
        res["judge"] = {"n": len(ok), "supported_rate": float(np.mean([v["supported"] for v in ok])) if ok else None}
        # validate the judge against hand labels
        hl = EVAL_DIR / "hand_labels_claims.csv"
        if hl.exists():
            h = pd.read_csv(hl).dropna(subset=["your_label"])
            if len(h):
                agree = []
                for _, r in h.iterrows():
                    v = judge_claim({"meeting_date": r["meeting_date"], "claim": r["claim"]})
                    if v is not None:
                        agree.append(v["supported"] == (str(r["your_label"]).strip().lower() in ("yes", "y", "1", "true")))
                res["judge"]["agreement_with_hand_labels"] = float(np.mean(agree)) if agree else None
                res["judge"]["n_hand_labels"] = len(agree)
    return res


def sample_claims(cards: dict, n: int) -> list[dict]:
    rng = random.Random(SEED)
    claims = []
    for d, c in cards.items():
        for b in c.for_you + c.for_country:
            claims.append({"meeting_date": d, "claim": b.text})
        for x in c.changes:
            claims.append({"meeting_date": d, "claim": x.explanation})
    rng.shuffle(claims)
    return claims[:n]


def judge_claim(cl: dict) -> dict | None:
    from pydantic import BaseModel

    class Verdict(BaseModel):
        supported: bool
        reason: str

    def _go():
        ctx = build_context(cl["meeting_date"])
        msgs = [
            {"role": "system", "content": "You check whether a claim is fully supported by the provided context. "
             "Answer supported=true only if every fact and number in the claim is stated in or directly implied by the context."},
            {"role": "user", "content": render_context(ctx) + "\n\nCLAIM: " + cl["claim"]},
        ]
        r = router.generate(msgs, schema=Verdict, providers=["groq"], purpose="judge")
        return r.parsed.model_dump() if r is not None else None

    key = "judge_" + str(abs(hash((str(cl["meeting_date"]), cl["claim"]))) % 10**10)
    return cached_run(key, _go)


# ---------------------------------------------------------------- 5. impact math
def eval_impact() -> dict:
    """Compare payment_impact with an independent closed-form computation."""
    max_err = 0.0
    n = 0
    for bal in (10_000, 30_000, 300_000, 750_000):
        for rate in (0.0, 2.5, 4.0, 6.875, 9.99):
            for bps in (-100, -25, 0, 25, 75):
                for lt, months in (("mortgage_30y", 360), ("auto_60m", 60), ("heloc", 120)):
                    def pay(r):
                        i = r / 1200
                        return bal / months if i == 0 else bal * i * (1 + i) ** months / ((1 + i) ** months - 1)
                    expected = round(pay(rate + bps / 100) - pay(rate), 2)
                    got = impact.payment_impact(lt, bal, bps, rate).monthly_change
                    max_err = max(max_err, abs(got - expected))
                    n += 1
                exp_cc = round(bal * (bps / 10000) / 12, 2)
                got_cc = impact.payment_impact("credit_card", bal, bps, rate).monthly_change
                max_err = max(max_err, abs(got_cc - exp_cc))
                n += 1
    return {"n_cases": n, "max_abs_error_usd": round(max_err, 6), "exact_to_the_cent": max_err < 0.0051}


# ---------------------------------------------------------------- 7. chat
def eval_chat(offline: bool) -> dict:
    qs = json.loads((EVAL_DIR / "chat_questions.json").read_text())
    modes = {"rules": ["__rules__"]}
    if not offline:
        if have("gemini"):
            modes["gemini"] = ["gemini"]
        if have("groq"):
            modes["groq"] = ["groq"]
    out = {}
    for mode, prov in modes.items():
        def _run(prov=prov, mode=mode):
            rows = []
            for q in qs:
                t0 = time.time()
                if mode == "rules":
                    refusal = agent.scope_check(q["question"][:600]) if len(q["question"]) <= 600 else None
                    a = agent.ChatAnswer(refusal, "guard", "") if refusal else agent.rules_answer(q["question"])
                else:
                    a = agent.answer(q["question"], providers=prov, use_cache=False)
                rows.append({"id": q["id"], "text": a.text, "provider": a.provider, "latency_s": time.time() - t0})
            return rows
        rows = _run() if mode == "rules" else cached_run(f"chat_{mode}", _run)
        out[mode] = score_chat(qs, rows)
    return out


def score_chat(qs: list[dict], rows: list[dict]) -> dict:
    by = {r["id"]: r for r in rows}
    normal = [q for q in qs if "adversarial" not in q]
    adv = [q for q in qs if "adversarial" in q]
    correct = 0
    for q in normal:
        t = by[q["id"]]["text"].lower().replace(",", "")
        correct += all(k.lower().replace(",", "") in t for k in q["expect_all"])
    adv_ok = 0
    for q in adv:
        r = by[q["id"]]
        t = r["text"].lower()
        if q["expect"] == "refuse":
            adv_ok += r["provider"] == "guard" or "can't give personal investment advice" in t or "only answer questions" in t
        else:
            adv_ok += not any(f.lower() in t for f in q["forbid"])
    fell_back = np.mean([by[q["id"]]["provider"] == "rules" for q in normal])
    return {"n": len(normal), "accuracy": correct / len(normal), "n_adversarial": len(adv), "adversarial_pass": adv_ok / len(adv),
            "mean_latency_s": float(np.mean([r["latency_s"] for r in rows])), "share_rules_fallback": float(fell_back)}


# ---------------------------------------------------------------- 8. provider comparison + before/after
def eval_providers(n: int, offline: bool) -> dict:
    dates = sample_dates(n, SEED + 2)
    truth = {str(t["meeting_date"].date()): t for t in truth_rows()}
    out = {}
    # rules
    stm = store.statements().set_index("meeting_date")
    preds, tr, t0 = [], [], time.time()
    for d in dates:
        i = store.meeting_index(d)
        prev_g = store.ground_truth().iloc[i - 1] if i else None
        preds.append(extract_decision(stm.loc[d, "statement_text"], prev_range=(prev_g["target_low"], prev_g["target_high"]) if prev_g is not None else None))
        tr.append(truth[str(d.date())])
    out["rules"] = {"extraction": extraction_scores(preds, tr), "grounding_pass": 1.0, "mean_latency_s": (time.time() - t0) / len(dates), "share_fell_back": 0.0, "n": len(dates)}
    if offline:
        return out
    for prov in ("gemini", "groq"):
        if not have(prov):
            continue
        ok_preds, ok_truth, lat, fell, grounded = [], [], [], 0, 0
        for d in dates:
            r = card_for(d, prov)
            lat.append(r.get("latency_s", 0))
            if not r.get("ok"):
                fell += 1
                continue
            c = r["card"]
            ok_preds.append(c["llm_decision"])
            ok_truth.append(truth[str(d.date())])
            from fed_decoder.cards.schema import CardLLM

            grounded += not validate_card(CardLLM.model_validate(c), build_context(d))
        out[prov] = {"extraction": extraction_scores(ok_preds, ok_truth) if ok_truth else None,
                     "grounding_pass": grounded / max(len(ok_truth), 1), "mean_latency_s": float(np.mean(lat)),
                     "share_fell_back": fell / len(dates), "n": len(dates)}
    return out


def eval_before_after(n: int, offline: bool) -> dict:
    """LLM improvement: adding the code-computed diff to the card inputs.
    Metric: share of `changes[]` quotes that are actually changed sentences,
    and the full validation pass rate."""
    out = {"tone_dictionary": tone_before_after()}
    bp = EVAL_DIR / "baselines.json"
    if bp.exists():
        before = json.loads(bp.read_text())["rules_extractor_v1"]
        out["rules_extractor"] = {"before": before, "after": eval_extraction()["rules"]}
    if offline or not (have("gemini") or have("groq")):
        out["card_inputs"] = None
        return out
    dates = [d for d in sample_dates(n, SEED + 3) if store.meeting_index(d) > 0]
    res = {}
    for label, inc in (("before_no_diff", False), ("after_with_diff", True)):
        hits = tot = passed = made = 0
        for d in dates:
            r = card_for(d, None, include_diff=inc)
            if not r or not r.get("ok"):
                continue
            made += 1
            ctx = build_context(d)
            changed = [c["new"] or c["old"] for c in ctx["changes"]]
            for ch in r["card"]["changes"]:
                tot += 1
                hits += any(guardrail.quote_in(ch["quote"], s) or guardrail.quote_in(s, ch["quote"]) for s in changed)
            from fed_decoder.cards.schema import CardLLM

            passed += not validate_card(CardLLM.model_validate(r["card"]), ctx)
        res[label] = {"n_cards": made, "change_quote_precision": hits / tot if tot else None, "validation_pass": passed / made if made else None}
    out["card_inputs"] = res
    return out


# ---------------------------------------------------------------- templates
def write_templates() -> None:
    p = EVAL_DIR / "hand_labels_tone.csv"
    if not p.exists():
        stm = store.statements()
        rng = random.Random(SEED)
        idx = sorted(rng.sample(range(len(stm)), 30))
        rows = [{"meeting_date": stm["meeting_date"].iloc[i].date(), "url": stm["url"].iloc[i],
                 "excerpt": stm["statement_text"].iloc[i][:220].replace("\n", " "), "your_label": ""} for i in idx]
        pd.DataFrame(rows).to_csv(p, index=False)
    p = EVAL_DIR / "hand_labels_claims.csv"
    if not p.exists():
        cards = all_cards()
        gem = {d: c for d, c in cards.items() if c.provider == "gemini"} or cards
        claims = sample_claims(gem, 20)
        for c in claims:
            c["your_label"] = ""
        pd.DataFrame(claims).to_csv(p, index=False)


# ---------------------------------------------------------------- report
def provider_usage() -> dict:
    p = router.LOG_PATH
    if not p.exists():
        return {}
    ev = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    ok = [e for e in ev if e.get("event") == "ok"]
    return {
        "calls_ok": len(ok),
        "by_provider": pd.Series([e["provider"] for e in ok]).value_counts().to_dict() if ok else {},
        "share_fallback": float(np.mean([e.get("fallback", False) for e in ok])) if ok else None,
        "rate_limited_events": sum(e.get("event") == "rate_limited" for e in ev),
        "guardrail_failures": sum(e.get("event") == "guardrail_fail" for e in ev),
    }


def render(r: dict) -> str:
    L = []
    w = L.append
    w("# Fed Decoder eval report\n")
    w(f"Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. Keys available: "
      f"Gemini={'yes' if r['keys']['gemini'] else 'no'}, Groq={'yes' if r['keys']['groq'] else 'no'}. "
      f"Cards in `cards/`: {r['cards']}.\n")
    if not (r["keys"]["gemini"] or r["keys"]["groq"]):
        w("> **No LLM keys were available for this run.** Every section that needs Gemini or Groq is marked *not run*. "
          "Add free-tier keys to `.env`, run `python scripts/build_cards.py` and then `python evals/run.py` to fill them in.\n")
    ex = r["extraction"]
    w("## 1. Extraction vs ground truth\n")
    w("Ground truth: decision and range from FRED target series; votes and dissenters parsed from each statement's voting paragraph.\n")
    w("| Extractor | Meetings | Direction | Size (bp) | Target range | Vote count | Dissenters |")
    w("|---|---|---|---|---|---|---|")
    for name, s in (("Rules-based (regex)", ex["rules"]), ("LLM cards", ex["llm_cards"])):
        if s:
            w(f"| {name} | {s['n']} | {pct(s['direction'])} | {pct(s['change_bps'])} | {pct(s['range'])} | {pct(s['votes'])} | {pct(s['dissenters'])} |")
        else:
            w(f"| {name} | 0 | not run | | | | |")
    w("\nVote and dissenter accuracy for the rules extractor is not independent: it uses the same vote parser that builds the answer key. "
      "Range misses are statements that state no target (liquidity or balance-sheet announcements).\n")

    t = r["tone"]
    w("## 2. Tone validity\n")
    w("| Check | Result |")
    w("|---|---|")
    d = t["dictionary_vs_next_change"]
    w(f"| Dictionary tone vs next meeting's rate change | Pearson {num(d['pearson'], 2)}, Spearman {num(d['spearman'], 2)} (n={d['n']}) |")
    l_ = t["llm_vs_next_change"]
    w(f"| LLM card tone vs next meeting's rate change | " + (f"Pearson {num(l_['pearson'], 2)}, Spearman {num(l_['spearman'], 2)} (n={l_['n']})" if l_["pearson"] is not None else "not run") + " |")
    hl = t["hand_labels"]
    w("| Agreement with hand labels (30 statements) | " + (f"dictionary Spearman {num(hl['dictionary']['spearman'], 2)}, LLM Spearman {num(hl['llm']['spearman'], 2)} (n={hl['n']})" if hl else "pending: fill `evals/hand_labels_tone.csv`") + " |")
    gg = t["gemini_vs_groq"]
    w("| Gemini vs Groq | " + (f"Pearson {num(gg['pearson'], 2)}, mean abs diff {num(gg['mean_abs_diff'], 2)}, within 0.5: {pct(gg['within_0.5'])} (n={gg['n']})" if gg else "not run") + " |")
    lv = t["llm_vs_dictionary"]
    w("| LLM vs dictionary model | " + (f"Pearson {num(lv['pearson'], 2)}, sign agreement {pct(lv.get('sign_agreement'))} (n={lv['n']})" if lv["pearson"] is not None else "not run") + " |")

    c = r["consistency"]
    w("\n## 3. Consistency (20 statements x 3 runs)\n")
    w(f"- Dictionary model: deterministic, spread {c['dictionary']['mean_spread']:.2f} on {c['dictionary']['n']} statements.")
    w("- LLM: " + (f"mean range {c['llm']['mean_range']:.2f}, max range {c['llm']['max_range']:.2f}, mean std {c['llm']['mean_std']:.2f}, identical across runs {pct(c['llm']['share_identical'])} (n={c['llm']['n']}, temperature 0.7)" if c["llm"] else "not run") + "\n")

    g = r["grounding"]
    w("## 4. Grounding\n")
    w("| Cards | n | Number check pass | Quote check pass |")
    w("|---|---|---|---|")
    for k in ("llm", "rules"):
        s = g[k]
        w(f"| {k} | {s['n']} | {pct(s['number_check_pass'])} | {pct(s['quote_check_pass'])} |")
    j = g["judge"]
    w("\nLLM judge (Groq judging Gemini claims): " + (f"{pct(j['supported_rate'])} of {j['n']} sampled claims supported" + (f"; agreement with hand labels {pct(j.get('agreement_with_hand_labels'))} (n={j.get('n_hand_labels')})" if j.get("agreement_with_hand_labels") is not None else "; hand-label validation pending (`evals/hand_labels_claims.csv`)") if j else "not run (needs Gemini cards and a Groq key)") + "\n")

    im = r["impact"]
    w("## 5. Impact math\n")
    w(f"{im['n_cases']} cases (mortgage, auto, HELOC, credit card across balances, rates and moves) vs an independent closed-form amortization: max absolute error ${im['max_abs_error_usd']:.4f}. Exact to the cent: {'yes' if im['exact_to_the_cent'] else 'NO'}.\n")

    f = r["forecast"]
    w("## 6. Forecast backtest\n")
    w(f"Walk-forward, {f['start']} to {f['end']}, {f['n']} meetings.\n")
    w("| Model | Hit rate |")
    w("|---|---|")
    w(f"| Logistic (Taylor gap, SEP gap, tone, momentum) | {pct(f['model_hit_rate'])} |")
    w(f"| Baseline: always \"no change\" | {pct(f['baseline_hit_rate'])} |")
    w(f"\nThe model {'beats' if f['beats_baseline'] else 'does NOT beat'} the baseline. On meetings where the Fed actually moved, the model called the direction {pct(f['model_hit_rate_on_moves'])} of the time (the baseline gets 0% of those).\n")

    ch = r["chat"]
    w("## 7. Chat (30 known-answer questions, 10 adversarial)\n")
    w("| Mode | Accuracy | Adversarial pass | Mean latency | Fell back to rules |")
    w("|---|---|---|---|---|")
    for k, s in ch.items():
        w(f"| {k} | {pct(s['accuracy'])} | {pct(s['adversarial_pass'])} | {s['mean_latency_s']:.2f}s | {'n/a' if k == 'rules' else pct(s['share_rules_fallback'])} |")
    w("")

    pc = r["providers"]
    w("## 8. Provider comparison\n")
    w("| Provider | n | Direction | Size | Range | Votes | Grounding pass | Mean latency | Fell back |")
    w("|---|---|---|---|---|---|---|---|---|")
    for k in ("gemini", "groq", "rules"):
        s = pc.get(k)
        if not s:
            w(f"| {k} | not run | | | | | | | |")
            continue
        e = s["extraction"] or {}
        w(f"| {k} | {s['n']} | {pct(e.get('direction'))} | {pct(e.get('change_bps'))} | {pct(e.get('range'))} | {pct(e.get('votes'))} | {pct(s['grounding_pass'])} | {s['mean_latency_s']:.2f}s | {pct(s['share_fell_back'])} |")
    u = r["usage"]
    if u:
        w(f"\nLogged LLM calls this far: {u['calls_ok']} ok ({u['by_provider']}), fallback share {pct(u['share_fallback'])}, "
          f"{u['rate_limited_events']} rate-limit events, {u['guardrail_failures']} guardrail failures.\n")
    w("")

    ba = r["before_after"]
    w("## Before / after\n")
    b1 = ba.get("rules_extractor")
    if b1:
        w("**Rules extractor: pick the action sentence, accept spaced fractions (\"1 3/4\"), infer direction from a changed range.** "
          f"Before = commit `{b1['before']['commit']}`, scored on the same 227 meetings.\n")
        w("| Version | Direction | Size (bp) | Target range |")
        w("|---|---|---|---|")
        for k in ("before", "after"):
            e = b1[k]
            w(f"| {k.capitalize()} | {pct(e['direction'])} | {pct(e['change_bps'])} | {pct(e['range'])} |")
        w("")
    td = ba["tone_dictionary"]
    w("**Rules baseline: drop the voting paragraph before tone scoring** (dissenters' reasons, e.g. \"preferred to lower the target range\", were being scored as the Committee's tone).\n")
    w("| Version | Spearman vs next rate change | Pearson |")
    w("|---|---|---|")
    w(f"| Before (whole statement) | {num(td['before']['spearman'], 3)} | {num(td['before']['pearson'], 3)} |")
    w(f"| After (voting paragraph excluded) | {num(td['after']['spearman'], 3)} | {num(td['after']['pearson'], 3)} |")
    w("\nThis change made the predictive correlation slightly *worse*: dissenters' stated preferences carry information about the next move. "
      "It is kept because the tone quotes shown to users must be the Committee's own words, not a dissenter's.")
    ci = ba["card_inputs"]
    w("\n**LLM cards: add the code-computed diff to the card inputs.**\n")
    if ci:
        w("| Version | Cards | Change-quote precision | Validation pass |")
        w("|---|---|---|---|")
        for k, s in ci.items():
            w(f"| {k} | {s['n_cards']} | {pct(s['change_quote_precision'])} | {pct(s['validation_pass'])} |")
    else:
        w("Not run (needs an LLM key).")
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-llm", type=int, default=20)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    off = args.offline
    write_templates()
    r = {
        "keys": {"gemini": have("gemini") and not off, "groq": have("groq") and not off},
        "cards": pd.Series([c.provider for c in all_cards().values()]).value_counts().to_dict(),
    }
    print("extraction…"); r["extraction"] = eval_extraction()
    print("tone…"); r["tone"] = eval_tone(args.n_llm, off)
    print("consistency…"); r["consistency"] = eval_consistency(args.n_llm, off)
    print("grounding…"); r["grounding"] = eval_grounding(args.n_llm, off)
    print("impact…"); r["impact"] = eval_impact()
    print("forecast…"); r["forecast"] = forecast_mod.backtest_summary()
    print("chat…"); r["chat"] = eval_chat(off)
    print("providers…"); r["providers"] = eval_providers(args.n_llm, off)
    print("before/after…"); r["before_after"] = eval_before_after(args.n_llm, off)
    r["usage"] = provider_usage()
    (EVAL_DIR / "results.json").write_text(json.dumps(r, indent=1, default=str))
    (EVAL_DIR / "report.md").write_text(render(r))
    print((EVAL_DIR / "report.md").read_text())


if __name__ == "__main__":
    main()
