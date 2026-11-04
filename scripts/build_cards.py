"""Pre-generate a decoder card for every meeting (cards/YYYY-MM-DD.json).

Throttled below the free per-minute limit by the provider rate limiters.
Resumable: meetings that already have a validated LLM card are skipped, so if
the daily cap is hit, just run it again tomorrow.

  python scripts/build_cards.py                 # LLM cards (Gemini -> Groq), rules fallback
  python scripts/build_cards.py --rules-only    # no API calls
  python scripts/build_cards.py --provider groq --limit 20
  python scripts/build_cards.py --since 2024-01-01 --force
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from fed_decoder import config
from fed_decoder.cards.builder import build_llm_card
from fed_decoder.cards.context import build_context
from fed_decoder.cards.rules import build_rules_card
from fed_decoder.cards.store import card_path, load_card, save_card
from fed_decoder.data import store
from fed_decoder.llm import router


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules-only", action="store_true")
    ap.add_argument("--provider", choices=["gemini", "groq"], help="use only this provider")
    ap.add_argument("--limit", type=int, default=0, help="max LLM calls this run")
    ap.add_argument("--since", default=None)
    ap.add_argument("--force", action="store_true", help="rebuild even if an LLM card exists")
    args = ap.parse_args()

    have_keys = any(router.get_provider(p).available() for p in (["gemini", "groq"] if not args.provider else [args.provider]))
    use_llm = have_keys and not args.rules_only
    if not use_llm and not args.rules_only:
        print("No GEMINI_API_KEY / GROQ_API_KEY found: writing rules-based cards only.")
    providers = [args.provider] if args.provider else None

    dates = store.statements()["meeting_date"]
    if args.since:
        dates = dates[dates >= pd.Timestamp(args.since)]
    made = {"llm": 0, "rules": 0, "skipped": 0}
    for d in dates:
        existing = load_card(d)
        if existing and existing.provider in ("gemini", "groq") and existing.validated and not args.force:
            made["skipped"] += 1
            continue
        ctx = build_context(d)
        card = None
        if use_llm and (not args.limit or made["llm"] < args.limit):
            card = build_llm_card(ctx, providers=providers)
            if card is None and router.LAST_FAILURES and all(e == "RateLimited" for _, e in router.LAST_FAILURES):
                print(f"{d.date()}: every provider is rate-limited (daily cap?). Stopping; rerun later to resume.")
                break
        if card is not None:
            made["llm"] += 1
            print(f"{d.date()}: {card.provider} card (tone {card.tone_score:+.1f})", flush=True)
        else:
            if existing is not None and not args.force:
                continue  # keep the existing rules card
            card = build_rules_card(ctx)
            made["rules"] += 1
            if use_llm:
                print(f"{d.date()}: LLM card failed validation or providers unavailable -> rules card", flush=True)
        save_card(card)
    n = len(list(config.CARDS_DIR.glob("*.json")))
    print(f"done: {made}; {n} cards in {config.CARDS_DIR}")


if __name__ == "__main__":
    main()
