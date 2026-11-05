"""Who voted which way, read from the statement's voting paragraph.

dissent_details() says, for each dissenter, which way they leaned relative to
the decision: 'hawk' (wanted tighter policy), 'dove' (wanted easier policy) or
'other' (objected to wording or something else), plus their stated preference.
"""
from __future__ import annotations

import re

from fed_decoder.data.ground_truth import parse_votes

_HAWK = re.compile(r"raise|increase|tighten|less aggressive|smaller (reduction|cut)|not support inclusion of an easing|no change|maintain|leave", re.I)
_DOVE = re.compile(r"lower|reduce|cut|larger (reduction|cut)|ease|easing|more accommodat|purchase", re.I)


_FRAC_BPS = {"1/4": 25, "1/2": 50, "3/4": 75}


def _pref_bps(p: str) -> int | None:
    m = re.search(r"by (\d+/\d+|\d+) (percentage point|basis points)", p)
    if not m:
        return None
    return _FRAC_BPS.get(m.group(1)) or (int(m.group(1)) if m.group(2).startswith("basis") else int(m.group(1)) * 100)


def _lean(pref: str, decision: str, change_bps: int = 0) -> str:
    p = pref.lower()
    size = _pref_bps(p)
    # same direction as the decision but a different size: smaller cut / bigger hike = hawkish, and vice versa
    if size and decision == "cut" and re.search(r"lower|reduce", p):
        return "hawk" if size < abs(change_bps) else "dove" if size > abs(change_bps) else "other"
    if size and decision == "hike" and re.search(r"raise|increase", p):
        return "hawk" if size > abs(change_bps) else "dove" if size < abs(change_bps) else "other"
    if re.search(r"\b(no change|maintain|leave|keep)\b", p) and not re.search(r"easing bias", p):
        return "hawk" if decision == "cut" else "dove" if decision == "hike" else "other"
    if re.search(r"lower|reduce|\bcut\b|larger (reduction|cut)|\bease\b|more accommodat", p):
        return "dove"
    if re.search(r"raise|increase|tighten|less aggressive|smaller|not support inclusion of an easing", p):
        return "hawk"
    return "other"


def _short_pref(pref: str) -> str:
    p = pref.lower()
    size = re.search(r"by (\d+/\d+|\d+-\d+/\d+|\d+) (percentage point|basis points)", p)
    amt = ""
    if size:
        amt = {"1/4": "¼-pt ", "1/2": "½-pt ", "3/4": "¾-pt "}.get(size.group(1), f"{size.group(1)} " if size.group(2).startswith("basis") else "")
    if re.search(r"raise|increase", p):
        return f"a {amt}hike".replace("a ¼", "a ¼")
    if re.search(r"lower|reduce", p):
        return f"a {amt}cut"
    if re.search(r"no change|maintain|leave|keep", p) and "easing bias" not in p:
        return "no change"
    if "easing bias" in p:
        return "no easing bias"
    return "a different approach"


def dissent_details(text: str, decision: str, dissenters: list[str], change_bps: int = 0) -> list[dict]:
    t = re.sub(r"\s+", " ", text)
    i = t.find("Voting against")
    block = t[i:] if i >= 0 else ""
    out = []
    for name in dissenters:
        last = name.split()[-1].rstrip(".,")
        # the reason that follows this person (shared reasons apply to everyone listed before "who")
        m = re.search(re.escape(last) + r"[^;]*?\bwho\b([^;]*)", block) or re.search(r"\b(?:President|Governor) " + re.escape(last) + r"\b([^.]*)", block)
        pref = m.group(1) if m else ""
        out.append({"name": name, "lean": _lean(pref, decision, change_bps), "preferred": _short_pref(pref) if pref else "a different approach"})
    return out


def voters(text: str) -> list[str]:
    return parse_votes(text).get("voters_for") or []
