#!/usr/bin/env python3
"""
fetch_driving_pages.py
======================
Fetches specific gov.uk driving penalty / enforcement pages that are missing
from the scraped corpus and writes them to data/raw/driving/ as JSON files
matching the scraper's output format.

Pages targeted (all missing from the current index):
  - /speeding-penalties
  - /driving-without-insurance
  - /totting-up-driving-disqualification
  - /new-drivers-and-penalty-points
  - /penalty-points-endorsements  (existing page is too short; fetch sub-pages)

Usage
-----
  python fetch_driving_pages.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
RAW_DRIVING = ROOT / "data" / "raw" / "housing"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; UKLegalResearchBot/1.0; "
        "+https://example.com/bot)"
    )
}

TARGETS = [
    "https://www.gov.uk/council-tax/full-time-students",
    "https://www.gov.uk/council-tax/who-has-to-pay",
]

# gov.uk content selectors (same as main scraper)
CONTENT_SELECTORS = [
    "main#content",
    "div.govuk-grid-column-two-thirds",
    "article",
    "div#content",
    "main",
]

STRIP_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".gem-c-breadcrumbs", ".govuk-breadcrumbs",
    ".gem-c-related-navigation", ".related-navigation",
    ".gem-c-feedback", ".gem-c-print-link",
    ".govuk-cookie-banner", ".gem-c-skip-link",
    ".app-c-contents-list",
    "script", "style",
]


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for sel in STRIP_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    for content_sel in CONTENT_SELECTORS:
        el = soup.select_one(content_sel)
        if el:
            return el.get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)


def _slug(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def fetch_and_save(url: str, out_dir: Path) -> None:
    slug = _slug(url)
    # Find next available number
    existing = sorted(out_dir.glob("*.json"))
    nums = []
    for f in existing:
        try:
            nums.append(int(f.name.split("_")[0]))
        except ValueError:
            pass
    next_num = (max(nums) + 1) if nums else 100

    out_path = out_dir / f"{next_num:03d}_{slug}.json"
    if out_path.exists():
        print(f"  SKIP (exists): {out_path.name}")
        return

    print(f"  Fetching: {url}", end=" ... ", flush=True)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        print(f"FAILED ({exc})")
        return

    # Extract title
    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else slug.replace("-", " ").title()

    content = _extract_text(resp.text)
    word_count = len(content.split())

    doc = {
        "title": title,
        "url": url,
        "category": "housing",
        "content": content,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "last_modified": "",
        "word_count": word_count,
    }

    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK ({word_count} words) -> {out_path.name}")


def main() -> None:
    RAW_DRIVING.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(TARGETS)} driving penalty pages into {RAW_DRIVING}\n")

    for url in TARGETS:
        fetch_and_save(url, RAW_DRIVING)
        time.sleep(2.0)   # polite delay

    print("\nDone. Run `python run_indexer.py` to rebuild the index.")


if __name__ == "__main__":
    main()
