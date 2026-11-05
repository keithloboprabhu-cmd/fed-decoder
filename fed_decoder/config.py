"""Central configuration. Model names and limits live here, not in code paths.

Free-tier limits change. Verify them in each console before deploying:
  - Gemini: https://aistudio.google.com  (Rate limits page)
  - Groq:   https://console.groq.com/settings/limits
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CARDS_DIR = ROOT / "cards"
CACHE_DIR = ROOT / ".cache"

STATEMENTS_PATH = DATA_DIR / "statements.parquet"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.parquet"
FRED_PATH = DATA_DIR / "fred.parquet"
FEATURES_PATH = DATA_DIR / "meeting_features.parquet"

FED_BASE = "https://www.federalreserve.gov"
USER_AGENT = "fed-decoder/1.0 (educational project; polite scraper)"
SCRAPE_DELAY_S = 1.0
START_YEAR = 2000


def _secret(name: str) -> str | None:
    """Read a key from the environment, .env, or Streamlit secrets."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        val = os.environ.get(name)
        if val:
            return val
    except Exception:
        pass
    try:
        import streamlit as st

        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:
        return None


# ---- LLM providers (free tiers only; never enable billing) -----------------
# gemini-2.5-flash is closed to new users (Nov 2026); 3.7/3.8-flash were returning 503 "high demand".
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
# Tried in order when a model answers 503 "high demand" (free-tier overload comes and goes).
GEMINI_FALLBACK_MODELS = [m for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-flash-lite-latest").split(",") if m]
GEMINI_TIMEOUT_S = int(os.environ.get("GEMINI_TIMEOUT_S", "60"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
# Ask: Gemma 4 runs on the same free Gemini API key with its own (larger) quota and supports
# function calling; it backs up the Flash models when their 20-requests-per-day cap is hit.
ASK_GEMINI_MODELS = [m for m in os.environ.get("ASK_GEMINI_MODELS", "gemini-3.5-flash,gemini-3.6-flash,gemini-3-flash-preview,gemma-4-26b-a4b-it,gemma-4-31b-it,gemini-3.5-flash-lite,gemini-3.1-flash-lite").split(",") if m]
# Google Search grounding can't share a call with function tools on the free tier, so web_search
# makes its own grounded call. gemma-4-26b-a4b-it supported it when the Flash models were capped (Nov 2026).
SEARCH_MODELS = [m for m in os.environ.get("SEARCH_MODELS", "gemma-4-26b-a4b-it,gemini-3.5-flash,gemini-3.1-flash-lite").split(",") if m]
# gpt-oss-20b's browser_search found the current chair; the 120b returned a stale name (Nov 2026 test).
GROQ_SEARCH_MODEL = os.environ.get("GROQ_SEARCH_MODEL", "openai/gpt-oss-20b")

# Requests per minute we allow ourselves: kept below the published free caps.
GEMINI_RPM = int(os.environ.get("GEMINI_RPM", "8"))
GROQ_RPM = int(os.environ.get("GROQ_RPM", "25"))
# Groq's free tier also caps tokens per minute (8,000 for gpt-oss-120b, Nov 2026);
# one decoder card is ~6,000 tokens, so this is usually the binding limit.
GROQ_TPM = int(os.environ.get("GROQ_TPM", "8000"))
# Longest wait the router will honour on a 429 before falling back.
MAX_BACKOFF_S = float(os.environ.get("MAX_BACKOFF_S", "12"))
# Daily budget we allow the deployed app to spend on live chat (all users).
# Gemini's free tier allows 20 requests/day per model (checked Nov 2026), so
# 5 models give ~100/day; a chat answer takes 2-3 calls. Groq adds more.
DAILY_LLM_BUDGET = int(os.environ.get("DAILY_LLM_BUDGET", "80"))
SESSION_QUESTION_LIMIT = 15
CHAT_HISTORY_TURNS = 6


def gemini_key() -> str | None:
    return _secret("GEMINI_API_KEY")


def groq_key() -> str | None:
    return _secret("GROQ_API_KEY")


def fred_key() -> str | None:
    return _secret("FRED_API_KEY")


# ---- FRED series (each ID verified on first run by scripts/fetch_fred.py) --
FRED_SERIES = {
    "DFEDTARU": "Fed funds target range, upper bound",
    "DFEDTARL": "Fed funds target range, lower bound",
    "DFEDTAR": "Fed funds target rate (pre-Dec 2008)",
    "DFF": "Effective federal funds rate",
    "CPIAUCSL": "CPI, all urban consumers (index)",
    "PCEPILFE": "Core PCE price index",
    "UNRATE": "Unemployment rate",
    "PAYEMS": "Nonfarm payrolls (thousands)",
    "DGS2": "2-year Treasury yield",
    "DGS10": "10-year Treasury yield",
    "MORTGAGE30US": "30-year fixed mortgage rate",
    "TERMCBCCALLNS": "Credit card interest rate (all accounts)",
    "RIFLPBCIANM60NM": "New car loan rate, 60 months (commercial banks)",
    "FEDTARMD": "SEP median projection, fed funds (current year)",
    "GDPPOT": "Real potential GDP",
    "GDPC1": "Real GDP",
    "DTWEXBGS": "Trade-weighted US dollar index (broad)",
    "SP500": "S&P 500 index",
}

# Two-letter codes for FRED's state unemployment series ("{code}UR", e.g. CAUR).
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
STATE_UR_PATH = DATA_DIR / "state_unemployment.parquet"

FOOTER = "Not financial advice. Data: Federal Reserve, FRED. AI: Gemini / Groq free tiers."
PRIVACY_NOTICE = "Don't enter personal information. Questions are sent to free-tier AI providers that may use them to improve their models."
