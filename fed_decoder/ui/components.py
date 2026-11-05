"""HTML building blocks for the Staircase UI. Presentation only: every number shown is
passed in from the data and calculation layers, and every piece of copy is rewritten
at render time by code (never by changing stored data)."""
from __future__ import annotations

import difflib
import html
import math
import re

from fed_decoder.analysis.diff import redline, sentences
from fed_decoder.ui import theme

E = html.escape

# One-line definitions shown on hover or tap (dotted underline).
GLOSSARY = {
    "target range": "The band the Fed sets for the overnight rate banks charge each other. Most short-term rates follow it.",
    "dissent": "A vote against the decision. Dissents show where the debate is heading.",
    "hawkish": "Leaning toward higher rates, usually because inflation is the bigger worry.",
    "dovish": "Leaning toward lower rates, usually because jobs or growth are the bigger worry.",
    "SEP": "Summary of Economic Projections: officials' own forecasts, published four times a year.",
    "basis point": "One hundredth of a percentage point. 25 basis points = 0.25%.",
    "Taylor rule": "A rule of thumb for where rates 'should' be, from inflation and how hot the economy is running.",
    "pt": "Percentage point. ¼ pt = 0.25%.",
}

NUM_WORD = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten", 11: "Eleven", 12: "Twelve"}


def term(word: str, key: str | None = None) -> str:
    d = GLOSSARY.get(key or word) or GLOSSARY.get((key or word).lower(), "")
    return f'<span class="term" tabindex="0" data-def="{E(d)}">{E(word)}</span>' if d else E(word)


# ---------------------------------------------------------------- formatting
def pct(x: float) -> str:
    return f"{x:.2f}%"


def fmt_range(lo, hi) -> str:
    if lo is None or hi is None or (isinstance(hi, float) and math.isnan(hi)):
        return "not stated"
    return pct(hi) if lo == hi else f"{lo:.2f}–{hi:.2f}%"


def points(bps: int) -> str:
    b = abs(int(bps))
    return {25: "a quarter point", 50: "half a point", 75: "three quarters of a point", 100: "a full point"}.get(b, f"{b / 100:.2f} points")


def frac_pt(bps: int) -> str:
    return {25: "¼", 50: "½", 75: "¾", 100: "1"}.get(abs(int(bps)), f"{abs(int(bps)) / 100:.2f}")


def headline(direction: str, bps: int) -> str:
    if direction == "hold":
        return "The Fed held interest rates steady"
    return f"The Fed {'cut' if direction == 'cut' else 'raised'} interest rates by {points(bps)}"


def short_move(direction: str, bps: int) -> str:
    if direction == "hold":
        return "held"
    return f"{'cut' if direction == 'cut' else 'raised'} {frac_pt(bps)} pt"


def arrow_chip(direction: str, bps: int) -> tuple[str, str]:
    if direction == "hold":
        return "→ held", "hold"
    if direction == "hike":
        return f"▲ +{abs(bps) / 100:.2f}", "hike"
    return f"▼ −{abs(bps) / 100:.2f}", "cut"


def verdict_headline(d, details: list[dict]) -> str:
    """Event + direction, 8 words max. 'Held at 3.50–3.75%. Three wanted a hike.'"""
    rng = fmt_range(d.target_low, d.target_high)
    first = {"hold": f"Held at {rng}.", "cut": f"Cut to {rng}.", "hike": f"Raised to {rng}."}[d.direction]
    if d.votes_for is None:
        return first
    if not d.votes_against:
        return first + " Unanimous."
    leans = {x["lean"] for x in details}
    n = NUM_WORD.get(len(details), str(len(details)))
    if leans == {"hawk"}:
        want = "a hike" if d.direction == "hold" else "less" if d.direction == "cut" else "more"
        tail = f"{n} wanted {want}." if len(details) > 1 else f"One wanted {want}."
    elif leans == {"dove"}:
        want = "a cut" if d.direction == "hold" else "more" if d.direction == "cut" else "less"
        tail = f"{n} wanted {want}." if len(details) > 1 else f"One wanted {want}."
    else:
        tail = f"{n} dissented." if len(details) > 1 else "One dissented."
    return f"{first} {tail}"


