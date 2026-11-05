"""Live tools for Ask: official sources first, each with a timeout, a TTL cache and an error
the model can read. Every result carries `source` (a URL) and `as_of` so answers can cite
and date current facts. Free endpoints only; keys (FRED, BLS) are optional.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import operator
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from fed_decoder import config

ET_TZ = ZoneInfo("America/New_York")
UA = {"User-Agent": config.USER_AGENT}
CACHE_DIR = config.CACHE_DIR / "live"
STATS = {"hits": 0, "misses": 0, "errors": 0}
_LOCK = threading.Lock()
_MEM: dict[str, tuple[float, dict]] = {}

H = 3600
TTL = {"fed_leadership": 12 * H, "fomc_calendar": 24 * H, "fred_search": H, "fred_series": H, "bls_latest": H,
       "treasury_yields": H, "fed_feed": 15 * 60, "web_search": H, "fetch_page": 6 * H}

# Source priority 1 and 2. fetch_page reads only these.
OFFICIAL = ["federalreserve.gov", "newyorkfed.org", "bostonfed.org", "philadelphiafed.org", "clevelandfed.org", "richmondfed.org",
            "atlantafed.org", "chicagofed.org", "stlouisfed.org", "minneapolisfed.org", "kansascityfed.org", "dallasfed.org",
            "frbsf.org", "bls.gov", "bea.gov", "treasury.gov", "fiscaldata.treasury.gov", "cbo.gov", "congress.gov"]
OUTLETS = ["reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com"]
ALLOWED = OFFICIAL + OUTLETS + ["wikipedia.org"]


def now_et() -> datetime:
    return datetime.now(ET_TZ)


def domain_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in ALLOWED)


def source_rank(url: str) -> int:
    host = (urlparse(url).hostname or "").lower()
    if any(host == d or host.endswith("." + d) for d in OFFICIAL):
        return 1
    if any(host == d or host.endswith("." + d) for d in OUTLETS):
        return 2
    return 3


# ---------------------------------------------------------------- cache
def cached(name: str):
    """TTL cache in memory and on disk. Errors are cached for 2 minutes only."""
    def deco(fn):
        def wrapper(*args, **kwargs):
            key = name + ":" + hashlib.sha1(json.dumps([args, kwargs], sort_keys=True, default=str).encode()).hexdigest()[:16]
            ttl = TTL.get(name, H)
            now = time.time()
            with _LOCK:
                hit = _MEM.get(key)
            if hit is None:
                try:
                    blob = json.loads((CACHE_DIR / f"{key.replace(':', '_')}.json").read_text())
                    hit = (blob["t"], blob["v"])
                except Exception:
                    hit = None
            if hit and now - hit[0] < (ttl if "error" not in hit[1] else 120):
                STATS["hits"] += 1
                return hit[1]
            STATS["misses"] += 1
            try:
                val = fn(*args, **kwargs)
            except requests.Timeout:
                val = {"error": f"{name}: the source timed out; try again or use another tool"}
            except Exception as e:  # noqa: BLE001
                val = {"error": f"{name}: {type(e).__name__}: {str(e)[:200]}"}
            if "error" in val:
                STATS["errors"] += 1
            with _LOCK:
                _MEM[key] = (now, val)
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (CACHE_DIR / f"{key.replace(':', '_')}.json").write_text(json.dumps({"t": now, "v": val}))
            except Exception:
                pass
            return val
        wrapper.__name__ = fn.__name__
        wrapper.__wrapped__ = fn
        return wrapper
    return deco


def _get(url: str, timeout: float = 15, **kw) -> requests.Response:
    r = requests.get(url, timeout=timeout, headers=UA, **kw)
    r.raise_for_status()
    return r


# ---------------------------------------------------------------- Fed leadership
BOARD_URL = config.FED_BASE + "/aboutthefed/bios/board/default.htm"
FOMC_URL = config.FED_BASE + "/monetarypolicy/fomc.htm"


def _pairs(lines: list[str], start: int, stop_words: tuple[str, ...]) -> list[dict]:
    out, i = [], start
    while i < len(lines) - 1 and not lines[i].startswith(stop_words):
        name, rest = lines[i], lines[i + 1]
        if rest.startswith(","):
            parts = [p.strip() for p in rest.strip(", ").split(",")]
            if len(parts) > 1 and "President" in parts[0]:  # "Interim President, Atlanta"
                parts = [parts[-1]] + parts[:-1]
            out.append({"name": name, "affiliation": parts[0], "role": ", ".join(parts[1:]) or None})
            i += 2
        else:
            i += 1
    return out


@cached("fed_leadership")
def fed_leadership() -> dict:
    """Board of Governors and this year's FOMC voters and alternates, from federalreserve.gov."""
    from fed_decoder.data.leadership import fetch_board

    board = fetch_board()["members"]
    soup = BeautifulSoup(_get(FOMC_URL).content.decode("utf-8", "replace"), "lxml")
    main = soup.find(id="article") or soup
    lines = [x for x in main.get_text("\n", strip=True).split("\n") if x]
    voters, alternates, rotation = [], [], {}
    # The first "Members" is a site-menu link; the list is the one followed by "Name" / ", Affiliation".
    starts = [i for i, ln in enumerate(lines[:-2]) if ln.endswith("Members") and lines[i + 2].startswith(",")]
    year = next((m.group(0) for i in starts[:1] for m in [re.match(r"20\d\d", lines[i])] if m), str(date.today().year))
    if starts:
        i = starts[0]
        voters = _pairs(lines, i + 1, ("Alternate Members",))
        if "Alternate Members" in lines:
            alternates = _pairs(lines, lines.index("Alternate Members") + 1, ("Federal Reserve Bank Rotation",))
        if "Federal Reserve Bank Rotation on the FOMC" in lines:
            j = lines.index("Federal Reserve Bank Rotation on the FOMC")
            years = [ln for ln in lines[j:j + 12] if re.fullmatch(r"20\d\d", ln)]
            k = next(n for n in range(j, len(lines)) if lines[n] == "Members")
            banks = []
            for ln in lines[k + 1:]:
                if ln in ("Alternate Members",) or len(banks) >= 5 * len(years):
                    break
                banks.append(ln)
            for n, y in enumerate(years):
                rotation[y] = banks[n * 5:(n + 1) * 5]
    if not voters:
        return {"error": "fed_leadership: could not read the FOMC members list (page layout changed?)", "board": board,
                "source": BOARD_URL}
    chair = next((m["name"] for m in board if "Chair" in m["title"] and "Vice" not in m["title"]), None)
    return {
        "as_of": date.today().isoformat(),
        "chair": chair,
        "board_of_governors": [{"name": m["name"], "title": m["title"]} for m in board],
        "fomc_voters_year": year,
        "fomc_voters_this_year": voters,
        "fomc_alternates": alternates,
        "voting_banks_by_year": rotation,
        "note": "Governors serve 14-year terms; the chair and vice chairs serve 4-year terms as officers. "
                "Bank presidents rotate onto the FOMC at the first meeting of each year; New York always votes.",
        "sources": [BOARD_URL, FOMC_URL],
        "source": FOMC_URL,
    }


