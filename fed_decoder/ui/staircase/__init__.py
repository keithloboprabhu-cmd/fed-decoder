"""The Rate Staircase: a small custom Streamlit component (plain HTML/SVG/JS, no build).

Hikes are red up-steps, cuts blue down-steps, holds flat gray runs. Click, drag or use
the arrow keys to choose a meeting; presets zoom to well-known periods. Returns
{"date": "YYYY-MM-DD", "n": counter} when the reader commits a selection.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import streamlit.components.v1 as components

_component = components.declare_component("staircase", path=str(Path(__file__).parent))


def presets(today: date) -> list[dict]:
    return [
        {"label": "2000s", "start": "2000-01-01", "end": "2009-12-31"},
        {"label": "2008", "start": "2007-06-01", "end": "2009-12-31"},
        {"label": "2020", "start": "2019-06-01", "end": "2021-12-31"},
        {"label": "2022 hikes", "start": "2021-12-01", "end": "2023-12-31"},
        {"label": "Now", "start": (today - timedelta(days=int(3 * 365.25))).isoformat(), "end": today.isoformat()},
    ]


def staircase(meetings: list[dict], selected: str | None, today: date, key: str = "staircase"):
    """meetings: [{d, lo, hi, c, lab}] sorted by date. Returns the committed selection or None."""
    return _component(meetings=meetings, selected=selected, presets=presets(today), default_preset="Now",
                      today=today.isoformat(), key=key, default=None)
