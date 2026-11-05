"""Scrape every FOMC statement since 2000 into data/statements.parquet.

Incremental: only fetches meetings not already stored (use --full to redo all).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fed_decoder import config
from fed_decoder.data import fomc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    config.DATA_DIR.mkdir(exist_ok=True)
    existing = pd.DataFrame()
    if config.STATEMENTS_PATH.exists() and not args.full:
        existing = pd.read_parquet(config.STATEMENTS_PATH)
    have = set(pd.to_datetime(existing["meeting_date"]).dt.date) if len(existing) else set()
    links = fomc.list_statement_links()
    # The RSS feed lists a statement the moment it's released, sometimes before the calendar page does.
    from fed_decoder.data.feed import statement_links

    known = {l.meeting_date for l in links}
    links += [l for l in statement_links() if l.meeting_date not in known]
    links.sort(key=lambda l: l.meeting_date)
    print(f"found {len(links)} statement links; {len(have)} already stored")
    rows = []
    for link in links:
        if link.meeting_date in have:
            continue
        row = fomc.fetch_statement(link)
        if len(row["statement_text"]) < 200:
            print(f"WARNING short statement {link.meeting_date} {link.url}")
        print(link.meeting_date, len(row["statement_text"]), flush=True)
        rows.append(row)
    df = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True) if rows else existing
    df["meeting_date"] = pd.to_datetime(df["meeting_date"])
    df = df.drop_duplicates("meeting_date").sort_values("meeting_date").reset_index(drop=True)
    df.to_parquet(config.STATEMENTS_PATH, index=False)
    print(f"saved {len(df)} statements -> {config.STATEMENTS_PATH}")


if __name__ == "__main__":
    main()
