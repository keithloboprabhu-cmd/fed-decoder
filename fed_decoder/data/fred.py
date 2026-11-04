"""FRED / ALFRED download.

With FRED_API_KEY set we use the official API; without it we use the public
fredgraph CSV endpoint, which needs no key (verified 2026-11 for every series
in config.FRED_SERIES). SEP medians (on FRED since the December 2015 SEP) are pulled as ALFRED vintages so the
forecast only ever sees the projection that was public at each meeting.
"""
from __future__ import annotations

import io
import time
from datetime import date

import pandas as pd
import requests

from fed_decoder import config

_S = requests.Session()
_S.headers["User-Agent"] = config.USER_AGENT


def _csv(url: str, params: dict, tries: int = 4) -> pd.DataFrame:
    for attempt in range(tries):
        try:
            r = _S.get(url, params=params, timeout=60)
            if r.status_code == 200 and r.text.startswith("observation_date"):
                return pd.read_csv(io.StringIO(r.text))
        except requests.RequestException:
            pass
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"FRED fetch failed: {params}")


def fetch_series(series_id: str, start: str = "1995-01-01") -> pd.Series:
    key = config.fred_key()
    if key:
        r = _S.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": key, "file_type": "json", "observation_start": start},
            timeout=60,
        )
        r.raise_for_status()
        obs = r.json()["observations"]
        s = pd.Series({pd.Timestamp(o["date"]): o["value"] for o in obs})
    else:
        df = _csv("https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": series_id, "cosd": start})
        s = df.set_index(pd.to_datetime(df["observation_date"]))[series_id]
    s = pd.to_numeric(s.replace(".", None), errors="coerce").dropna()
    s.name = series_id
    return s


def fetch_all(start: str = "1995-01-01") -> pd.DataFrame:
    """Long format: date, series_id, value."""
    frames = []
    for sid in config.FRED_SERIES:
        s = fetch_series(sid, start)
        if s.empty:
            raise RuntimeError(f"series {sid} returned no data; check the ID")
        frames.append(pd.DataFrame({"date": s.index, "series_id": sid, "value": s.values}))
        print(f"{sid}: {len(s)} obs, last {s.index[-1].date()} = {s.iloc[-1]}")
    return pd.concat(frames, ignore_index=True)


def fetch_sep_vintage(asof: date) -> dict[int, float]:
    """SEP median fed funds projection by year, as published on `asof`."""
    df = _csv(
        "https://alfred.stlouisfed.org/graph/alfredgraph.csv",
        {"id": "FEDTARMD", "vintage_date": asof.isoformat()},
        tries=2,
    )
    col = [c for c in df.columns if c != "observation_date"][0]
    df = df.dropna(subset=[col])
    df = df[pd.to_numeric(df[col], errors="coerce").notna()]
    return {int(str(d)[:4]): float(v) for d, v in zip(df["observation_date"], df[col])}
