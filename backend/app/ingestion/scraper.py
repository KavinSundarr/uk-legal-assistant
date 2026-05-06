"""
UK Legal Assistant — document scraper.

Crawls gov.uk, citizensadvice.org.uk, nhs.uk, acas.org.uk, and
shelter.org.uk using a two-level BFS per domain source.

Each category can have multiple domain sources.  Robots.txt is
checked per domain (cached).  A polite 2–3 s random delay is
inserted between every request.  Transient network failures are
retried up to 3 times with exponential back-off via tenacity.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings


# ---------------------------------------------------------------------------
# Source catalogue  —  each category is a list of per-domain source configs
# ---------------------------------------------------------------------------

SCRAPE_SOURCES: Dict[str, List[Dict]] = {

    "immigration": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/visas-immigration",
                "https://www.gov.uk/skilled-worker-visa",
                "https://www.gov.uk/indefinite-leave-to-remain",
                "https://www.gov.uk/british-citizenship",
                "https://www.gov.uk/biometric-residence-permits",
                "https://www.gov.uk/graduate-visa",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 50,
        },
    ],

    "student": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/visas-immigration/student-visas",
                "https://www.gov.uk/browse/education/university-and-further-education",
                "https://www.gov.uk/student-visa/work",
                "https://www.gov.uk/student-visa/extend-your-visa",
                "https://www.gov.uk/graduate-visa/eligibility",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 50,
        },
    ],

    "driving": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/driving",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 50,
        },
    ],

    "employment": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/employing-people",
                "https://www.gov.uk/browse/working",
                "https://www.gov.uk/employment-contracts-and-conditions",
                "https://www.gov.uk/redundancy-your-rights",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 30,
        },
        {
            "start_urls": [
                "https://www.acas.org.uk/advice",
                "https://www.acas.org.uk/dismissal",
                "https://www.acas.org.uk/discrimination-and-the-law",
                "https://www.acas.org.uk/working-hours",
                "https://www.acas.org.uk/pay-and-wages",
            ],
            "base_url":  "https://www.acas.org.uk",
            "extractor": "acas",
            "max_pages": 30,
        },
        {
            "start_urls": [
                "https://www.citizensadvice.org.uk/work/rights-at-work/",
                "https://www.citizensadvice.org.uk/work/dismissal/",
                "https://www.citizensadvice.org.uk/work/pay/",
            ],
            "base_url":  "https://www.citizensadvice.org.uk",
            "extractor": "citizensadvice",
            "max_pages": 20,
        },
    ],

    "housing": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/housing-local-services",
                "https://www.gov.uk/private-renting/your-rights-and-responsibilities",
                "https://www.gov.uk/deposit-protection-schemes-and-landlords",
                "https://www.gov.uk/eviction-notice-periods",
                "https://www.gov.uk/government/publications/how-to-rent",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 30,
        },
        {
            "start_urls": [
                "https://www.citizensadvice.org.uk/housing/renting-privately/",
                "https://www.citizensadvice.org.uk/housing/eviction/",
                "https://www.citizensadvice.org.uk/housing/repairs-in-rented-housing/",
            ],
            "base_url":  "https://www.citizensadvice.org.uk",
            "extractor": "citizensadvice",
            "max_pages": 25,
        },
        {
            "start_urls": [
                "https://england.shelter.org.uk/housing_advice/repairs",
                "https://england.shelter.org.uk/housing_advice/eviction",
                "https://england.shelter.org.uk/housing_advice/private_renting",
            ],
            "base_url":  "https://england.shelter.org.uk",
            "extractor": "shelter",
            "max_pages": 20,
        },
    ],

    "benefits": [
        {
            "start_urls": [
                "https://www.gov.uk/browse/benefits",
                "https://www.gov.uk/universal-credit/eligibility",
                "https://www.gov.uk/housing-benefit",
                "https://www.gov.uk/council-tax-reduction",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 50,
        },
        {
            "start_urls": [
                "https://www.citizensadvice.org.uk/benefits/",
                "https://www.citizensadvice.org.uk/benefits/universal-credit/",
            ],
            "base_url":  "https://www.citizensadvice.org.uk",
            "extractor": "citizensadvice",
            "max_pages": 20,
        },
    ],

    "healthcare": [
        {
            "start_urls": [
                "https://www.gov.uk/guidance/nhs-entitlements-migrant-health-guide",
                "https://www.gov.uk/using-the-nhs/overview",
                "https://www.gov.uk/government/publications/overseas-nhs-visitors-implementing-the-charging-regulations",
            ],
            "base_url":  "https://www.gov.uk",
            "extractor": "govuk",
            "max_pages": 20,
        },
        {
            "start_urls": [
                "https://www.citizensadvice.org.uk/health/nhs-healthcare/",
                "https://www.citizensadvice.org.uk/health/nhs-and-social-care-complaints/",
                "https://www.citizensadvice.org.uk/health/social-care/",
                "https://www.citizensadvice.org.uk/health/",
            ],
            "base_url":  "https://www.citizensadvice.org.uk",
            "extractor": "citizensadvice",
            "max_pages": 25,
        },
        {
            "start_urls": [
                "https://www.nhs.uk/nhs-services/",
                "https://www.nhs.uk/nhs-services/visiting-or-moving-to-england/",
                "https://www.nhs.uk/nhs-services/gps/",
                "https://www.nhs.uk/nhs-services/prescriptions-and-pharmacies/",
            ],
            "base_url":  "https://www.nhs.uk",
            "extractor": "nhs",
            "max_pages": 20,
        },
    ],

    "criminal": [
        {
            "start_urls": [
                "https://www.citizensadvice.org.uk/law-and-courts/legal-system/",
                "https://www.citizensadvice.org.uk/law-and-courts/discrimination/",
                "https://www.citizensadvice.org.uk/law-and-courts/civil-rights/",
                "https://www.citizensadvice.org.uk/law-and-courts/parking-tickets/",
                "https://www.citizensadvice.org.uk/law-and-courts/claiming-compensation-for-a-personal-injury/",
            ],
            "base_url":  "https://www.citizensadvice.org.uk",
            "extractor": "citizensadvice",
            "max_pages": 50,
        },
    ],
}


# ---------------------------------------------------------------------------
# Strip selectors  —  per extractor
# ---------------------------------------------------------------------------

_STRIP: Dict[str, List[str]] = {
    "govuk": [
        "header", "footer", "nav",
        ".govuk-cookie-banner", ".gem-c-skip-link",
        ".govuk-breadcrumbs", ".gem-c-print-link",
        ".gem-c-feedback", ".gem-c-related-navigation",
        ".gem-c-metadata", ".govuk-back-link",
        "[data-module='ga4-link-tracker']",
    ],
    "citizensadvice": [
        "header", "footer", "nav",
        ".cookie-banner", "[class*='cookie']",
        ".breadcrumbs", ".breadcrumb",
        "[aria-label='breadcrumb']",
        ".sidebar", ".aside", ".related-content",
        ".navigation-links", ".social-share", ".feedback",
    ],
    "nhs": [
        ".nhsuk-header", ".nhsuk-footer", ".nhsuk-navigation",
        ".nhsuk-breadcrumb", ".nhsuk-skip-link",
        ".nhsuk-review-date", ".nhsuk-feedback-banner",
        ".nhsuk-related-nav", "footer", "header", "nav",
    ],
    "acas": [
        "header", "footer", "nav",
        ".breadcrumbs", ".breadcrumb",
        ".global-footer", ".cookie-bar",
        ".site-header", ".skip-link",
        ".acas-hero__breadcrumb",
    ],
    "shelter": [
        "header", "footer", "nav",
        ".breadcrumbs", ".breadcrumb",
        ".site-header", ".site-footer",
        ".cookie-notice", ".skip-to-content",
        ".rich-text-sidebar",
    ],
}

# Content selectors — first match wins
_CONTENT_SELECTORS: Dict[str, List[str]] = {
    "govuk": [
        ".gem-c-govspeak",
        ".govuk-grid-column-two-thirds",
        "article",
        "main#content",
        "main",
    ],
    "citizensadvice": [
        "article",
        ".article-body",
        ".content-body",
        "main",
    ],
    "nhs": [
        ".nhsuk-main-wrapper",
        "main",
        "article",
    ],
    "acas": [
        ".article__body",
        ".page-content",
        "main",
        "article",
    ],
    "shelter": [
        ".rich-text",
        ".page-content",
        ".content",
        "main",
        "article",
    ],
}

# Drop pages with fewer than this many words
_MIN_WORDS = 200

_DELAY_MIN = 2.0
_DELAY_MAX = 3.5


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

class UKLegalScraper:
    """
    Scrapes UK legal information from multiple authoritative sources,
    organised by legal category, saved as JSON under data/raw/<category>/.
    """

    USER_AGENT = (
        "UKLegalAssistantBot/1.0 "
        "(Academic research; respectful scraping; "
        "contact: uk-legal-assistant@example.com)"
    )

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path(settings.raw_data_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent":      self.USER_AGENT,
            "Accept":          "text/html,application/xhtml+xml",
            "Accept-Language": "en-GB,en;q=0.9",
        })

        self._robots_cache: Dict[str, Optional[RobotFileParser]] = {}
        self._visited: Set[str] = set()

        # Summary tracking
        self._summary: Dict[str, Dict] = {}

        logger.add(
            self.output_dir.parent / "scraper.log",
            rotation="10 MB",
            level="DEBUG",
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_all(self, categories: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Scrape all configured categories (or a filtered subset).
        Returns {category: pages_saved}.
        """
        targets = {
            k: v for k, v in SCRAPE_SOURCES.items()
            if categories is None or k in categories
        }

        totals: Dict[str, int] = {}
        t0 = time.monotonic()

        for category, sources in targets.items():
            logger.info(f"━━━ Starting: {category} ━━━")
            saved, words, failed = self.scrape_category(category, sources)
            totals[category] = saved
            self._summary[category] = {
                "pages_saved": saved,
                "total_words": words,
                "failed_urls": failed,
            }
            logger.info(
                f"━━━ Finished: {category} — {saved} pages, "
                f"{words:,} words, {len(failed)} failed ━━━\n"
            )

        elapsed = time.monotonic() - t0
        logger.info(
            f"Done — {sum(totals.values())} pages across "
            f"{len(totals)} categories in {elapsed:.0f}s"
        )
        self._print_summary(elapsed)
        return totals

    def scrape_category(
        self,
        category: str,
        sources: List[Dict],
    ) -> Tuple[int, int, List[str]]:
        """
        Scrape all source configs for one category.
        Returns (pages_saved, total_words, failed_urls).
        """
        cat_dir = self.output_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)

        total_saved = 0
        total_words = 0
        all_failed:  List[str] = []

        for src_cfg in sources:
            saved, words, failed = self._scrape_one_source(
                category, src_cfg, cat_dir, start_idx=total_saved
            )
            total_saved += saved
            total_words += words
            all_failed.extend(failed)

        return total_saved, total_words, all_failed

    # ------------------------------------------------------------------
    # Per-source scraping
    # ------------------------------------------------------------------

    def _scrape_one_source(
        self,
        category:  str,
        config:    Dict,
        cat_dir:   Path,
        start_idx: int,
    ) -> Tuple[int, int, List[str]]:
        base_url  = config["base_url"]
        extractor = config["extractor"]
        max_pages = config["max_pages"]

        content_urls = self._discover_content_urls(
            start_urls=config["start_urls"],
            base_url=base_url,
            max_pages=max_pages,
        )
        logger.info(
            f"[{category}|{urlparse(base_url).netloc}] "
            f"Discovered {len(content_urls)} content URLs"
        )

        saved = 0
        total_words = 0
        failed: List[str] = []

        for idx, url in enumerate(content_urls, start=1):
            if url in self._visited:
                continue

            logger.info(
                f"[{category}] ({start_idx+idx}/{start_idx+len(content_urls)}) {url}"
            )
            doc = self._scrape_page(url, category, extractor)

            if doc is not None:
                slug     = self._url_to_slug(url)
                out_path = cat_dir / f"{start_idx + saved + 1:03d}_{slug}.json"
                self._save_document(doc, out_path)
                self._visited.add(url)
                total_words += doc.get("word_count", 0)
                saved += 1
            else:
                # Only track as 'failed' if we actually tried to fetch
                if url not in self._visited:
                    failed.append(url)

            self._polite_delay()

        return saved, total_words, failed

    # ------------------------------------------------------------------
    # Link discovery  (BFS)
    # ------------------------------------------------------------------

    def _discover_content_urls(
        self,
        start_urls: List[str],
        base_url:   str,
        max_pages:  int,
    ) -> List[str]:
        browse_queue: List[str] = list(start_urls)
        visited_browse: Set[str] = set()
        content_urls: Set[str] = set()

        # Seed URLs that are direct content pages should be scraped too
        for url in start_urls:
            if self._classify_link(url, base_url) in ("browse_and_content", "content_only"):
                content_urls.add(url)

        while browse_queue and len(content_urls) < max_pages:
            url = browse_queue.pop(0)
            if url in visited_browse:
                continue
            visited_browse.add(url)

            response = self._fetch(url)
            if response is None:
                continue

            soup  = BeautifulSoup(response.text, "html.parser")
            links = self._extract_page_links(soup, url, base_url)

            for link in links:
                if link in self._visited or link in content_urls:
                    continue

                link_type = self._classify_link(link, base_url)

                if link_type in ("browse_only", "browse_and_content"):
                    if link not in visited_browse:
                        browse_queue.append(link)

                if link_type in ("browse_and_content", "content_only"):
                    content_urls.add(link)

            self._polite_delay()

        return list(content_urls)[:max_pages]

    def _extract_page_links(
        self,
        soup:        BeautifulSoup,
        current_url: str,
        base_url:    str,
    ) -> List[str]:
        search_root = soup.find("main") or soup

        for sel in (".gem-c-popular-on-govuk", "aside", ".govuk-related-items"):
            for el in search_root.select(sel):
                el.decompose()

        base_netloc = urlparse(base_url).netloc
        seen: Dict[str, None] = {}

        for a in search_root.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            full   = urljoin(current_url, href)
            parsed = urlparse(full)

            # Allow same apex domain (e.g. england.shelter.org.uk ↔ shelter.org.uk)
            page_netloc = parsed.netloc
            if not (
                page_netloc == base_netloc
                or page_netloc.endswith("." + base_netloc)
                or base_netloc.endswith("." + page_netloc)
            ):
                continue

            canonical = urlunparse(parsed._replace(query="", fragment=""))
            if self._should_skip_url(canonical, base_url):
                continue

            seen[canonical] = None

        return list(seen)

    def _classify_link(self, url: str, base_url: str) -> str:
        """
        Return 'browse_only' | 'browse_and_content' | 'content_only'.
        """
        path     = urlparse(url).path.rstrip("/")
        segments = [s for s in path.split("/") if s]
        netloc   = urlparse(url).netloc

        # ── gov.uk ──────────────────────────────────────────────────────
        if "gov.uk" in netloc:
            if path.startswith("/browse"):
                return "browse_only"
            if len(segments) == 1:
                return "browse_and_content"
            return "content_only"

        # ── citizensadvice ───────────────────────────────────────────────
        if "citizensadvice" in netloc:
            if len(segments) <= 1:
                return "browse_only"
            if len(segments) <= 3:
                return "browse_and_content"
            return "content_only"

        # ── nhs.uk ───────────────────────────────────────────────────────
        if "nhs.uk" in netloc:
            if len(segments) <= 1:
                return "browse_only"
            if len(segments) == 2:
                return "browse_and_content"
            return "content_only"

        # ── acas.org.uk ──────────────────────────────────────────────────
        if "acas.org.uk" in netloc:
            if len(segments) == 0:
                return "browse_only"
            if len(segments) == 1:
                return "browse_and_content"
            return "content_only"

        # ── shelter ──────────────────────────────────────────────────────
        if "shelter" in netloc:
            if len(segments) <= 1:
                return "browse_only"
            if len(segments) == 2:
                return "browse_and_content"
            return "content_only"

        return "content_only"

    def _should_skip_url(self, url: str, base_url: str) -> bool:
        path   = urlparse(url).path.lower()
        netloc = urlparse(url).netloc

        if re.search(r"\.(pdf|docx?|xlsx?|zip|png|jpe?g|svg|gif|mp4|css|js)$", path):
            return True

        if "gov.uk" in netloc:
            skip = [
                "/contact", "/sign-in", "/government/organisations",
                "/search", "/help", "/api/", "/assets/",
                "/cymraeg", "/bank-holidays", "/find-local-council",
                "/rubbish-collection-day", "/register-to-vote",
                "/check-long-term-flood-risk", "/check-mot-history",
                "/check-vehicle-tax", "/vehicle-tax",
                "/estimate-income-tax", "/personal-tax-account",
                "/log-in-file-self-assessment-tax-return",
                "/apply-blue-badge", "/send-prisoner-money",
                "/benefits-calculators", "/foreign-travel-advice",
                "/government/get-involved", "/government/how-government-works",
                "/government/publications", "/government/collections",
                "/government/statistics",
            ]
            return any(path.startswith(p) for p in skip)

        if "citizensadvice" in netloc:
            skip = [
                "/about-us", "/contact-us", "/local-citizens-advice",
                "/cymraeg", "/scotland", "/wales", "/northern-ireland",
                "/search", "/privacy", "/media-centre",
            ]
            return any(path.startswith(p) for p in skip)

        if "nhs.uk" in netloc:
            skip = [
                "/search", "/about-us", "/our-policies",
                "/conditions",   # clinical conditions — out of scope
                "/medicines",    # drug info — out of scope
                "/live-well",    # lifestyle — out of scope
                "/mental-health",
            ]
            return any(path.startswith(p) for p in skip)

        if "acas.org.uk" in netloc:
            skip = [
                "/search", "/about-us", "/contact-us",
                "/events", "/training", "/media-centre",
            ]
            return any(path.startswith(p) for p in skip)

        if "shelter" in netloc:
            skip = [
                "/search", "/about-us", "/donate", "/support-us",
                "/get-help", "/our-work", "/media", "/jobs",
            ]
            return any(path.startswith(p) for p in skip)

        return False

    # ------------------------------------------------------------------
    # Page scraping
    # ------------------------------------------------------------------

    def _scrape_page(
        self,
        url:       str,
        category:  str,
        extractor: str,
    ) -> Optional[Dict]:
        if not self._robots_allows(url):
            logger.debug(f"robots.txt disallows: {url}")
            return None

        response = self._fetch(url)
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title, content = self._extract(soup, extractor)

        if not content:
            logger.info("  ↳ skip — no content extracted")
            return None

        word_count = len(content.split())
        if word_count < _MIN_WORDS:
            logger.info(f"  ↳ skip — too short ({word_count} words)")
            return None

        return {
            "title":         title,
            "url":           url,
            "category":      category,
            "content":       content,
            "scraped_at":    datetime.now(timezone.utc).isoformat(),
            "last_modified": self._get_last_modified(soup, response),
            "word_count":    word_count,
        }

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    def _extract(
        self,
        soup:      BeautifulSoup,
        extractor: str,
    ) -> Tuple[str, str]:
        """Strip boilerplate, find content area, return (title, text)."""
        for selector in _STRIP.get(extractor, []):
            for el in soup.select(selector):
                el.decompose()

        title_tag = soup.find("h1")
        title     = title_tag.get_text(strip=True) if title_tag else ""

        content_area: Optional[Tag] = None
        for selector in _CONTENT_SELECTORS.get(extractor, ["main"]):
            content_area = soup.select_one(selector)
            if content_area:
                break

        if not content_area:
            content_area = soup.find("main") or soup.find("body")

        if not content_area:
            return title, ""

        return title, self._html_to_text(content_area)

    @staticmethod
    def _html_to_text(root: Tag) -> str:
        """
        Walk the DOM and produce structured plain text that preserves:
          - Paragraphs          <p>
          - Headings            <h2>–<h6>  (prefixed with newline)
          - Unordered lists     <ul><li>   (• bullet)
          - Ordered lists       <ol><li>   (1. 2. 3. numbering)
          - Definition lists    <dl><dt><dd>
          - Tables              <table>    (pipe-separated rows)
        """
        lines: List[str] = []

        def walk(el: Tag) -> None:
            if not hasattr(el, "name") or el.name is None:
                return

            name = el.name.lower()

            if name in ("script", "style", "noscript", "template", "iframe"):
                return

            # ── Headings ──────────────────────────────────────────────
            if name in ("h2", "h3", "h4", "h5", "h6"):
                text = el.get_text(separator=" ", strip=True)
                if text:
                    lines.append(f"\n{text}")
                return          # no deeper recursion

            # ── Paragraphs ────────────────────────────────────────────
            if name == "p":
                text = el.get_text(separator=" ", strip=True)
                if text:
                    lines.append(text)
                return

            # ── Ordered / unordered lists ─────────────────────────────
            if name in ("ul", "ol"):
                items = el.find_all("li", recursive=False)
                for i, item in enumerate(items, 1):
                    text = item.get_text(separator=" ", strip=True)
                    if text:
                        prefix = f"{i}." if name == "ol" else "•"
                        lines.append(f"{prefix} {text}")
                return

            # ── Definition lists ──────────────────────────────────────
            if name == "dl":
                for child in el.children:
                    if not hasattr(child, "name"):
                        continue
                    cname = child.name.lower() if child.name else ""
                    text  = child.get_text(separator=" ", strip=True)
                    if cname == "dt" and text:
                        lines.append(f"\n{text}:")
                    elif cname == "dd" and text:
                        lines.append(f"  {text}")
                return

            # ── Tables ────────────────────────────────────────────────
            if name == "table":
                for row in el.find_all("tr"):
                    cells = [
                        td.get_text(separator=" ", strip=True)
                        for td in row.find_all(["th", "td"])
                    ]
                    if any(cells):
                        lines.append(" | ".join(c for c in cells if c))
                return

            # ── Block containers — recurse ────────────────────────────
            if name in (
                "div", "section", "article", "main", "aside",
                "header", "footer", "nav", "form",
                "blockquote", "figure", "figcaption",
                "details", "summary",
            ):
                for child in el.children:
                    walk(child)
                return

            # ── Everything else — grab text ───────────────────────────
            text = el.get_text(separator=" ", strip=True)
            if text:
                lines.append(text)

        walk(root)

        # Collapse consecutive blank lines
        cleaned: List[str] = []
        prev_blank = False
        for line in lines:
            stripped   = line.strip()
            is_blank   = not stripped
            if is_blank and prev_blank:
                continue
            cleaned.append(stripped)
            prev_blank = is_blank

        return "\n".join(cleaned).strip()

    # ------------------------------------------------------------------
    # HTTP layer
    # ------------------------------------------------------------------

    def _fetch(self, url: str) -> Optional[requests.Response]:
        try:
            return self._do_fetch(url)
        except Exception as exc:
            logger.error(f"Giving up on {url}: {exc}")
            return None

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=4, max=30),
        reraise=True,
    )
    def _do_fetch(self, url: str) -> Optional[requests.Response]:
        resp = self.session.get(url, timeout=20, allow_redirects=True)

        if resp.status_code in (404, 410):
            return None

        resp.raise_for_status()

        ct = resp.headers.get("Content-Type", "")
        if "text/html" not in ct and "application/xhtml" not in ct:
            return None

        return resp

    # ------------------------------------------------------------------
    # Robots.txt
    # ------------------------------------------------------------------

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin not in self._robots_cache:
            rp = RobotFileParser(f"{origin}/robots.txt")
            try:
                rp.read()
                self._robots_cache[origin] = rp
            except Exception:
                self._robots_cache[origin] = None

        rp = self._robots_cache[origin]
        return rp is None or rp.can_fetch(self.USER_AGENT, url)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print_summary(self, elapsed: float) -> None:
        logger.info("=" * 60)
        logger.info("SCRAPE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"{'Category':<15} {'Pages':>6} {'Words':>10} {'Failed':>7}")
        logger.info("-" * 45)
        total_pages = total_words = total_failed = 0
        for cat, stats in self._summary.items():
            p = stats["pages_saved"]
            w = stats["total_words"]
            f = len(stats["failed_urls"])
            logger.info(f"{cat:<15} {p:>6} {w:>10,} {f:>7}")
            total_pages  += p
            total_words  += w
            total_failed += f
        logger.info("-" * 45)
        logger.info(
            f"{'TOTAL':<15} {total_pages:>6} {total_words:>10,} {total_failed:>7}"
        )
        logger.info(f"Wall time: {elapsed:.0f}s")
        if total_failed:
            logger.info("Failed URLs:")
            for cat, stats in self._summary.items():
                for u in stats["failed_urls"]:
                    logger.info(f"  [{cat}] {u}")
        logger.info("=" * 60)

    @staticmethod
    def _get_last_modified(soup: BeautifulSoup, response: requests.Response) -> str:
        if val := response.headers.get("Last-Modified", ""):
            return val
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property") or ""
            if name in ("modified_date", "article:modified_time"):
                if content := meta.get("content", ""):
                    return content
        for tag in soup.find_all(["time", "p", "span"], limit=40):
            text = tag.get_text(strip=True)
            if re.search(r"last\s+updated", text, re.IGNORECASE):
                return text[:120]
        return ""

    @staticmethod
    def _url_to_slug(url: str, max_len: int = 60) -> str:
        path = urlparse(url).path.strip("/")
        slug = re.sub(r"[^a-z0-9]+", "-", path.lower())[:max_len].strip("-")
        return slug or hashlib.md5(url.encode()).hexdigest()[:12]

    @staticmethod
    def _save_document(doc: Dict, path: Path) -> None:
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.debug(f"Saved → {path.name}")

    @staticmethod
    def _polite_delay() -> None:
        time.sleep(random.uniform(_DELAY_MIN, _DELAY_MAX))
