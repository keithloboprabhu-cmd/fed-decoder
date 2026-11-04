"""Tools the chat model can call. All numbers come from here."""
from __future__ import annotations

import json
import re

import pandas as pd

from fed_decoder import config
from fed_decoder.analysis import diff as diff_mod
from fed_decoder.analysis import forecast as forecast_mod
from fed_decoder.analysis import impact
from fed_decoder.analysis.search import search_statements as _search
from fed_decoder.cards.store import load_card
from fed_decoder.data import store
from fed_decoder.llm.base import ToolSpec

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1)}

DEFAULT_RATE_SERIES = {"mortgage_30y": "MORTGAGE30US", "credit_card": "TERMCBCCALLNS", "auto_60m": "RIFLPBCIANM60NM"}


def parse_date(s: str) -> pd.Timestamp | None:
    s = (s or "").strip().lower()
    m = re.search(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", s)
    if m:
        return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3) or 15))
    m = re.search(r"(" + "|".join(MONTHS) + r"|" + "|".join(k[:3] for k in MONTHS) + r")\w*\.?,?\s+(?:\d{1,2},?\s+)?(\d{4})", s)
    if m:
        mon = next(v for k, v in MONTHS.items() if k.startswith(m.group(1)[:3]))
        return pd.Timestamp(int(m.group(2)), mon, 15)
    m = re.search(r"\b(20\d{2})\b", s)
    if m:
        return pd.Timestamp(int(m.group(1)), 6, 30)
    return None


def resolve_meeting(date_str: str) -> pd.Timestamp | None:
    d = parse_date(date_str)
    if d is None:
        return None
    stm = store.statements()
    # Prefer a meeting in the named month; else nearest.
    same = stm[(stm["meeting_date"].dt.year == d.year) & (stm["meeting_date"].dt.month == d.month)]
    if len(same) and not re.search(r"\d{4}-\d{1,2}-\d{1,2}", date_str or ""):
        # Several statements in one month (e.g. March 2020): prefer the last one that moved rates.
        gt = store.ground_truth().set_index("meeting_date")
        moved = [d for d in same["meeting_date"] if gt.loc[d, "change_bps"] != 0]
        return moved[-1] if moved else same.iloc[-1]["meeting_date"]
    return store.nearest_meeting(d)


def get_meeting(date: str) -> dict:
    d = resolve_meeting(date)
    if d is None:
        return {"error": f"could not understand date {date!r}; use YYYY-MM-DD"}
    gt = store.ground_truth()
    g = gt[gt["meeting_date"] == d].iloc[0]
    stm = store.statements()
    text = stm[stm["meeting_date"] == d]["statement_text"].iloc[0]
    card = load_card(d)
    out = {
        "meeting_date": str(d.date()),
        "decision": g["direction"],
        "change_bps": int(g["change_bps"]),
        "target_range_percent": [float(g["target_low"]), float(g["target_high"])],
        "previous_range_percent": [float(g["prev_low"]), float(g["prev_high"])],
        "votes_for": None if pd.isna(g["votes_for"]) else int(g["votes_for"]),
        "votes_against": None if pd.isna(g["votes_against"]) else int(g["votes_against"]),
        "dissenters": list(g["dissenters"]),
        "statement": text[:3500],
    }
    if card:
        out["tone_score"] = card.tone_score
        out["tone_quotes"] = [q.quote for q in card.tone_quotes[:3]]
        out["whats_next"] = card.whats_next
        out["for_you"] = [b.text for b in card.for_you]
    return out


def search_statements(query: str, year: int | None = None) -> dict:
    return {"results": _search(query, k=5, year=year)}


def diff_statements(a: str, b: str) -> dict:
    da, db = resolve_meeting(a), resolve_meeting(b)
    if da is None or db is None:
        return {"error": "could not resolve one of the dates"}
    stm = store.statements().set_index("meeting_date")
    ta, tb = stm.loc[da, "statement_text"], stm.loc[db, "statement_text"]
    ch = [c.to_dict() for c in diff_mod.sentence_changes(ta, tb)]
    return {"from": str(da.date()), "to": str(db.date()), "changed_fraction": diff_mod.changed_fraction(ta, tb), "changes": ch[:12]}


