"""Scheduled FOMC meetings from the Fed's calendar page (verified 2026-11).
Saved to data/calendar.json; refreshed by the scheduled workflow."""
from __future__ import annotations

import json
import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from fed_decoder import config

URL = config.FED_BASE + "/monetarypolicy/fomccalendars.htm"
PATH = config.DATA_DIR / "calendar.json"
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _statement_day(year: int, month_txt: str, days_txt: str) -> date | None:
    """'December' + '8-9*' -> Dec 9 (statements come on the last day). Handles 'Apr/May' + '30-1'."""
    months = [_MONTHS.get(m.strip()[:3].lower()) for m in month_txt.split("/")]
    days = [int(x) for x in re.findall(r"\d+", days_txt)]
    if not days or not months[-1]:
        return None
    return date(year, months[-1], days[-1])


def fetch_calendar() -> dict:
    soup = BeautifulSoup(requests.get(URL, timeout=30, headers={"User-Agent": config.USER_AGENT}).content, "lxml")
    meetings = []
    for panel in soup.select("div.panel-default"):
        head = panel.find(["h4", "h5"])
        m = re.match(r"(\d{4}) FOMC Meetings", head.get_text(strip=True) if head else "")
        if not m:
            continue
        for row in panel.select(".fomc-meeting"):
            mo, dd = row.select_one(".fomc-meeting__month"), row.select_one(".fomc-meeting__date")
            if not (mo and dd) or "notation" in dd.get_text().lower() or "unscheduled" in dd.get_text().lower():
                continue
            d = _statement_day(int(m.group(1)), mo.get_text(" ", strip=True), dd.get_text(" ", strip=True))
            if d:
                meetings.append({"date": d.isoformat(), "sep": "*" in dd.get_text()})
    if not meetings:
        raise RuntimeError("no meetings parsed; calendar layout may have changed")
    return {"as_of": date.today().isoformat(), "source": URL, "meetings": sorted(meetings, key=lambda x: x["date"])}


def save_calendar() -> dict:
    c = fetch_calendar()
    PATH.write_text(json.dumps(c, indent=1))
    return c


def next_meeting(today: date | None = None) -> dict | None:
    today = today or date.today()
    try:
        c = json.loads(PATH.read_text())
    except Exception:
        return None
    upcoming = [m for m in c["meetings"] if m["date"] >= today.isoformat()]
    return upcoming[0] if upcoming else None
