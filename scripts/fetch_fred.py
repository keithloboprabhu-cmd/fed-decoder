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


def main() -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    df = fred.fetch_all()
    df.to_parquet(config.FRED_PATH, index=False)
    print(f"saved {len(df)} rows -> {config.FRED_PATH}")

    # SEP vintages: one per meeting since the dot plot began (Jan 2012).
    stm = pd.read_parquet(config.STATEMENTS_PATH)
    dates = [d.date() for d in pd.to_datetime(stm["meeting_date"]) if d.year >= 2012]
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
