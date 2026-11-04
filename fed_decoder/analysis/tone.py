"""Dictionary tone model (no LLM): weighted hawkish and dovish phrases.

Raw score = (hawkish weight - dovish weight) / sqrt(1 + matches). It is mapped
onto the card scale (-2 dovish ... +2 hawkish) with a linear calibration that
is fit against the LLM card scores when those exist (see `calibrate`), and
otherwise against the corpus z-score.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

from fed_decoder import config
from fed_decoder.analysis.diff import sentences

# (pattern, weight). Positive = hawkish, negative = dovish.
PHRASES: list[tuple[str, float]] = [
    # --- hawkish: policy action / guidance
    (r"\braise[sd]? (?:its|the) target", 2.0),
    (r"\bincrease (?:its|the) target", 2.0),
    (r"\bfurther (?:policy )?firming\b", 1.5),
    (r"\badditional (?:policy )?firming\b", 1.5),
    (r"\bongoing increases in the target range\b", 1.5),
    (r"\bremoving (?:its )?policy accommodation\b", 1.0),
    (r"\bremoval of policy accommodation\b", 1.0),
    (r"\bfurther gradual increases\b", 1.2),
    (r"\breduc\w* (?:its |the )?holdings\b", 0.8),
    (r"\bdeliver price stability\b", 1.0),
    (r"\bstrongly committed to returning inflation\b", 1.2),
    (r"\bhighly attentive to inflation risks\b", 1.0),
    (r"\bremain vigilant\b", 0.8),
    # --- hawkish: inflation assessment
    (r"\binflation (?:remains|has remained|is) elevated\b", 1.2),
    (r"\belevated inflation\b", 1.0),
    (r"\binflation(?:ary)? pressures\b", 0.8),
    (r"\bheightened inflation\b", 1.0),
    (r"\bupside risks? to inflation\b", 1.2),
    (r"\binflation (?:has )?(?:moved|picked|risen|increased) up\b", 1.0),
    (r"\bincreases in energy (?:and other commodity )?prices\b", 0.5),
    (r"\bunwelcome (?:rise|increase) in inflation\b", 1.0),
    (r"\bweighted mainly toward conditions that may generate heightened inflation\b", 1.0),
    # --- hawkish: real economy strength
    (r"\b(?:solid|strong|robust) (?:pace|rate|growth)\b", 0.5),
    (r"\bjob gains have been (?:solid|strong|robust)\b", 0.5),
    (r"\blabor market (?:has )?(?:remained |continued to )?(?:strengthen|strong|tight)\w*\b", 0.5),
    (r"\bunemployment rate (?:has )?(?:declined|remained low|fell)\b", 0.4),
    (r"\bresilient\b", 0.3),
    # --- dovish: policy action / guidance
    (r"\blower(?:s|ed)? (?:its|the) target", -2.0),
    (r"\breduce (?:its|the) target", -2.0),
    (r"\bdecrease (?:its|the) target", -2.0),
    (r"\bcut\b", -1.0),
    (r"\baccommodative\b", -1.0),
    (r"\bpolicy accommodation\b(?! (?:can|will) be removed)", -0.4),
    (r"\b(?:be )?patient\b", -0.8),
    (r"\bexceptionally low levels\b", -1.5),
    (r"\bfor an extended period\b", -1.2),
    (r"\b0 to 1/4 percent\b", -1.5),
    (r"\b(?:asset|securities|treasury securities) purchases\b", -1.0),
    (r"\bincrease (?:its )?holdings\b", -1.0),
    (r"\bexpand (?:its )?holdings\b", -1.0),
    (r"\bpurchase (?:additional )?(?:agency |longer-term |treasury )", -1.0),
    (r"\bsupport (?:the|a) (?:economy|stronger|recovery)\b", -0.6),
    (r"\bact as appropriate to sustain the expansion\b", -1.2),
    (r"\bwill act (?:in a timely manner|as needed)\b", -0.8),
    (r"\buse its full range of tools\b", -1.2),
    (r"\badjustments to the target range\b", -0.3),
    # --- dovish: risk assessment
    (r"\bdownside risks?\b", -1.0),
    (r"\bweighted mainly toward conditions that may generate economic weakness\b", -1.5),
    (r"\bweak(?:ness|ened|ening|er)\b", -0.7),
    (r"\bsoften(?:ed|ing)?\b", -0.6),
    (r"\bdeteriorat\w*\b", -0.8),
    (r"\bcontraction\b", -0.8),
    (r"\bstrains?\b", -0.6),
    (r"\bslack\b", -0.6),
    (r"\bslow(?:ed|ing|er)\b", -0.5),
    (r"\bmoderated\b", -0.4),
    (r"\b(?:running |remained |remains )?below (?:its |the Committee's )?(?:longer-run objective|2 percent)\b", -0.8),
    (r"\bunemployment rate (?:has )?(?:moved|ticked|risen|increased) up\b", -0.8),
    (r"\b(?:downside )?risks to employment\b", -0.8),
    (r"\bcoronavirus\b", -0.8),
    (r"\binflation (?:has )?(?:eased|declined|moderated)\b", -0.5),
    (r"\bdisinflation\b", -0.5),
]

_COMPILED = [(re.compile(p, re.I), w, p) for p, w in PHRASES]
_CAL_PATH = config.DATA_DIR / "tone_calibration.json"


@dataclass
class ToneResult:
    raw: float
    score: float  # calibrated, clipped to [-2, 2]
    matches: list[dict]  # {"phrase", "weight", "quote"}


def policy_text(text: str) -> str:
    """Drop the voting paragraph (dissent reasons are not the Committee's
    tone) and discount-rate boilerplate."""
    keep = []
    for para in text.split("\n\n"):
        p = para.strip()
        if re.match(r"(Voting|Absent and not voting|In a related action|In taking the discount rate action|In taking this action)", p):
            continue
        keep.append(p)
    return "\n\n".join(keep)


def raw_score(text: str) -> tuple[float, list[dict]]:
    matches: list[dict] = []
    hawk = dove = 0.0
    for sent in sentences(policy_text(text)):
        for rx, w, _ in _COMPILED:
            for m in rx.finditer(sent):
                matches.append({"phrase": m.group(0), "weight": w, "quote": sent})
                if w > 0:
                    hawk += w
                else:
                    dove += -w
    raw = (hawk - dove) / math.sqrt(1 + len(matches))
    return raw, matches


def load_calibration() -> tuple[float, float]:
    try:
        d = json.loads(_CAL_PATH.read_text())
        return float(d["slope"]), float(d["intercept"])
    except Exception:
        return 0.75, 0.0


def calibrate(raw_scores: list[float], target_scores: list[float] | None = None) -> dict:
    """Fit raw -> card scale. With targets (LLM card scores) use least squares;
    without, map the corpus so that +/-2 standard deviations hit +/-2."""
    import numpy as np

    x = np.asarray(raw_scores, dtype=float)
    if target_scores is not None and len(target_scores) >= 10:
        y = np.asarray(target_scores, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        method = "least squares vs LLM card scores"
    else:
        sd = float(x.std()) or 1.0
        slope, intercept = 1.0 / sd, -float(x.mean()) / sd
        method = "corpus z-score"
    d = {"slope": float(slope), "intercept": float(intercept), "method": method, "n": int(len(x))}
    _CAL_PATH.write_text(json.dumps(d, indent=2))
    return d


def score(text: str) -> ToneResult:
    raw, matches = raw_score(text)
    slope, intercept = load_calibration()
    s = max(-2.0, min(2.0, slope * raw + intercept))
    return ToneResult(raw=round(raw, 3), score=round(s, 2), matches=matches)


def top_quotes(result: ToneResult, k: int = 3) -> list[dict]:
    """The sentences that move the score most, with their matched phrases."""
    by_quote: dict[str, dict] = {}
    for m in result.matches:
        q = by_quote.setdefault(m["quote"], {"quote": m["quote"], "weight": 0.0, "phrases": []})
        q["weight"] += m["weight"]
        q["phrases"].append(m["phrase"])
    ranked = sorted(by_quote.values(), key=lambda q: abs(q["weight"]), reverse=True)
    return [dict(q, weight=round(q["weight"], 2), direction="hawkish" if q["weight"] > 0 else "dovish") for q in ranked[:k] if q["weight"] != 0]
