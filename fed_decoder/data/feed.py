"""The Federal Reserve's official press-release RSS feeds: the fastest machine-readable
signal that a new FOMC statement is out (verified 2026-11).

  https://www.federalreserve.gov/feeds/press_monetary.xml   monetary policy releases
  https://www.federalreserve.gov/feeds/press_all.xml        everything (fallback)

FOMC statements appear as "Federal Reserve issues FOMC statement" with a link like
/newsevents/pressreleases/monetary20261028a.htm. Unscheduled (emergency) statements use
the same URL pattern, so they are picked up too.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime

import requests

from fed_decoder import config
from fed_decoder.data.fomc import StatementLink

FEEDS = [config.FED_BASE + "/feeds/press_monetary.xml", config.FED_BASE + "/feeds/press_all.xml"]
_STATEMENT_URL = re.compile(r"/pressreleases/monetary(\d{8})a\.htm$")
_TITLE = re.compile(r"\bFOMC statement\b|\bFederal Open Market Committee\b.*\b(statement|announces)\b", re.I)


def statement_links(timeout: int = 20) -> list[StatementLink]:
    """FOMC statement links in the feed, newest first. Empty list if the feed can't be read."""
    for url in FEEDS:
        try:
            r = requests.get(url, timeout=timeout, headers={"User-Agent": config.USER_AGENT})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
        except Exception:
            continue
        return parse(root)
    return []


def parse(root: ET.Element) -> list[StatementLink]:
    out = []
    for it in root.iter("item"):
        link, title = (it.findtext("link") or "").strip(), (it.findtext("title") or "").strip()
        m = _STATEMENT_URL.search(link)
        if m and _TITLE.search(title):
            out.append(StatementLink(datetime.strptime(m.group(1), "%Y%m%d").date(), link))
    return sorted(out, key=lambda l: l.meeting_date, reverse=True)
