"""Is there an FOMC statement in the Fed's RSS feed that we haven't stored yet?

Prints the new dates and, under GitHub Actions, writes `new=true|false` to $GITHUB_OUTPUT
so the workflow only runs the full update when something changed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fed_decoder import config
from fed_decoder.data.feed import statement_links


def main() -> None:
    have = set(pd.to_datetime(pd.read_parquet(config.STATEMENTS_PATH)["meeting_date"]).dt.date)
    new = [l for l in statement_links() if l.meeting_date not in have]
    for l in new:
        print(f"new statement: {l.meeting_date} {l.url}")
    if not new:
        print("no new statements in the feed")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"new={'true' if new else 'false'}\n")


if __name__ == "__main__":
    main()
