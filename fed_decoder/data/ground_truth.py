"""Per-meeting ground truth, parsed in code. This is the eval answer key.

- Decision and target range come from FRED target series (DFEDTAR before
  2008-12-16, DFEDTARL/DFEDTARU after), comparing the day before the
  statement with two days after. This is independent of the statement text.
- Votes and dissenters are parsed from the statement's voting paragraph
  (reported since March 2002). Known edge cases can be corrected in
  data/ground_truth_overrides.csv.
"""
from __future__ import annotations

import re
from datetime import timedelta

import pandas as pd

from fed_decoder import config

RANGE_START = pd.Timestamp("2008-12-16")

_TITLE = re.compile(r",\s*(?:Chairman|Chairwoman|Chair|Vice Chairman|Vice Chair|Vice Chairwoman)\b\.?", re.I)
_NOT_NAME = {
    "Federal", "Reserve", "Committee", "Board", "Open", "Market", "Treasury", "Bank", "Chair", "Chairman", "Vice",
    "President", "Governor", "Governors", "In", "The", "Voting", "Absent", "Mr", "Ms", "Mrs", "Dr", "Bureau",
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
    "Kansas", "City", "New", "York", "St", "Louis", "San", "Francisco", "Federal Reserve",
}
_NAME = re.compile(r"\b([A-Z][a-zA-Z'\-]+(?: [A-Z]\.)*(?: [A-Z][a-zA-Z'\-]+)+(?:,? Jr\.)?)")


def target_series(fred: pd.DataFrame) -> pd.DataFrame:
    """Daily target range (low, high) from 1995 onward."""
    w = fred.pivot_table(index="date", columns="series_id", values="value")
    w.index = pd.to_datetime(w.index)
    idx = pd.date_range("1995-01-01", w.index.max(), freq="D")
    single = w["DFEDTAR"].reindex(idx).ffill()
    lo = w["DFEDTARL"].reindex(idx).ffill()
    hi = w["DFEDTARU"].reindex(idx).ffill()
    out = pd.DataFrame({"low": single, "high": single}, index=idx)
    mask = idx >= RANGE_START
    out.loc[mask, "low"] = lo[mask]
    out.loc[mask, "high"] = hi[mask]
    return out


def _clean_name(n: str) -> str:
    n = _TITLE.sub("", n).strip(" ,;:.")
    n = re.sub(r"^(?:and|were|was)\b:?\s*", "", n).strip()
    if n.endswith(" Jr"):
        n += "."
    return n


def _names(text: str) -> list[str]:
    out = []
    for m in _NAME.finditer(text):
        cand = _clean_name(m.group(1))
        words = cand.replace(",", "").replace(".", "").split()
        if not words or words[0] in _NOT_NAME or words[-1] in _NOT_NAME:
            continue
        if any(w in {"Federal", "Reserve", "Committee", "Bank"} for w in words):
            continue
        if any(len(w) > 1 and w.isupper() for w in words):  # "DO NOT REMOVE"
            continue
        if cand not in out:
            out.append(cand)
    return out


def parse_votes(text: str) -> dict:
    """Return votes_for, votes_against, voters, dissenters (None when not reported)."""
    t = re.sub(r"\s+", " ", text.replace("–", "-").replace("—", "-"))
    res = {"votes_for": None, "votes_against": None, "voters_for": [], "dissenters": []}

    # 2026+ format: "approved the following statement for release by a 12 - 0 vote"
    m = re.search(r"by an? (\d+)\s*-\s*(\d+) vote", t)
    if m:
        res["votes_for"], res["votes_against"] = int(m.group(1)), int(m.group(2))

    m = re.search(r"Voting (?:\(by notation\) )?for (?:the|this)[^:]*?(?:action|statement)[^:]*?(?:were|was)?:?\s*(.+?)(?=Voting against|Absent and not voting|In a related action|In taking|$)", t)
    if m:
        clause = re.sub(r"^\s*(?:were|was)?\s*:?\s*", "", _TITLE.sub(";", m.group(1)))
        parts = [p for p in re.split(r";\s*(?:and\s+)?|\s+and\s+(?=[A-Z])", clause) if p.strip()]
        voters = []
        for p in parts:
            p = _clean_name(p.split(". ")[0] if re.search(r"\.\s+[A-Z][a-z]+ [a-z]", p) else p)
            if p and re.match(r"^[A-Z]", p) and len(p.split()) >= 2:
                voters.append(p)
        res["voters_for"] = voters
        res["votes_for"] = len(voters)
        res["votes_against"] = 0

    against = re.findall(r"Voting against\b(.+?)(?=Voting against|Absent and not voting|In a related action|In taking|$)", t)
    dissenters: list[str] = []
    for clause in against:
        body = re.sub(r"^.*?\b(?:were|was)\b\s*:?\s*|^[^:]*:\s*", "", clause, count=1)
        # Entries are separated by ";" and each may carry a ", who ..." reason.
        for entry in re.split(r";\s*(?:and\s+)?", body):
            pieces = re.split(r"\bwho\b", entry)
            name_zones = [pieces[0]]
            # "X, who ..., and Y, who ..." : the next name sits after the last ", and "
            for mid in pieces[1:-1]:
                k = max(mid.rfind(", and "), mid.rfind(" and "))
                if k != -1:
                    name_zones.append(mid[k:])
            for zone in name_zones:
                for n in _names(zone):
                    if n not in dissenters and n not in res["voters_for"]:
                        dissenters.append(n)
    if against:
        res["dissenters"] = dissenters
        if res["votes_for"] is not None and not re.search(r"by an? \d+\s*-\s*\d+ vote", t):
            res["votes_against"] = len(dissenters)
    return res


def rate_decision(targets: pd.DataFrame, meeting: pd.Timestamp) -> dict:
    before = targets.loc[meeting - timedelta(days=1)]
    after = targets.loc[min(meeting + timedelta(days=2), targets.index.max())]
    change = round((after["high"] - before["high"]) * 100)
    direction = "hike" if change > 0 else "cut" if change < 0 else "hold"
    return {
        "direction": direction,
        "change_bps": int(change),
        "target_low": float(after["low"]),
        "target_high": float(after["high"]),
        "prev_low": float(before["low"]),
        "prev_high": float(before["high"]),
    }


def build(statements: pd.DataFrame, fred: pd.DataFrame) -> pd.DataFrame:
    targets = target_series(fred)
    rows = []
    for _, r in statements.iterrows():
        d = pd.Timestamp(r["meeting_date"])
        row = {"meeting_date": d, **rate_decision(targets, d), **parse_votes(r["statement_text"])}
        rows.append(row)
    gt = pd.DataFrame(rows)
    ov_path = config.DATA_DIR / "ground_truth_overrides.csv"
    if ov_path.exists():
        ov = pd.read_csv(ov_path, parse_dates=["meeting_date"])
        for _, o in ov.iterrows():
            m = gt["meeting_date"] == o["meeting_date"]
            field, val = o["field"], o["value"]
            if field == "dissenters":
                gt.loc[m, "dissenters"] = gt.loc[m, "dissenters"].apply(lambda _: [v for v in str(val).split("|") if v])
            elif field in ("votes_for", "votes_against", "change_bps"):
                gt.loc[m, field] = int(val)
            else:
                gt.loc[m, field] = val
    return gt
