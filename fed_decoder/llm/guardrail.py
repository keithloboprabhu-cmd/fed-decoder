"""Grounding guardrails: numbers and quotes in LLM output must come from the
context the model was given (statement text, computed data, tool results)."""
from __future__ import annotations

import re
import unicodedata

# 5-3/4, 1/4, 3.75, 1,234.5, -0.25, 25
_NUM = re.compile(r"(?<![\w/])[-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w/.])[-−]?\d+(?:\.\d+)?(?:[-‑ ]\d+/\d+)?(?:/\d+)?")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def _to_float(tok: str) -> float | None:
    t = tok.replace("−", "-").replace(",", "").replace("‑", "-").strip()
    try:
        m = re.fullmatch(r"(-?\d+)[- ](\d+)/(\d+)", t)
        if m:
            whole = float(m.group(1))
            frac = float(m.group(2)) / float(m.group(3))
            return whole + frac if whole >= 0 else whole - frac
        m = re.fullmatch(r"(-?\d+)/(\d+)", t)
        if m:
            return float(m.group(1)) / float(m.group(2))
        return float(t)
    except (ValueError, ZeroDivisionError):
        return None


def extract_numbers(text: str) -> list[tuple[str, float]]:
    text = unicodedata.normalize("NFKC", text)
    out = []
    # ISO dates count as their parts (year, month, day) so "2024-09-18" grounds "2024" and "18".
    for m in _DATE_ISO.finditer(text):
        for g in m.groups():
            out.append((g, float(g)))
    text = _DATE_ISO.sub(" ", text)
    for m in _NUM.finditer(text):
        v = _to_float(m.group(0))
        if v is not None:
            out.append((m.group(0), v))
    return out


def _variants(v: float) -> set[float]:
    """A context number also grounds its unit conversions:
    basis points <-> percentage points, and sign flips (a cut of 25 = -25)."""
    vs = {v, abs(v), v * 100, v / 100, abs(v) * 100, abs(v) / 100}
    return {round(x, 4) for x in vs}


def context_number_set(context: str) -> set[float]:
    s: set[float] = set()
    for tok, v in extract_numbers(context):
        s |= _variants(v)
        m = re.fullmatch(r"-?(\d+)[-‑ ](\d+)/(\d+)", tok)
        if m:  # "1-3/4" also grounds "1" and "3/4"
            s |= _variants(float(m.group(1))) | _variants(int(m.group(2)) / int(m.group(3)))
    return s


def ungrounded_numbers(output: str, context: str, allow: set[float] | None = None) -> list[str]:
    allowed = context_number_set(context) | (allow or set())
    bad = []
    for tok, v in extract_numbers(output):
        if round(v, 4) in allowed or round(abs(v), 4) in allowed:
            continue
        # tolerate rounding of a context value to 1 or 2 decimals
        if any(abs(v - c) < 0.006 for c in allowed if abs(c) < 1e6):
            continue
        # a context value rounded to the same number of decimals ("3.7" from a calc result of 3.717251);
        # whole numbers still need an exact match
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if dec and any(round(c, dec) == round(abs(v), dec) for c in allowed if abs(c) < 1e6):
            continue
        bad.append(tok)
    return bad


def _norm_quote(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace("\u2011", "-").replace("\u2010", "-")
    s = re.sub(r"\s+", " ", s).strip().strip('"').strip()
    return s.lower().rstrip(".")


def quote_in(quote: str, source: str) -> bool:
    """Verbatim check. Markdown emphasis is ignored, and a quote shortened with
    an ellipsis passes if every piece (3+ words) appears in order in the source."""
    q = _norm_quote(quote.replace("**", "").replace("__", ""))
    if not q:
        return False
    src = _norm_quote(source.replace("**", ""))
    pieces = [p.strip(" ,;") for p in re.split(r"\.\.\.|\u2026", q) if p.strip(" ,;")]
    if len(pieces) <= 1:
        return (pieces[0] if pieces else q) in src
    pos = 0
    for p in pieces:
        if len(p.split()) < 3:
            return False
        i = src.find(p, pos)
        if i == -1:
            return False
        pos = i + len(p)
    return True


def bad_quotes(quotes: list[str], source: str) -> list[str]:
    return [q for q in quotes if q and not quote_in(q, source)]