# ---------------------------------------------------------------- calendar
@cached("fomc_calendar")
def fomc_calendar() -> dict:
    from fed_decoder.data.calendar import fetch_calendar

    cal = fetch_calendar()
    today = date.today()
    ms = cal["meetings"]
    past = [m for m in ms if m["date"] < today.isoformat()][-4:]
    upcoming = [m for m in ms if m["date"] >= today.isoformat()][:6]
    return {"as_of": today.isoformat(), "today": today.isoformat(), "recent": past, "upcoming": upcoming,
            "note": "Dates are the statement day (the last day of each meeting). sep=true: a Summary of Economic Projections (dot plot) is released.",
            "source": cal.get("source")}


# ---------------------------------------------------------------- FRED
FRED_API = "https://api.stlouisfed.org/fred"
# Used for search when there is no FRED key, and to steer the model to the right IDs.
CATALOG = {**config.FRED_SERIES, **{
    "CPILFESL": "Core CPI (excluding food and energy), index", "PCEPI": "PCE price index", "PAYEMS": "Nonfarm payrolls (thousands)",
    "ICSA": "Initial jobless claims (weekly)", "JTSJOL": "Job openings (JOLTS)", "CES0500000003": "Average hourly earnings",
    "CIVPART": "Labor force participation rate", "U6RATE": "U-6 unemployment rate", "T10Y2Y": "10-year minus 2-year Treasury spread",
    "DGS3MO": "3-month Treasury yield", "DGS30": "30-year Treasury yield", "MORTGAGE15US": "15-year fixed mortgage rate",
    "DPRIME": "Bank prime loan rate", "IORB": "Interest rate on reserve balances", "RRPONTSYAWARD": "Overnight reverse repo award rate",
    "SOFR": "Secured Overnight Financing Rate", "WALCL": "Fed balance sheet: total assets (millions)", "RRPONTSYD": "Overnight reverse repo volume",
    "T5YIE": "5-year breakeven inflation", "T10YIE": "10-year breakeven inflation", "MICH": "Michigan inflation expectations (1 year)",
    "UMCSENT": "Michigan consumer sentiment", "RSAFS": "Retail sales", "INDPRO": "Industrial production", "HOUST": "Housing starts",
    "CSUSHPINSA": "Case-Shiller home price index", "A191RL1Q225SBEA": "Real GDP growth, annualized quarterly %",
    "PSAVERT": "Personal saving rate", "TOTALSL": "Consumer credit outstanding", "DRCCLACBS": "Credit card delinquency rate",
    "BAMLH0A0HYM2": "High-yield corporate bond spread", "VIXCLS": "VIX volatility index", "DEXUSEU": "Dollar per euro",
    "GFDEBTN": "Federal debt, total public", "FYFSD": "Federal surplus or deficit",
}}


