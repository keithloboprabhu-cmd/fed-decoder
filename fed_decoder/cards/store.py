"""Load pre-generated decoder cards (cards/YYYY-MM-DD.json). Zero API calls."""
from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from fed_decoder import config
from fed_decoder.cards.schema import Card


def card_path(meeting_date) -> "config.Path":
    return config.CARDS_DIR / f"{pd.Timestamp(meeting_date).date().isoformat()}.json"


@lru_cache(maxsize=512)
def _load(path_str: str, mtime: float) -> Card | None:
    try:
        return Card.model_validate(json.loads(open(path_str).read()))
    except Exception:
        return None


def load_card(meeting_date) -> Card | None:
    p = card_path(meeting_date)
    if not p.exists():
        return None
    return _load(str(p), p.stat().st_mtime)


def save_card(card: Card) -> None:
    config.CARDS_DIR.mkdir(exist_ok=True)
    card_path(card.meeting_date).write_text(card.model_dump_json(indent=2))


def all_cards() -> dict[str, Card]:
    out = {}
    for p in sorted(config.CARDS_DIR.glob("*.json")):
        c = _load(str(p), p.stat().st_mtime)
        if c:
            out[c.meeting_date] = c
    return out
