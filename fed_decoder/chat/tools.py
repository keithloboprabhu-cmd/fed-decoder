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


LATEST = re.compile(r"\b(latest|last|most recent|newest|current|this)\b", re.I)


def statement_url(d: pd.Timestamp) -> str:
    return f"{config.FED_BASE}/newsevents/pressreleases/monetary{d:%Y%m%d}a.htm"


def get_meeting(date: str) -> dict:
    d = store.statements()["meeting_date"].max() if LATEST.search(date or "") and not parse_date(date) else resolve_meeting(date)
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
        "source": statement_url(d),
        "as_of": str(d.date()),
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


def notable_meetings(kind: str = "split", limit: int = 6) -> dict:
    """Meetings ranked from the record. kind: 'split' (most dissents), 'big_moves' (largest rate changes)."""
    gt = store.ground_truth().copy()
    gt["n_dissent"] = gt["dissenters"].apply(len)
    if kind == "big_moves":
        gt["size"] = gt["change_bps"].abs()
        top = gt[gt["size"] > 0].sort_values(["size", "meeting_date"], ascending=[False, False]).head(limit)
    else:
        top = gt[gt["n_dissent"] > 0].sort_values(["n_dissent", "meeting_date"], ascending=[False, False]).head(limit)
    rows = [{"meeting_date": str(r.meeting_date.date()), "decision": r.direction, "change_bps": int(r.change_bps),
             "votes_for": None if pd.isna(r.votes_for) else int(r.votes_for), "votes_against": int(r.n_dissent),
             "dissenters": list(r.dissenters)} for r in top.itertuples()]
    return {"kind": kind, "meetings": rows,
            "note": "Ranked from recorded votes since 2000; dissents are the clearest sign a decision was contested."}


from fed_decoder.chat import live  # noqa: E402

TOOLS = {
    "get_meeting": get_meeting,
    "search_statements": search_statements,
    "diff_statements": diff_statements,
    "get_series": get_series,
    "payment_impact": payment_impact,
    "forecast_next": forecast_next,
    "notable_meetings": notable_meetings,
    "fed_leadership": live.fed_leadership,
    "fomc_calendar": live.fomc_calendar,
    "fred_search": live.fred_search,
    "fred_series": live.fred_series,
    "bls_latest": live.bls_latest,
    "treasury_yields": live.treasury_yields,
    "fed_feed": live.fed_feed,
    "web_search": live.web_search,
    "fetch_page": live.fetch_page,
    "calc": live.calc,
}

_OBJ = lambda props, req=(): {"type": "object", "properties": props, **({"required": list(req)} if req else {})}  # noqa: E731
_S = {"type": "string"}

TOOL_SPECS = [
    ToolSpec("fed_leadership", "LIVE from federalreserve.gov: chair, vice chairs, governors, this year's FOMC voters and alternates, and which banks vote in coming years.", _OBJ({})),
    ToolSpec("fomc_calendar", "LIVE from federalreserve.gov: recent and upcoming FOMC meeting dates, and which have projections (SEP/dot plot).", _OBJ({})),
    ToolSpec("get_meeting", "One FOMC decision from the archive: move, target range, votes, dissenters, statement. date: 'latest', YYYY-MM-DD or 'September 2024'.",
             _OBJ({"date": _S}, ["date"])),
    ToolSpec("search_statements", "Keyword search over every FOMC statement since 2000.", _OBJ({"query": _S, "year": {"type": "integer"}}, ["query"])),
    ToolSpec("diff_statements", "Wording changes between two FOMC statements (dates a, b).", _OBJ({"a": _S, "b": _S}, ["a", "b"])),
    ToolSpec("notable_meetings", "Most contested meetings since 2000 (kind=split) or largest moves (kind=big_moves).",
             _OBJ({"kind": {"type": "string", "enum": ["split", "big_moves"]}})),
    ToolSpec("fred_search", "Find FRED series IDs for any economic topic.", _OBJ({"query": _S}, ["query"])),
    ToolSpec("fred_series", "LIVE FRED data for any series ID: latest value with date, recent history, and year-over-year % for price indexes. "
             "Fed funds upper/lower bound: DFEDTARU/DFEDTARL. CPI: CPIAUCSL. Unemployment: UNRATE.",
             _OBJ({"id": _S, "start": {"type": "string", "description": "YYYY-MM-DD (default 3 years ago)"}, "end": _S}, ["id"])),
    ToolSpec("bls_latest", "LIVE BLS release data: series = cpi, core_cpi, unemployment, payrolls or wages. Includes year-over-year % and monthly job change.",
             _OBJ({"series": _S}, ["series"])),
    ToolSpec("treasury_yields", "LIVE Treasury par yield curve (1-month to 30-year) for a date (default latest).", _OBJ({"on": {"type": "string", "description": "YYYY-MM-DD"}})),
    ToolSpec("fed_feed", "LIVE Fed RSS: latest press releases (kind=monetary), speeches, or testimony.",
             _OBJ({"kind": {"type": "string", "enum": ["monetary", "speeches", "testimony", "all"]}})),
    ToolSpec("web_search", "Web search for news, history and anything the other tools don't cover. Can be stale: never use it for leadership, rates or data.",
             _OBJ({"query": _S}, ["query"])),
    ToolSpec("fetch_page", "Read an official page in full (federalreserve.gov, regional Feds, BLS, BEA, Treasury, CBO, Congress.gov, major outlets).",
             _OBJ({"url": _S}, ["url"])),
    ToolSpec("calc", "Arithmetic. Use for EVERY calculation (differences, percents, conversions); never do math yourself.", _OBJ({"expr": _S}, ["expr"])),
    ToolSpec("payment_impact", "Monthly payment change for a loan if its rate moves. loan_type: mortgage_30y, auto_60m, credit_card, heloc.",
             _OBJ({"loan_type": _S, "balance": {"type": "number"}, "rate_change_bps": {"type": "integer"}, "base_rate_pct": {"type": "number"}},
                  ["loan_type", "balance", "rate_change_bps"])),
    ToolSpec("forecast_next", "Model odds (hold/cut/hike) for the next FOMC meeting, with backtest. Educational, a forecast not a fact.", _OBJ({})),
]


MY_IMPACT_SPEC = ToolSpec(
    "my_impact",
    "Show the reader their own monthly cost change for a rate move, computed privately in the app from the situation they entered. "
    "Use it for 'what if' or 'what does this mean for me' questions. You will NOT see the amounts; they are shown only to the reader.",
    {"type": "object", "properties": {"rate_change_bps": {"type": "integer", "description": "e.g. -25 for a quarter-point cut, 50 for a half-point hike"}},
     "required": ["rate_change_bps"]})


def run_tool(name: str, args: dict) -> str:
    if name == "my_impact":
        # The amounts are rendered by the app for the reader only; nothing personal goes back to the model.
        return json.dumps({"status": "shown to the reader in the app", "rate_change_bps": args.get("rate_change_bps")})
    fn = TOOLS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        return json.dumps(fn(**args), default=str, ensure_ascii=False)
    except TypeError as e:
        return json.dumps({"error": f"bad arguments: {e}"})
    except Exception as e:  # never surface a stack trace to the model or user
        return json.dumps({"error": f"tool failed: {type(e).__name__}"})
