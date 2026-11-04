"""Download every FRED series in config.FRED_SERIES into data/fred.parquet,
plus SEP median vintages (data/sep_vintages.parquet)."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fed_decoder import config
from fed_decoder.data import fred

SEP_PATH = config.DATA_DIR / "sep_vintages.parquet"


SEP_FIRST = pd.Timestamp("2015-12-01")  # first FEDTARMD vintage on ALFRED


def main() -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    if "--sep-only" not in sys.argv:
        df = fred.fetch_all()
        df.to_parquet(config.FRED_PATH, index=False)
        print(f"saved {len(df)} rows -> {config.FRED_PATH}")
        # State unemployment rates for the personal "For you" panel.
        frames = []
        for code in config.STATES:
            s_ = fred.fetch_series(f"{code}UR", start="2000-01-01")
            frames.append(pd.DataFrame({"date": s_.index, "state": code, "value": s_.values}))
        st = pd.concat(frames, ignore_index=True)
        st.to_parquet(config.STATE_UR_PATH, index=False)
        print(f"saved {len(st)} state unemployment rows -> {config.STATE_UR_PATH}")

    # SEP vintages: one per meeting since FRED began carrying the median.
    stm = pd.read_parquet(config.STATEMENTS_PATH)
    dates = [d.date() for d in pd.to_datetime(stm["meeting_date"]) if d >= SEP_FIRST]
    have = pd.read_parquet(SEP_PATH) if SEP_PATH.exists() else pd.DataFrame(columns=["asof", "year", "median"])
    done = set(pd.to_datetime(have["asof"]).dt.date) if len(have) else set()
    rows = []
    for d in dates:
        asof = d + timedelta(days=1)
        if asof in done:
            continue
        try:
            for yr, v in fred.fetch_sep_vintage(asof).items():
                rows.append({"asof": pd.Timestamp(asof), "year": yr, "median": v})
        except RuntimeError as e:
            print("skip", asof, e)
    out = pd.concat([have, pd.DataFrame(rows)], ignore_index=True)
    out["asof"] = pd.to_datetime(out["asof"])
    out.drop_duplicates(["asof", "year"]).to_parquet(SEP_PATH, index=False)
    print(f"saved {len(out)} SEP vintage rows -> {SEP_PATH}")


if __name__ == "__main__":
    main()