def _fred_key() -> str | None:
    return config.fred_key()


@cached("fred_search")
def fred_search(query: str, limit: int = 8) -> dict:
    q = (query or "").strip()
    if not q:
        return {"error": "fred_search: empty query"}
    key = _fred_key()
    if key:
        j = _get(f"{FRED_API}/series/search", params={"search_text": q, "api_key": key, "file_type": "json", "limit": limit,
                                                       "order_by": "popularity", "sort_order": "desc"}).json()
        res = [{"id": s["id"], "title": s["title"], "units": s.get("units_short"), "frequency": s.get("frequency_short"),
                "last_updated": s.get("last_updated", "")[:10]} for s in j.get("seriess", [])]
        return {"results": res, "source": "https://fred.stlouisfed.org/searchresults/?st=" + quote(q)}
    words = [w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) > 2]
    scored = sorted(((sum(w in (k + " " + v).lower() for w in words), k, v) for k, v in CATALOG.items()), reverse=True)
    res = [{"id": k, "title": v} for s, k, v in scored if s > 0][:limit]
    return {"results": res, "note": "Searched a built-in list of common series (no FRED API key configured). "
            "fred_series also accepts any other valid FRED ID.", "source": "https://fred.stlouisfed.org/"}


@cached("fred_series")
def fred_series(id: str, start: str | None = None, end: str | None = None) -> dict:  # noqa: A002
    sid = re.sub(r"[^A-Za-z0-9_]", "", id or "").upper()
    if not sid:
        return {"error": "fred_series: give a FRED series ID (use fred_search to find one)"}
    start = start or (date.today() - timedelta(days=3 * 365)).isoformat()
    key = _fred_key()
    obs: list[tuple[str, float]] = []
    title = CATALOG.get(sid)
    units = None
    if key:
        j = _get(f"{FRED_API}/series/observations", params={"series_id": sid, "api_key": key, "file_type": "json",
                                                            "observation_start": start, **({"observation_end": end} if end else {})}).json()
        if "error_message" in j:
            return {"error": f"fred_series: {j['error_message']}"}
        obs = [(o["date"], float(o["value"])) for o in j.get("observations", []) if o["value"] not in (".", "")]
        try:
            meta = _get(f"{FRED_API}/series", params={"series_id": sid, "api_key": key, "file_type": "json"}).json()["seriess"][0]
            title, units = meta["title"], meta.get("units")
        except Exception:
            pass
    else:
        try:
            r = _get("https://fred.stlouisfed.org/graph/fredgraph.csv", timeout=20,
                     params={"id": sid, "cosd": start, **({"coed": end} if end else {})})
            for line in r.text.splitlines()[1:]:
                d, _, v = line.partition(",")
                if v not in (".", ""):
                    obs.append((d, float(v)))
        except Exception:
            from fed_decoder.data import store  # offline copy for the core series

            if sid in config.FRED_SERIES:
                s = store.get_series(sid, start, end)
                obs = [(str(i.date()), float(v)) for i, v in s.items()]
    if not obs:
        return {"error": f"fred_series: no data for {sid} in that window (check the ID with fred_search)"}
    pts = obs if len(obs) <= 36 else [obs[i] for i in range(0, len(obs), max(1, len(obs) // 30))] + [obs[-1]]
    last_d, last_v = obs[-1]
    out = {"id": sid, "title": title, "units": units, "as_of": last_d, "latest": {"date": last_d, "value": last_v},
           "first": {"date": obs[0][0], "value": obs[0][1]}, "points": [{"date": d, "value": v} for d, v in pts],
           "source": f"https://fred.stlouisfed.org/series/{sid}"}
    # Year-over-year change for monthly index series (CPI, PCE), computed here so the model never does math.
    if len(obs) > 13 and re.search(r"CPI|PCEPI|PCEPILFE|CPILFESL", sid):
        try:
            d0 = datetime.fromisoformat(last_d)
            prior = next(v for d, v in reversed(obs) if datetime.fromisoformat(d) <= d0.replace(year=d0.year - 1))
            out["yoy_pct"] = round((last_v / prior - 1) * 100, 1)
        except StopIteration:
            pass
    return out


# ---------------------------------------------------------------- BLS
BLS_SERIES = {"cpi": ("CUUR0000SA0", "CPI-U, all items (index, not seasonally adjusted)"),
              "core_cpi": ("CUUR0000SA0L1E", "CPI-U less food and energy (index)"),
              "unemployment": ("LNS14000000", "Unemployment rate, %"),
              "payrolls": ("CES0000000001", "Total nonfarm payrolls, thousands"),
              "wages": ("CES0500000003", "Average hourly earnings, $")}
BLS_FRED = {"cpi": "CPIAUCSL", "core_cpi": "CPILFESL", "unemployment": "UNRATE", "payrolls": "PAYEMS", "wages": "CES0500000003"}


@cached("bls_latest")
def bls_latest(series: str) -> dict:
    key = (series or "").lower().strip().replace(" ", "_")
    key = {"inflation": "cpi", "jobs": "payrolls", "unemployment_rate": "unemployment", "core": "core_cpi"}.get(key, key)
    if key not in BLS_SERIES:
        return {"error": f"bls_latest: series must be one of {sorted(BLS_SERIES)}"}
    sid, title = BLS_SERIES[key]
    body = {"seriesid": [sid], "startyear": str(date.today().year - 1), "endyear": str(date.today().year)}
    bkey = config._secret("BLS_API_KEY")
    if bkey:
        body["registrationkey"] = bkey
    try:
        j = requests.post("https://api.bls.gov/publicAPI/v2/timeseries/data/", json=body, timeout=15, headers=UA).json()
        data = j["Results"]["series"][0]["data"] if j.get("status") == "REQUEST_SUCCEEDED" else []
    except Exception:
        data = []
    if data:
        rows = [(f"{d['year']}-{d['period'][1:]}", float(d["value"])) for d in data if d["period"].startswith("M") and d["period"] != "M13"]
        rows.sort()
        out = {"series": key, "id": sid, "title": title, "as_of": rows[-1][0], "latest": {"month": rows[-1][0], "value": rows[-1][1]},
               "source": f"https://data.bls.gov/timeseries/{sid}"}
        if key in ("cpi", "core_cpi") and len(rows) >= 13:
            prior = dict(rows).get(f"{int(rows[-1][0][:4]) - 1}{rows[-1][0][4:]}")
            if prior:
                out["yoy_pct"] = round((rows[-1][1] / prior - 1) * 100, 1)
        if key == "payrolls" and len(rows) >= 2:
            out["monthly_change_thousands"] = round(rows[-1][1] - rows[-2][1])
        return out
    # BLS's keyless daily limit is shared; FRED republishes the same series the same morning.
    f = fred_series.__wrapped__(BLS_FRED[key], (date.today() - timedelta(days=430)).isoformat())
    if "error" in f:
        return {"error": "bls_latest: BLS unavailable (daily limit) and FRED fallback failed"}
    f["note"] = "BLS API unavailable (keyless daily limit); same series via FRED."
    f["series"] = key
    if key == "payrolls" and len(f["points"]) >= 2:
        f["monthly_change_thousands"] = round(f["points"][-1]["value"] - f["points"][-2]["value"])
    return f


# ---------------------------------------------------------------- Treasury
@cached("treasury_yields")
def treasury_yields(on: str | None = None) -> dict:
    d = date.fromisoformat(on) if on else date.today()
    rows = []
    for back in range(0, 3):  # this month, or the previous ones early in a month
        m = (d.replace(day=1) - timedelta(days=back * 28)).strftime("%Y%m")
        r = _get("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml",
                 params={"data": "daily_treasury_yield_curve", "field_tdr_date_value_month": m}, timeout=20)
        for e in ET.fromstring(r.content).iter():
            if e.tag.endswith("properties"):
                rows.append({c.tag.split("}")[1]: c.text for c in e})
        rows = [x for x in rows if x.get("NEW_DATE", "")[:10] <= d.isoformat()]
        if rows:
            break
    if not rows:
        return {"error": "treasury_yields: no yield curve data for that date"}
    row = max(rows, key=lambda x: x["NEW_DATE"])
    labels = {"BC_1MONTH": "1-month", "BC_3MONTH": "3-month", "BC_6MONTH": "6-month", "BC_1YEAR": "1-year", "BC_2YEAR": "2-year",
              "BC_5YEAR": "5-year", "BC_10YEAR": "10-year", "BC_20YEAR": "20-year", "BC_30YEAR": "30-year"}
    curve = {lab: float(row[k]) for k, lab in labels.items() if row.get(k)}
    out = {"as_of": row["NEW_DATE"][:10], "yields_pct": curve,
           "source": "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve"}
    if "10-year" in curve and "2-year" in curve:
        out["spread_10y_minus_2y_pct"] = round(curve["10-year"] - curve["2-year"], 2)
    return out


# ---------------------------------------------------------------- Fed feeds
FEEDS = {"monetary": "press_monetary", "speeches": "speeches", "testimony": "testimony", "all": "press_all"}


@cached("fed_feed")
def fed_feed(kind: str = "monetary", limit: int = 8) -> dict:
    k = FEEDS.get((kind or "monetary").lower(), None)
    if not k:
        return {"error": f"fed_feed: kind must be one of {sorted(FEEDS)}"}
    url = f"{config.FED_BASE}/feeds/{k}.xml"
    items = []
    for it in ET.fromstring(_get(url).content).find("channel").findall("item")[: max(1, min(limit, 15))]:
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(ET_TZ).date().isoformat()
        except Exception:
            when = None
        items.append({"title": unescape(it.findtext("title") or ""), "date": when, "link": it.findtext("link"),
                      "summary": re.sub(r"<[^>]+>", "", unescape(it.findtext("description") or ""))[:240]})
    return {"as_of": date.today().isoformat(), "items": items, "source": url}


# ---------------------------------------------------------------- web search
def _gemini_search(q: str) -> dict | None:
    key = config.gemini_key()
    if not key:
        return None
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=15_000, retry_options=types.HttpRetryOptions(attempts=1)))
    prompt = (f"Today is {now_et():%B %d, %Y}. Search the web and answer briefly and factually, with dates: {q}\n"
              "Prefer official sources (federalreserve.gov, regional Fed banks, BLS, BEA, Treasury), then Reuters, AP, Bloomberg, WSJ, FT.")
    t0 = time.time()
    for model in config.SEARCH_MODELS:
        if time.time() - t0 > 18:
            break
        try:
            r = client.models.generate_content(model=model, contents=prompt,
                                               config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
        except Exception:
            continue
        gm = r.candidates[0].grounding_metadata if r.candidates else None
        srcs = [{"title": c.web.title, "url": c.web.uri} for c in ((gm and gm.grounding_chunks) or []) if getattr(c, "web", None)]
        if r.text and srcs:
            return {"answer": r.text.strip()[:1500], "results": srcs[:6], "engine": f"Google Search via {model}"}
    return None


def _groq_search(q: str) -> dict | None:
    key = config.groq_key()
    if not key:
        return None
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=20, headers={"Authorization": "Bearer " + key},
                      json={"model": config.GROQ_SEARCH_MODEL, "reasoning_effort": "low", "max_completion_tokens": 900,
                            "tools": [{"type": "browser_search"}], "tool_choice": "required",
                            "messages": [{"role": "user", "content": f"Today is {now_et():%B %d, %Y}. Search the web and answer briefly, "
                                          f"with dates and source URLs, preferring official sources: {q}"}]})
    if r.status_code != 200:
        return None
    msg = r.json()["choices"][0]["message"]
    text = re.sub(r"【[^】]*】", "", msg.get("content") or "").strip()
    urls = []
    for t in msg.get("executed_tools") or []:
        for m in re.finditer(r"https?://[^\s\)\]\"'>]+", json.dumps(t.get("output") or "")):
            u = m.group(0).rstrip(".,\\")
            if u not in urls:
                urls.append(u)
    urls = sorted(urls, key=source_rank)[:6]
    if not text:
        return None
    return {"answer": text[:1500], "results": [{"title": urlparse(u).hostname, "url": u} for u in urls], "engine": "Groq browser search"}


def _wikipedia(q: str) -> dict | None:
    j = _get("https://en.wikipedia.org/w/api.php", params={"action": "opensearch", "search": q, "limit": 3, "format": "json"}, timeout=10).json()
    titles = j[1] if len(j) > 1 else []
    for t in titles:
        s = _get("https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(t.replace(" ", "_")), timeout=10).json()
        if s.get("extract"):
            return {"answer": s["extract"][:1200], "results": [{"title": s.get("title"), "url": s.get("content_urls", {}).get("desktop", {}).get("page")}],
                    "engine": "Wikipedia (background only)"}
    return None


@cached("web_search")
def web_search(query: str) -> dict:
    q = (query or "").strip()[:300]
    if not q:
        return {"error": "web_search: empty query"}
    tried = []
    for name, fn in (("google", _gemini_search), ("groq", _groq_search), ("wikipedia", _wikipedia)):
        try:
            res = fn(q)
        except Exception as e:  # noqa: BLE001
            tried.append(f"{name}: {type(e).__name__}")
            continue
        if res:
            res["as_of"] = date.today().isoformat()
            res["source"] = (res["results"][0]["url"] if res.get("results") else None)
            res["note"] = "Search summaries can be stale or wrong. For leadership, rates and data, prefer the official tools."
            return res
        tried.append(f"{name}: no result")
    return {"error": "web_search: no search engine available right now (" + "; ".join(tried) + ")"}


# ---------------------------------------------------------------- fetch_page
@cached("fetch_page")
def fetch_page(url: str, max_chars: int = 6000) -> dict:
    if not url.startswith(("https://", "http://")) or not domain_ok(url):
        return {"error": "fetch_page: that domain is not on the allowlist (official sources, major outlets, Wikipedia)"}
    r = _get(url, timeout=20)
    soup = BeautifulSoup(r.content, "lxml")  # let the parser read the charset (pages carry a BOM)
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    main = soup.find(id="article") or soup.find("main") or soup.find("article") or soup.body or soup
    text = re.sub(r"\n{3,}", "\n\n", main.get_text("\n", strip=True))
    title = (soup.title.get_text(strip=True) if soup.title else url)[:150]
    return {"title": title, "text": text[: max(500, min(max_chars, 12000))], "truncated": len(text) > max_chars,
            "as_of": date.today().isoformat(), "source": url}


# ---------------------------------------------------------------- calc
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow,
        ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "log": math.log, "exp": math.exp}


def calc(expr: str) -> dict:
    """Safe arithmetic: numbers, + - * / ** %, parentheses, round/abs/min/max/sqrt/log/exp."""
    src = (expr or "").replace("^", "**").replace(",", "")[:200]

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("only arithmetic is allowed")

    try:
        val = ev(ast.parse(src, mode="eval"))
    except Exception as e:  # noqa: BLE001
        return {"error": f"calc: {e}"}
    if isinstance(val, float):
        val = round(val, 6)
    return {"expr": src, "result": val}