# ---------------------------------------------------------------- verdict facts
def vote_dots(n_for: int, details: list[dict], majority_names: list[str]) -> str:
    dots = []
    for i in range(n_for):
        nm = majority_names[i] if i < len(majority_names) else "Majority"
        dots.append(f'<span class="dot" tabindex="0" data-tip="{E(nm)}: voted with the decision"></span>')
    for x in details:
        cls = {"hawk": "dhike", "dove": "dcut"}.get(x["lean"], "dother")
        dots.append(f'<span class="dot {cls}" tabindex="0" data-tip="{E(x["name"])}: dissented, wanted {E(x["preferred"])}"></span>')
    return '<div class="dots" role="img" aria-label="Vote">' + "".join(dots) + "</div>"


def tone_words(score: float) -> tuple[str, str]:
    s = float(score)
    if s > 0.3:
        return "Hawkish", "hike"
    if s < -0.3:
        return "Dovish", "cut"
    return "Balanced", "hold"


def tone_caption(score: float, previous: list[float]) -> str:
    word, _ = tone_words(score)
    if not previous:
        return word
    delta = score - sum(previous[-3:]) / len(previous[-3:])
    if word == "Hawkish":
        trend = "tilting more" if delta > 0.3 else "easing off" if delta < -0.3 else "steady"
    elif word == "Dovish":
        trend = "tilting more" if delta < -0.3 else "easing off" if delta > 0.3 else "steady"
    else:
        trend = "tilting hawkish" if delta > 0.3 else "tilting dovish" if delta < -0.3 else "steady"
    return f"{word}, {trend}"


def tone_stripe(score: float, previous: list[float]) -> str:
    pos = lambda s: (max(-2.0, min(2.0, s)) + 2) / 4 * 100  # noqa: E731
    ghosts = "".join(f'<i style="left:{pos(p):.1f}%"></i>' for p in previous[-6:])
    return (f'<div class="stripe" role="img" aria-label="Tone {score:+.1f} from -2 dovish to +2 hawkish; faint ticks are the previous six meetings">'
            f'{ghosts}<b style="left:{pos(score):.1f}%"></b></div>'
            f'<div class="stripe-ends"><span>◀ {term("dovish")}</span><span>{term("hawkish")} ▶</span></div>')


# ---------------------------------------------------------------- small visuals
def sparkline(values: list[float], width: int = 120, height: int = 32, color: str = theme.INK) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = " ".join(f"{i / (len(values) - 1) * (width - 4) + 2:.1f},{height - 3 - (v - lo) / span * (height - 6):.1f}" for i, v in enumerate(values))
    last = values[-1]
    lx, ly = width - 2, height - 3 - (last - lo) / span * (height - 6)
    return (f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.5"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.5" fill="{color}"/></svg>')


def stacked_odds(p: dict) -> str:
    segs = [("hold", "hold", theme.HOLD), ("hike", "hike ▲", theme.HIKE), ("cut", "cut ▼", theme.CUT)]
    bar = "".join(f'<i style="width:{p[k] * 100:.1f}%;background:{c}" title="{lab} {p[k] * 100:.0f}%"></i>' for k, lab, c in segs if p[k] >= 0.005)
    legend = " · ".join(f"{lab} {p[k] * 100:.0f}%" for k, lab, _ in segs)
    return f'<div class="sbar" role="img" aria-label="{E(legend)}">{bar}</div><div class="slegend">{E(legend)}</div>'


def signed_money(x: float, unit: str = "/mo") -> str:
    if abs(x) < 0.005:
        return "no change"
    return f"{'−' if x < 0 else '+'}${abs(x):,.2f}{unit}" if abs(x) < 10 else f"{'−' if x < 0 else '+'}${abs(x):,.0f}{unit}"


# ---------------------------------------------------------------- copy rules (render time)
_CUT_PHRASES = [r"\bthe Committee('s)?\b", r"\bin support of (its|the Federal Reserve's) (goals|dual mandate)\b", r"\bremains? watchful\b",
                r"\bthe Federal Open Market Committee\b", r"\bthe Federal Reserve\b"]


def plain(text: str, max_words: int = 10) -> str:
    """Shorten a card sentence for display: drop boilerplate, keep the first clause, cap the words.
    Code-only, so no number can be introduced; the stored card is unchanged."""
    t = re.split(r"(?<=[.;])\s", text.strip())[0]
    for p in _CUT_PHRASES:
        t = re.sub(p, "the Fed", t, flags=re.I)
    t = re.sub(r"\bthe Fed the Fed\b", "the Fed", t)
    t = re.sub(r"^(This|The) (change|update|revision) (means|signals|shows|indicates) (that )?", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,;")
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words]).rstrip(",;:") + "…"
    return t[:1].upper() + t[1:]


