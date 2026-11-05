"""Snapshot the official pages the Ask primer (knowledge/primer.md) is written from.

Saves each page's main text to knowledge/sources/<slug>.txt and a manifest with a hash per
page. The monthly workflow runs this; when a hash changes it opens a pull request so a person
(or the model, with review) can re-verify the matching primer section.

    python scripts/build_primer.py            # fetch and update the snapshot
    python scripts/build_primer.py --check    # exit 1 if any source changed or the primer breaks a rule
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

from fed_decoder import config  # noqa: E402

KNOW = ROOT / "knowledge"
SRC = KNOW / "sources"
MANIFEST = KNOW / "sources.json"
PRIMER = KNOW / "primer.md"

# slug -> URL. Official pages (federalreserve.gov, regional Fed banks, the Fed's own history site).
SOURCES = {
    "who-we-are": "https://www.federalreserve.gov/aboutthefed/fedexplained/who-we-are.htm",
    "fed-act": "https://www.federalreservehistory.org/essays/federal-reserve-act-signed",
    "purpose-faq": "https://www.federalreserve.gov/faqs/about_12594.htm",
    "goals-faq": "https://www.federalreserve.gov/faqs/what-economic-goals-does-federal-reserve-seek-to-achieve-through-monetary-policy.htm",
    "two-percent-faq": "https://www.federalreserve.gov/faqs/economy_14400.htm",
    "legal-framework-faq": "https://www.federalreserve.gov/faqs/basic-framework-determines-conduct-monetary-policy.htm",
    "independence-faq": "https://www.federalreserve.gov/faqs/about_12799.htm",
    "fomc-faq": "https://www.federalreserve.gov/faqs/about_12844.htm",
    "bank-president-faq": "https://www.federalreserve.gov/faqs/how-is-a-federal-reserve-bank-president-selected.htm",
    "how-policy-works": "https://www.federalreserve.gov/monetarypolicy/monetary-policy-what-are-its-goals-how-does-it-work.htm",
    "policy-tools": "https://www.federalreserve.gov/monetarypolicy/policytools.htm",
    "iorb": "https://www.federalreserve.gov/monetarypolicy/reserve-balances.htm",
    "on-rrp": "https://www.federalreserve.gov/monetarypolicy/overnight-reverse-repurchase-agreements.htm",
    "omo": "https://www.federalreserve.gov/monetarypolicy/openmarket.htm",
    "discount-window": "https://www.federalreserve.gov/monetarypolicy/discountrate.htm",
    "balance-sheet": "https://www.federalreserve.gov/monetarypolicy/bst.htm",
    "rates-matter-faq": "https://www.federalreserve.gov/faqs/why-do-interest-rates-matter.htm",
    "prime-rate-faq": "https://www.federalreserve.gov/faqs/credit_12846.htm",
    "sep-faq": "https://www.federalreserve.gov/faqs/summary-economic-projections-sep.htm",
    "minutes-faq": "https://www.federalreserve.gov/faqs/minutes-federal-open-market-committee-fomc.htm",
    "longer-run-goals-faq": "https://www.federalreserve.gov/faqs/statement-on-longer-run-goals-monetary-policy-strategy-FOMC.htm",
    "great-inflation": "https://www.federalreservehistory.org/essays/great-inflation",
    "great-recession": "https://www.federalreservehistory.org/essays/great-recession-and-its-aftermath",
    "statement-2020-03-15": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20200315a.htm",
    "statement-2022-03-16": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20220316a.htm",
    "statement-2023-07-26": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20230726a.htm",
}

# The primer must never carry current people or current rates (those come from tools).
FORBIDDEN = [r"\b(current|currently|today|now|this year)\b.*\b(chair|governor|president|rate|percent)\b",
             r"\b(Warsh|Powell|Jefferson|Bowman|Barr|Cook|Waller|Williams|Hammack|Kashkari|Logan|Paulson)\b"]
ALLOWED_PEOPLE = {"Volcker", "Bernanke", "Greenspan", "Yellen", "Burns", "Wilson"}  # historical figures only


def page_text(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": config.USER_AGENT})
    r.raise_for_status()
    soup = BeautifulSoup(r.content, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        t.decompose()
    main = soup.find(id="article") or soup.find("main") or soup.find("article") or soup.body
    text = main.get_text("\n", strip=True)
    return re.sub(r"\n{2,}", "\n", text)


def primer_problems() -> list[str]:
    if not PRIMER.exists():
        return ["knowledge/primer.md is missing"]
    body = PRIMER.read_text()
    probs = []
    for line in body.splitlines():
        if line.startswith(("Source", "> Source", "_Sources")):
            continue
        for pat in FORBIDDEN:
            m = re.search(pat, line, re.I)
            if m:
                probs.append(f"current-fact wording not allowed in the primer: {line.strip()[:100]!r}")
    sections = re.split(r"\n## ", body)[1:]
    for s in sections:
        if "Sources:" not in s:
            probs.append(f"section without a citation: {s.splitlines()[0]!r}")
    words = len(re.findall(r"\b\w+\b", body))
    if not 1100 <= words <= 2000:
        probs.append(f"primer is {words} words; keep it near 1,500")
    return probs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report changes and rule breaks without writing")
    args = ap.parse_args()
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    new, changed, failed = {}, [], []
    SRC.mkdir(parents=True, exist_ok=True)
    for slug, url in SOURCES.items():
        try:
            text = page_text(url)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{slug}: {type(e).__name__}")
            if slug in old:
                new[slug] = old[slug]
            continue
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        prev = old.get(slug, {})
        new[slug] = {"url": url, "sha": h, "chars": len(text),
                     "fetched": prev.get("fetched") if prev.get("sha") == h else date.today().isoformat()}
        if prev.get("sha") != h:
            changed.append(slug)
        if not args.check:
            (SRC / f"{slug}.txt").write_text(f"{url}\n\n{text}\n")
    if not args.check:
        MANIFEST.write_text(json.dumps(new, indent=1) + "\n")
    probs = primer_problems()
    print(f"changed: {changed or 'none'}")
    print(f"failed: {failed or 'none'}")
    print(f"primer: {'ok' if not probs else probs}")
    return 1 if (args.check and (changed or probs)) or probs else 0


if __name__ == "__main__":
    raise SystemExit(main())