def get_series(id: str, start: str | None = None, end: str | None = None) -> dict:
    sid = id.upper().strip()
    if sid not in config.FRED_SERIES:
        return {"error": f"unknown series {sid}; available: {sorted(config.FRED_SERIES)}"}
    s = store.get_series(sid, start, end)
    if s.empty:
        return {"error": "no data in that window"}
    # Thin long daily series to at most ~24 points (month-end samples).
    pts = s.resample("ME").last().dropna() if len(s) > 60 else s
    if len(pts) > 24:
        pts = pts.iloc[:: max(1, len(pts) // 24)]
    return {
        "series_id": sid,
        "description": config.FRED_SERIES[sid],
        "first": {"date": str(s.index[0].date()), "value": round(float(s.iloc[0]), 3)},
        "last": {"date": str(s.index[-1].date()), "value": round(float(s.iloc[-1]), 3)},
        "min": round(float(s.min()), 3),
        "max": round(float(s.max()), 3),
        "points": [{"date": str(i.date()), "value": round(float(v), 3)} for i, v in pts.items()],
    }


def payment_impact(loan_type: str, balance: float, rate_change_bps: int, base_rate_pct: float | None = None) -> dict:
    lt = loan_type.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"mortgage": "mortgage_30y", "30y": "mortgage_30y", "car": "auto_60m", "auto": "auto_60m", "card": "credit_card", "credit": "credit_card", "heloc": "heloc"}
    for k, v in aliases.items():
        if k in lt and lt not in impact.LOAN_TERMS_MONTHS and lt not in impact.REVOLVING:
            lt = v
    src = None
    if base_rate_pct is None:
        sid = DEFAULT_RATE_SERIES.get(lt)
        if sid:
            last = store.series(sid)
            base_rate_pct, src = float(last.iloc[-1]), f"{sid} latest ({last.index[-1].date()})"
        elif lt == "heloc":
            base_rate_pct = float(store.series("DFEDTARU").iloc[-1]) + 3.0 + 0.5
            src = "prime (fed funds upper + 3) + 0.5 margin"
    try:
        r = impact.payment_impact(lt, float(balance), int(rate_change_bps), float(base_rate_pct)).to_dict()
    except ValueError as e:
        return {"error": str(e)}
    r["base_rate_source"] = src or "provided"
    return r


def forecast_next() -> dict:
    return forecast_mod.forecast_next().to_dict()


TOOLS = {
    "get_meeting": get_meeting,
    "search_statements": search_statements,
    "diff_statements": diff_statements,
    "get_series": get_series,
    "payment_impact": payment_impact,
    "forecast_next": forecast_next,
}

TOOL_SPECS = [
    ToolSpec("get_meeting", "Decision, target range, votes, dissenters, statement text and decoder card for the FOMC meeting nearest a date.",
             {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD, YYYY-MM, or 'September 2024'"}}, "required": ["date"]}),
    ToolSpec("search_statements", "Keyword search over every FOMC statement since 2000. Returns matching paragraphs with dates.",
             {"type": "object", "properties": {"query": {"type": "string"}, "year": {"type": "integer", "description": "optional year filter"}}, "required": ["query"]}),
    ToolSpec("diff_statements", "Sentence-level changes between two FOMC statements.",
             {"type": "object", "properties": {"a": {"type": "string", "description": "earlier meeting date"}, "b": {"type": "string", "description": "later meeting date"}}, "required": ["a", "b"]}),
    ToolSpec("get_series", "FRED data series summary. IDs: " + ", ".join(f"{k} ({v})" for k, v in config.FRED_SERIES.items()),
             {"type": "object", "properties": {"id": {"type": "string"}, "start": {"type": "string", "description": "YYYY-MM-DD"}, "end": {"type": "string", "description": "YYYY-MM-DD"}}, "required": ["id"]}),
    ToolSpec("payment_impact", "Monthly payment change for a loan if its rate moves. loan_type: mortgage_30y, auto_60m, credit_card, heloc. base_rate_pct defaults to the latest FRED average for that product.",
             {"type": "object", "properties": {"loan_type": {"type": "string"}, "balance": {"type": "number"}, "rate_change_bps": {"type": "integer"}, "base_rate_pct": {"type": "number"}}, "required": ["loan_type", "balance", "rate_change_bps"]}),
    ToolSpec("forecast_next", "Model probabilities (hold/cut/hike) for the next FOMC meeting, with signals and backtest. Educational only.",
             {"type": "object", "properties": {}}),
]


def run_tool(name: str, args: dict) -> str:
    fn = TOOLS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(**args), default=str, ensure_ascii=False)
    except TypeError as e:
        return json.dumps({"error": f"bad arguments: {e}"})
    except Exception as e:  # never surface a stack trace to the model or user
        return json.dumps({"error": f"tool failed: {type(e).__name__}"})