# ---------------------------------------------------------------- redline
def _explain_for(new_s: str, old_s: str, changes) -> str:
    from fed_decoder.llm.guardrail import quote_in

    for c in changes:
        q = c.quote
        if (new_s and (quote_in(q, new_s) or quote_in(new_s, q))) or (old_s and (quote_in(q, old_s) or quote_in(old_s, q))):
            return c.explanation
    return ""


def changed_sentences(old: str | None, new: str, changes, skip=None) -> list[dict]:
    """Only the sentences that changed, each as a word-level redline with its note.
    `skip(sentence)` drops sentences covered elsewhere (the decision and the vote)."""
    if not old:
        return []
    a, b = sentences(old), sentences(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        olds, news, used = list(a[i1:i2]), list(b[j1:j2]), set()
        for n in news:
            best, br = None, 0.0
            for k, o in enumerate(olds):
                if k not in used:
                    r = difflib.SequenceMatcher(None, o, n).ratio()
                    if r > br:
                        best, br = k, r
            if best is not None and br >= 0.5:
                used.add(best)
                o = olds[best]
                ops = redline(o, n)
                item = {"old": o, "new": n, "ops": ops, "note": _explain_for(n, o, changes)}
            else:
                item = {"old": "", "new": n, "ops": None, "note": _explain_for(n, "", changes)}
            if not (skip and skip(item["new"] or item["old"])):
                out.append(item)
        for k, o in enumerate(olds):
            if k not in used and not (skip and skip(o)):
                out.append({"old": o, "new": "", "ops": None, "note": _explain_for("", o, changes)})
    return out


def redline_html(item: dict) -> str:
    if item["ops"]:
        return "".join(E(op.text) if op.op == "equal" else f"<del>{E(op.text)}</del>" if op.op == "delete" else f"<ins>{E(op.text)}</ins>"
                       for op in item["ops"])
    return f"<ins>{E(item['new'])}</ins>" if item["new"] else f"<del>{E(item['old'])}</del>"


def swap_phrase(item: dict) -> str | None:
    """'“solid” → “strong”' when a change is a short word swap."""
    if not item.get("ops"):
        return None
    dels = [op.text.strip() for op in item["ops"] if op.op == "delete" and op.text.strip()]
    ins = [op.text.strip() for op in item["ops"] if op.op == "insert" and op.text.strip()]
    if len(dels) == 1 and len(ins) == 1 and len(dels[0].split()) <= 3 and len(ins[0].split()) <= 3:
        return f"<del>{E(dels[0].strip(',.'))}</del> → <ins>{E(ins[0].strip(',.'))}</ins>"
    return None


def footer_html(text: str) -> str:
    return f'<div class="foot">{E(text)}</div>'
