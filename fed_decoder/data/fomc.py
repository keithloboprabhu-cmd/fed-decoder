"""Scrape FOMC statements from federalreserve.gov.

Sources (verified 2026-11):
  - /monetarypolicy/fomccalendars.htm      : the last ~5 years plus next year
  - /monetarypolicy/fomchistorical{YYYY}.htm : older years
Statement URL formats seen across eras:
  /boarddocs/press/general/2000/20000202/
  /boarddocs/press/monetary/2004/20040128/default.htm
  /newsevents/press/monetary/20080130a.htm         (redirects)
  /newsevents/pressreleases/monetary20200129a.htm
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from fed_decoder import config

_SESSION = requests.Session()
_SESSION.headers["User-Agent"] = config.USER_AGENT

DATE_RE = re.compile(r"(\d{8})")

BOILERPLATE = re.compile(
    r"^(release date:|for immediate release|for release at|share$|home$|\||accessibility|"
    r"last update|news and events|\d{4} monetary policy|federal reserve issues fomc statement|"
    r"back to top|implementation note|related information|board of governors)",
    re.I,
)
STOP = re.compile(r"^(for media inquiries|implementation note issued|attachment|related information)", re.I)


@dataclass
class StatementLink:
    meeting_date: date
    url: str


def _get(url: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, timeout=30)
            if r.status_code == 200:
                time.sleep(config.SCRAPE_DELAY_S)
                return r.content.decode("utf-8", errors="replace")
        except requests.RequestException:
            pass
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}")


def _abs(href: str) -> str:
    return href if href.startswith("http") else config.FED_BASE + href


def _date_from_url(url: str) -> date | None:
    m = DATE_RE.search(url)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def links_from_page(html: str) -> list[StatementLink]:
    """Find statement links. Historical pages label them "Statement";
    the current calendar page uses "HTML" inside a "Statement:" line."""
    soup = BeautifulSoup(html, "lxml")
    out: dict[date, StatementLink] = {}
    for a in soup.find_all("a", href=True):
        href, text = a["href"], a.get_text(" ", strip=True)
        parent_text = a.parent.get_text(" ", strip=True) if a.parent else ""
        is_hist = text.lower() == "statement"
        is_cal = text == "HTML" and parent_text.startswith("Statement") and re.search(r"monetary\d{8}a\.htm", href)
        if not (is_hist or is_cal):
            continue
        if href.lower().endswith(".pdf"):
            continue
        d = _date_from_url(href)
        if d is None or d.year < config.START_YEAR:
            continue
        # Keep the first link per date (the policy statement precedes others).
        out.setdefault(d, StatementLink(d, _abs(href)))
    return list(out.values())


def list_statement_links(today: date | None = None) -> list[StatementLink]:
    today = today or date.today()
    links: dict[date, StatementLink] = {}
    cal = _get(config.FED_BASE + "/monetarypolicy/fomccalendars.htm")
    for link in links_from_page(cal):
        links.setdefault(link.meeting_date, link)
    min_cal_year = min((d.year for d in links), default=today.year)
    for year in range(config.START_YEAR, min_cal_year):
        html = _get(f"{config.FED_BASE}/monetarypolicy/fomchistorical{year}.htm")
        for link in links_from_page(html):
            links.setdefault(link.meeting_date, link)
    return sorted((l for l in links.values() if l.meeting_date <= today), key=lambda l: l.meeting_date)


def extract_statement_text(html: str) -> str:
    """Pull the statement body as clean paragraphs separated by blank lines."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        t.decompose()
    root = soup.select_one("#article") or soup.select_one("#content") or soup.body or soup
    blocks = root.find_all(["p", "td", "li"]) or [root]
    paras: list[str] = []
    seen: set[str] = set()
    for b in blocks:
        # skip containers whose text is duplicated by nested <p>
        if b.name != "p" and b.find("p"):
            continue
        txt = b.get_text(" ", strip=True).replace("\u00a0", " ").replace("\u2009", " ")
        txt = re.sub(r"\s+", " ", txt).strip()
        txt = txt.replace(" ,", ",").replace(" .", ".").replace(" ;", ";")
        if not txt or txt in seen:
            continue
        if STOP.match(txt):
            break
        if BOILERPLATE.match(txt) or len(txt) < 25:
            continue
        seen.add(txt)
        paras.append(txt)
    if not paras:  # very old pages: plain text body
        raw = root.get_text("\n", strip=True)
        paras = [l for l in raw.split("\n") if len(l) > 40 and not BOILERPLATE.match(l)]
    return "\n\n".join(paras)


def fetch_statement(link: StatementLink) -> dict:
    html = _get(link.url)
    return {
        "meeting_date": link.meeting_date,
        "statement_text": extract_statement_text(html),
        "url": link.url,
    }
