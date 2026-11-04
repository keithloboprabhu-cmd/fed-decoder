"""Read-only access to the committed Parquet data, with simple caching."""
from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

import numpy as np
import pandas as pd

from fed_decoder import config

# Monthly/quarterly data are released with a lag. When we report "the latest
# value as of a meeting" we only use observations at least this old, to
# approximate what was public at the time.
RELEASE_LAG_DAYS = {"M": 35, "Q": 95, "D": 1, "W": 7}
FREQ = {
    "CPIAUCSL": "M", "PCEPILFE": "M", "UNRATE": "M", "PAYEMS": "M", "TERMCBCCALLNS": "Q",
    "RIFLPBCIANM60NM": "M", "GDPC1": "Q", "GDPPOT": "Q", "MORTGAGE30US": "W",
}


@lru_cache(maxsize=1)
def statements() -> pd.DataFrame:
    df = pd.read_parquet(config.STATEMENTS_PATH)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    return df.sort_values("meeting_date").reset_index(drop=True)


@lru_cache(maxsize=1)
def ground_truth() -> pd.DataFrame:
    df = pd.read_parquet(config.GROUND_TRUTH_PATH)
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    return df.sort_values("meeting_date").reset_index(drop=True)


@lru_cache(maxsize=1)
def fred_long() -> pd.DataFrame:
    df = pd.read_parquet(config.FRED_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


@lru_cache(maxsize=64)
def series(sid: str) -> pd.Series:
    df = fred_long()
    s = df[df["series_id"] == sid].set_index("date")["value"].sort_index()
    s.name = sid
    return s


def get_series(sid: str, start: str | None = None, end: str | None = None) -> pd.Series:
    s = series(sid)
    if start:
        s = s[s.index >= pd.Timestamp(start)]
    if end:
        s = s[s.index <= pd.Timestamp(end)]
    return s


def value_asof(sid: str, when: pd.Timestamp, lagged: bool = True) -> tuple[pd.Timestamp, float] | None:
    s = series(sid)
    cutoff = pd.Timestamp(when) - timedelta(days=RELEASE_LAG_DAYS[FREQ.get(sid, "D")] if lagged else 0)
    s = s[s.index <= cutoff]
    if s.empty:
        return None
    return s.index[-1], float(s.iloc[-1])


def yoy_asof(sid: str, when: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    s = series(sid)
    cutoff = pd.Timestamp(when) - timedelta(days=RELEASE_LAG_DAYS[FREQ.get(sid, "M")])
    s = s[s.index <= cutoff]
    if len(s) < 13:
        return None
    return s.index[-1], round((s.iloc[-1] / s.iloc[-13] - 1) * 100, 1)


def payroll_avg_change(when: pd.Timestamp, months: int = 3) -> tuple[pd.Timestamp, float] | None:
    s = series("PAYEMS")
    s = s[s.index <= pd.Timestamp(when) - timedelta(days=35)]
    if len(s) < months + 1:
        return None
    return s.index[-1], round(float(s.diff().iloc[-months:].mean()), 0)


def gdp_growth_asof(when: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    s = series("GDPC1")
    s = s[s.index <= pd.Timestamp(when) - timedelta(days=95)]
    if len(s) < 2:
        return None
    return s.index[-1], round(((s.iloc[-1] / s.iloc[-2]) ** 4 - 1) * 100, 1)


def move_around(sid: str, when: pd.Timestamp, pct: bool = False) -> float | None:
    """Change from the last close before `when` to the close on `when`
    (statements are released at 2pm, so the same-day close reflects them)."""
    s = series(sid)
    before = s[s.index < pd.Timestamp(when)]
    on = s[(s.index >= pd.Timestamp(when)) & (s.index <= pd.Timestamp(when) + timedelta(days=3))]
    if before.empty or on.empty:
        return None
    a, b = float(before.iloc[-1]), float(on.iloc[0])
    return round((b / a - 1) * 100, 2) if pct else round((b - a) * 100)  # pct or basis points


def meeting_index(when) -> int:
    df = statements()
    hits = np.where(df["meeting_date"] == pd.Timestamp(when))[0]
    if not len(hits):
        raise KeyError(f"no statement for {when}")
    return int(hits[0])


def nearest_meeting(when) -> pd.Timestamp:
    df = statements()
    d = pd.Timestamp(when)
    i = int(np.argmin(np.abs((df["meeting_date"] - d).dt.days.values)))
    return df["meeting_date"].iloc[i]
