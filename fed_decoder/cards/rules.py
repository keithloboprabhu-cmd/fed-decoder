"""Rules-based decoder (no LLM). Powers pasted statements when the APIs are
unavailable, and is the eval baseline. Uses only the statement text (plus
the previous statement for the size of moves the text doesn't state)."""
from __future__ import annotations

import re

from fed_decoder.analysis import tone as tone_mod
from fed_decoder.cards.schema import Bullet, Card, ChangeItem, Citation, Decision, ToneQuote
from fed_decoder.data.ground_truth import parse_votes

RULES_LABEL = "Automated summary (rules-based)"

_FRAC = r"\d+(?:[- ]\d+/\d+)?|\d+/\d+|\d+\.\d+"
_UP = r"rais\w*|increas\w*|tighten\w*|firm\w*"
_DOWN = r"lower\w*|reduc\w*|decreas\w*|cut\w*|eas\w*"
_HOLD = r"keep\w*|maintain\w*|leav\w*|hold\w*|decided today to keep|remain\w*"


def frac_to_float(s: str) -> float:
    s = s.strip()
    m = re.fullmatch(r"(\d+)[- ](\d+)/(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.fullmatch(r"(\d+)/(\d+)", s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    return float(s)


def _policy_sentence(text: str) -> str:
    """The sentence that states the rate decision. Prefer sentences with an
    action verb ("decided", "voted") over forward-guidance sentences."""
    t = re.sub(r"\s+", " ", text).replace("\u2011", "-").replace("\u2010", "-")
    cands = []
    for sent in re.split(r"(?<=\.)\s+(?=[A-Z])", t):
        if re.search(r"target (?:range )?for the federal funds rate|federal funds rate target|target rate|target range", sent, re.I) and "percent" in sent:
            cands.append(sent)
    for sent in cands:
        if re.search(r"\b(decided|voted|agreed|establish|will maintain|reaffirmed|remains appropriate)\b", sent) and re.search(rf"(?:{_FRAC}) percent", sent):
            return sent
    return cands[0] if cands else ""


def extract_range(text: str) -> tuple[float, float] | None:
    s = _policy_sentence(text)
    if not s:
        return None
    m = re.search(rf"\b({_FRAC})(?: percent)? to ({_FRAC}) percent", s)
    if m:
        return frac_to_float(m.group(1)), frac_to_float(m.group(2))
    m = re.search(rf"(?:at|to|of) ({_FRAC}) percent", s)
    if m:
        v = frac_to_float(m.group(1))
        return v, v
    return None


def extract_decision(text: str, prev_text: str | None = None, prev_range: tuple[float, float] | None = None) -> dict:
    """`prev_range` (the last known range) lets us size moves the text doesn't
    state; otherwise we parse it from `prev_text`."""
    s = _policy_sentence(text)
    rng = extract_range(text)
    prev_rng = prev_range or (extract_range(prev_text) if prev_text else None)
    size = None
    m = re.search(r"by (\d+) basis points?|(\d+) basis points?|by (\d+(?:-\d+/\d+)?|\d+/\d+) percentage points?", s)
    if m:
        size = int(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else round(frac_to_float(m.group(3)) * 100)
    head = s[:200].lower()
    if re.search(rf"\b(?:{_UP})\b", head) and not re.search(r"\b(?:keep|maintain)\b", head):
        direction = "hike"
    elif re.search(rf"\b(?:{_DOWN})\b", head) and not re.search(r"\b(?:keep|maintain)\b", head):
        direction = "cut"
    else:
        direction = "hold"
    # Wording like "decided to establish a target range" names no direction:
    # infer it from the change in the stated range.
    if direction == "hold" and rng and prev_rng and abs(rng[1] - prev_rng[1]) > 1e-9:
        direction = "hike" if rng[1] > prev_rng[1] else "cut"
    if size is None and direction != "hold" and rng and prev_rng:
        size = round(abs(rng[1] - prev_rng[1]) * 100)
    if direction == "hold":
        size = 0
    change = (size or 0) * (1 if direction == "hike" else -1 if direction == "cut" else 0)
    votes = parse_votes(text)
    return {
        "direction": direction,
        "change_bps": int(change),
        "target_low": rng[0] if rng else None,
        "target_high": rng[1] if rng else None,
        "votes_for": votes["votes_for"],
        "votes_against": votes["votes_against"],
        "dissenters": votes["dissenters"],
        "policy_sentence": s,
    }


def fmt_range(lo: float | None, hi: float | None) -> str:
    if lo is None or hi is None:
        return "an unstated level"
    f = lambda x: f"{x:.2f}".rstrip("0").rstrip(".")  # noqa: E731
    return f"{f(hi)}%" if lo == hi else f"{f(lo)}% to {f(hi)}%"


def decision_summary(d: dict) -> str:
    rng = fmt_range(d.get("target_low"), d.get("target_high"))
    bps = abs(d.get("change_bps") or 0)
    if d["direction"] == "hike":
        return f"The Fed raised its policy rate by {bps} basis points, to {rng}."
    if d["direction"] == "cut":
        return f"The Fed cut its policy rate by {bps} basis points, to {rng}."
    return f"The Fed held its policy rate at {rng}."


def build_rules_card(ctx: dict) -> Card:
    """Template-filled card from the code-computed context (see context.py)."""
    text = ctx["statement"]
    d = extract_decision(text, ctx.get("prev_statement"))
    notes = [RULES_LABEL]
    if d["target_high"] is None and ctx.get("ground_truth", {}).get("target_high") is not None:
        # Statement states no range (e.g. a liquidity-only statement): show the prevailing one.
        d["target_low"], d["target_high"] = ctx["ground_truth"]["target_low"], ctx["ground_truth"]["target_high"]
        notes.append("Statement does not state a target; showing the prevailing target from FRED.")
    tr = tone_mod.score(text)
    quotes = tone_mod.top_quotes(tr, 3)
    impacts = ctx["impacts"]
    vote_txt = ""
    if d["votes_for"] is not None:
        vote_txt = f" The vote was {d['votes_for']}-{d['votes_against']}."
        if d["dissenters"]:
            vote_txt += " Dissenting: " + ", ".join(d["dissenters"]) + "."
    changes = []
    for c in ctx["changes"][:6]:
        if c["kind"] == "added":
            changes.append(ChangeItem(quote=c["new"], explanation="New language added in this statement."))
        elif c["kind"] == "removed":
            changes.append(ChangeItem(quote=c["old"], explanation="Language from the previous statement that was dropped."))
        else:
            changes.append(ChangeItem(quote=c["new"], explanation="Reworded from the previous statement: “" + c["old"][:160] + ("…”" if len(c["old"]) > 160 else "”")))
    for_you = [Bullet(topic=b["topic"], text=b["text"]) for b in impacts["for_you"]]
    for_country = [Bullet(topic=b["topic"], text=b["text"]) for b in impacts["for_country"]]
    lean = "hawkish (leaning toward higher rates)" if tr.score > 0.3 else "dovish (leaning toward lower rates)" if tr.score < -0.3 else "balanced"
    return Card(
        meeting_date=ctx["meeting_date"],
        decision=Decision(
            direction=d["direction"],
            change_bps=d["change_bps"],
            target_low=d["target_low"] if d["target_low"] is not None else float("nan"),
            target_high=d["target_high"] if d["target_high"] is not None else float("nan"),
            votes_for=d["votes_for"],
            votes_against=d["votes_against"],
            dissenters=d["dissenters"],
            summary=decision_summary(d) + vote_txt,
        ),
        changes=changes,
        tone_score=tr.score,
        tone_quotes=[ToneQuote(quote=q["quote"], direction=q["direction"]) for q in quotes],
        for_you=for_you,
        for_country=for_country,
        whats_next=f"The dictionary tone reading is {lean}.",
        confidence="medium" if d["target_high"] is not None else "low",
        citations=[Citation(source="statement", detail=d["policy_sentence"][:300])]
        + [Citation(source=s, detail=v) for s, v in ctx["data_citations"]],
        provider="rules",
        model="rules-v1",
        validated=True,
        validation_notes=notes,
    )
