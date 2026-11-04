"""Derived data: ground truth, tone calibration, forecast backtest.

Run after fetch_statements.py and fetch_fred.py. Pure computation, no API calls.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fed_decoder import config
from fed_decoder.analysis import forecast, tone
from fed_decoder.data import ground_truth, store


def main() -> None:
    stm = pd.read_parquet(config.STATEMENTS_PATH)
    fred = pd.read_parquet(config.FRED_PATH)
    gt = ground_truth.build(stm, fred)
    gt.to_parquet(config.GROUND_TRUTH_PATH, index=False)
    print(f"ground truth: {len(gt)} meetings; moves: {gt['direction'].value_counts().to_dict()}")
    store.ground_truth.cache_clear()
    store.statements.cache_clear()

    # Tone calibration: against LLM card scores if any exist, else corpus z-score.
    raws = [tone.raw_score(t)[0] for t in stm["statement_text"]]
    targets = []
    for d, r in zip(stm["meeting_date"], raws):
        p = config.CARDS_DIR / f"{pd.Timestamp(d).date()}.json"
        if p.exists():
            c = json.loads(p.read_text())
            if c.get("provider") in ("gemini", "groq"):
                targets.append((r, c["tone_score"]))
    if len(targets) >= 10:
        cal = tone.calibrate([a for a, _ in targets], [b for _, b in targets])
    else:
        cal = tone.calibrate(raws)
    print("tone calibration:", cal)

    bt = forecast.backtest()
    print("forecast backtest:", forecast.backtest_summary(bt))


if __name__ == "__main__":
    main()
