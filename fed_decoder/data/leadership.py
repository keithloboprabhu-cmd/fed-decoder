"""Who runs the Fed, from the Board of Governors page (verified 2026-11):
https://www.federalreserve.gov/aboutthefed/bios/board/default.htm

FOMC statements stopped listing voters in June 2026, so the chair can't be read from
statements any more; this page is the authoritative source. Saved to data/board.json and
refreshed by the scheduled workflow.
"""
from __future__ import annotations

import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from fed_decoder import config

URL = config.FED_BASE + "/aboutthefed/bios/board/default.htm"
PATH = config.DATA_DIR / "board.json"


def fetch_board() -> dict:
    r = requests.get(URL, timeout=30, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    soup = BeautifulSoup(r.content.decode("utf-8", errors="replace"), "lxml")
    members, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/aboutthefed/bios/board/([a-z\-]+)\.htm$", a["href"])
        if not m or m.group(1) in ("default", "boardmembership"):
            continue
        text = a.get_text(" ", strip=True)
        name, _, title = text.partition(", ")
        if name and name not in seen:
            seen.add(name)
            members.append({"name": name, "title": title or "Governor", "bio": config.FED_BASE + a["href"]})
    if not members:
        raise RuntimeError("no board members found; page layout may have changed")
    return {"as_of": date.today().isoformat(), "source": URL, "members": members}


def load_board() -> dict | None:
    try:
        return json.loads(PATH.read_text())
    except Exception:
        return None


def save_board() -> dict:
    b = fetch_board()
    PATH.write_text(json.dumps(b, indent=1))
    return b
