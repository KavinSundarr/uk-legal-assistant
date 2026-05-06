#!/usr/bin/env python3
"""
run_scraper.py — UK Legal Assistant document scraping pipeline.

Discovers and saves publicly available UK legal pages from gov.uk and
citizensadvice.org.uk as JSON files under data/raw/<category>/.

Usage
-----
# Scrape all categories (~200-300 pages, ~10-20 min at polite rate limits)
python run_scraper.py

# Scrape specific categories only
python run_scraper.py --categories immigration driving housing

# Discover links but do not download pages (quick sanity-check)
python run_scraper.py --dry-run

# Write JSON files to a custom location
python run_scraper.py --output-dir /tmp/legal-data
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — add backend/ so `app.*` imports resolve from the repo root
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT / "backend"))

from loguru import logger  # noqa: E402  (after path bootstrap)
from app.ingestion.scraper import UKLegalScraper, SCRAPE_SOURCES  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_scraper",
        description="UK Legal Assistant — document scraping pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--categories",
        nargs="+",
        metavar="CAT",
        choices=sorted(SCRAPE_SOURCES),
        help=(
            "Scrape only these categories "
            f"(choices: {', '.join(sorted(SCRAPE_SOURCES))}). "
            "Default: all."
        ),
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "raw",
        metavar="DIR",
        help="Directory for scraped JSON files (default: data/raw/).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and count URLs only — no files written.",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log verbosity (default: INFO).",
    )
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header(args: argparse.Namespace) -> None:
    width = 60
    logger.info("═" * width)
    logger.info(" UK Legal Assistant — Document Scraper")
    logger.info("═" * width)
    cats = ", ".join(sorted(args.categories)) if args.categories else "all"
    logger.info(f"  Categories  : {cats}")
    logger.info(f"  Output dir  : {args.output_dir}")
    logger.info(f"  Dry run     : {args.dry_run}")
    logger.info("═" * width)


def _print_summary(totals: dict[str, int], elapsed: float) -> None:
    width = 60
    logger.info("")
    logger.info("═" * width)
    logger.info(" SCRAPING COMPLETE")
    logger.info("─" * width)
    for cat, count in sorted(totals.items()):
        bar = "█" * min(count, 40)
        logger.info(f"  {cat:<20} {count:>4}  {bar}")
    logger.info("─" * width)
    logger.info(f"  {'Total pages':<20} {sum(totals.values()):>4}")
    logger.info(f"  {'Time elapsed':<20} {elapsed:>3.0f}s")
    logger.info("═" * width)


def _dry_run(args: argparse.Namespace, scraper: UKLegalScraper) -> None:
    logger.info("DRY RUN — link discovery only, no files written.\n")
    totals: dict[str, int] = {}

    targets = {
        k: v
        for k, v in SCRAPE_SOURCES.items()
        if args.categories is None or k in args.categories
    }

    for category, sources in targets.items():
        total_urls = 0
        for src_cfg in sources:
            urls = scraper._discover_content_urls(
                start_urls=src_cfg["start_urls"],
                base_url=src_cfg["base_url"],
                max_pages=src_cfg["max_pages"],
            )
            total_urls += len(urls)
        logger.info(f"  {category:<20} {total_urls:>4} URLs found")
        totals[category] = total_urls

    logger.info(f"\n  {'Total':<20} {sum(totals.values()):>4} URLs")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _build_parser().parse_args()

    # Remove the default loguru handler and replace with our level preference
    logger.remove()
    logger.add(sys.stderr, level=args.log_level, colorize=True)

    _print_header(args)

    scraper = UKLegalScraper(output_dir=args.output_dir)

    if args.dry_run:
        _dry_run(args, scraper)
        return

    t0 = time.monotonic()
    totals = scraper.scrape_all(categories=args.categories)
    _print_summary(totals, elapsed=time.monotonic() - t0)


if __name__ == "__main__":
    main()
