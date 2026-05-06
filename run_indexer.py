#!/usr/bin/env python3
"""
run_indexer.py — UK Legal Assistant document indexing pipeline.

Reads scraped JSON files from data/raw/<category>/, chunks them, embeds them
with BAAI/bge-small-en-v1.5, builds a FAISS + BM25 index, and writes the
artefacts to data/index/.

Usage
-----
# Index all categories
python run_indexer.py

# Index specific categories only
python run_indexer.py --categories immigration driving

# Point at a different raw-data or index directory
python run_indexer.py --raw-dir /tmp/raw --index-dir /tmp/index
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT / "backend"))

from loguru import logger  # noqa: E402
from app.ingestion.chunker import TextChunker  # noqa: E402
from app.ingestion.indexer import VectorIndexer  # noqa: E402
from app.config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_indexer",
        description="UK Legal Assistant — document indexing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--categories",
        nargs="+",
        metavar="CAT",
        help="Index only these categories. Default: all sub-dirs under --raw-dir.",
    )
    p.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "data" / "raw",
        metavar="DIR",
        help="Directory containing scraped JSON files (default: data/raw/).",
    )
    p.add_argument(
        "--index-dir",
        type=Path,
        default=ROOT / "data" / "index",
        metavar="DIR",
        help="Destination directory for index artefacts (default: data/index/).",
    )
    p.add_argument(
        "--chunk-size",
        type=int,
        default=settings.chunk_size,
        metavar="N",
        help=f"Words per chunk (default: {settings.chunk_size}).",
    )
    p.add_argument(
        "--overlap",
        type=int,
        default=settings.chunk_overlap,
        metavar="N",
        help=f"Overlap words between consecutive chunks (default: {settings.chunk_overlap}).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_documents(raw_dir: Path, categories: list[str] | None) -> list[dict]:
    """Read all JSON files under raw_dir, optionally filtered by category."""
    import json

    docs: list[dict] = []
    cat_dirs = sorted(raw_dir.iterdir()) if raw_dir.exists() else []

    for cat_dir in cat_dirs:
        if not cat_dir.is_dir():
            continue
        if categories and cat_dir.name not in categories:
            continue

        json_files = sorted(cat_dir.glob("*.json"))
        for jf in json_files:
            try:
                doc = json.loads(jf.read_text(encoding="utf-8"))
                docs.append(doc)
            except Exception as exc:
                logger.warning(f"Skipping {jf}: {exc}")

        logger.info(f"  {cat_dir.name:<20} {len(json_files):>4} files loaded")

    return docs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    args = _build_parser().parse_args()

    logger.remove()
    logger.add(sys.stderr, level=args.log_level, colorize=True)

    width = 60
    logger.info("═" * width)
    logger.info(" UK Legal Assistant — Document Indexer")
    logger.info("═" * width)
    cats = ", ".join(sorted(args.categories)) if args.categories else "all"
    logger.info(f"  Categories  : {cats}")
    logger.info(f"  Raw dir     : {args.raw_dir}")
    logger.info(f"  Index dir   : {args.index_dir}")
    logger.info(f"  Chunk size  : {args.chunk_size} words")
    logger.info(f"  Overlap     : {args.overlap} words")
    logger.info("═" * width)

    t0 = time.monotonic()

    # ---- Load raw documents ------------------------------------------------
    logger.info("Loading scraped documents …")
    docs = _load_documents(args.raw_dir, args.categories)

    if not docs:
        logger.error(
            f"No documents found in {args.raw_dir}. "
            "Run `python run_scraper.py` first."
        )
        sys.exit(1)

    logger.info(f"Loaded {len(docs)} documents total")

    # ---- Chunk -------------------------------------------------------------
    logger.info("Chunking documents …")
    chunker = TextChunker(chunk_size=args.chunk_size, overlap=args.overlap)
    chunks = chunker.chunk_batch(docs)
    logger.info(f"Produced {len(chunks)} chunks")

    # ---- Build index -------------------------------------------------------
    logger.info("Building FAISS + BM25 index …")
    # Override index path from CLI flag
    settings.index_path = str(args.index_dir)
    indexer = VectorIndexer()
    indexer.build(chunks)

    elapsed = time.monotonic() - t0
    logger.info("═" * width)
    logger.info(f"  Documents   : {len(docs)}")
    logger.info(f"  Chunks      : {len(chunks)}")
    logger.info(f"  Time        : {elapsed:.1f}s")
    logger.info(f"  Index dir   : {args.index_dir}")
    logger.info("═" * width)
    logger.info("Indexing complete. Start the API with: uvicorn backend.app.main:app --reload")


if __name__ == "__main__":
    main()
