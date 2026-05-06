"""
TextChunker — splits documents into focused, retrieval-optimised chunks.

Strategy
--------
1. Semantic split: break on paragraph boundaries (blank lines).  Keeps
   related sentences together without crossing topic boundaries.
2. Hard-cap enforcement: any semantic piece that still exceeds
   MAX_SEMANTIC_WORDS (250) is further split with the fixed sliding-window
   algorithm so no chunk ever exceeds that limit.
3. Quality filter: discard chunks that are too short, dominated by
   numbers/symbols, or look like navigation menus.
4. Statistics: log avg / min / max size, total kept / skipped with reasons.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List

from loguru import logger

from app.config import settings


_MAX_SEMANTIC_WORDS = 250   # hard cap — semantic pieces over this get re-split
_MIN_CHUNK_WORDS    = 30    # quality floor — shorter chunks discarded


class TextChunker:
    """
    Splits raw document text into overlapping, quality-filtered chunks.
    Each chunk inherits the source document's metadata.
    """

    def __init__(self, chunk_size: int | None = None, overlap: int | None = None):
        self.chunk_size = chunk_size or settings.chunk_size    # target words
        self.overlap    = overlap    or settings.chunk_overlap  # overlap words
        # Accumulate across chunk_batch call
        self._skip_stats:  Counter    = Counter()
        self._word_counts: List[int]  = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(self, text: str, metadata: Dict) -> List[Dict]:
        """Return chunk dicts for one document.  Resets per-doc skip tracking."""
        pieces = self._semantic_split(text)
        kept: List[Dict] = []

        for piece in pieces:
            verdict = self._quality_verdict(piece)
            if verdict != "ok":
                self._skip_stats[verdict] += 1
                continue
            kept.append(
                {
                    **metadata,
                    "content":     piece,
                    "chunk_index": len(kept),
                    "chunk_total": None,
                }
            )

        for c in kept:
            c["chunk_total"] = len(kept)

        return kept

    def chunk_batch(self, documents: List[Dict]) -> List[Dict]:
        """Chunk every document and return the flattened list with statistics."""
        self._skip_stats.clear()
        self._word_counts.clear()

        all_chunks: List[Dict] = []

        for doc in documents:
            meta = {
                "title":         doc.get("title", ""),
                "url":           doc.get("url", ""),
                "category":      doc.get("category", ""),
                "last_modified": doc.get("last_modified", ""),
                "scraped_at":    doc.get("scraped_at", ""),
            }
            chunks = self.chunk(doc.get("content", ""), meta)
            for c in chunks:
                self._word_counts.append(len(c["content"].split()))
            all_chunks.extend(chunks)

        # Re-number chunk_index globally (optional — not used by retriever)
        for idx, c in enumerate(all_chunks):
            c["chunk_index"] = idx

        self._log_stats(len(documents))
        return all_chunks

    # ------------------------------------------------------------------
    # Semantic splitting
    # ------------------------------------------------------------------

    def _semantic_split(self, text: str) -> List[str]:
        """Split on paragraph boundaries, then enforce the hard word cap."""
        # Paragraph boundary = one or more blank lines
        paragraphs = re.split(r"\n{2,}", text)

        pieces: List[str] = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(para.split()) <= _MAX_SEMANTIC_WORDS:
                pieces.append(para)
            else:
                pieces.extend(self._fixed_split(para))

        return pieces

    def _fixed_split(self, text: str) -> List[str]:
        """Sliding-window fixed chunking used when a paragraph is too long."""
        words = text.split()
        step  = max(1, self.chunk_size - self.overlap)
        result: List[str] = []
        for start in range(0, len(words), step):
            window = words[start : start + self.chunk_size]
            if window:
                result.append(" ".join(window))
            if start + self.chunk_size >= len(words):
                break
        return result

    # ------------------------------------------------------------------
    # Quality filter
    # ------------------------------------------------------------------

    def _quality_verdict(self, text: str) -> str:
        """Return 'ok' or a skip-reason string."""
        words = text.split()

        if len(words) < _MIN_CHUNK_WORDS:
            return "too_short"

        # Mostly numbers / symbols — over 60 % of tokens lack any letter
        non_alpha = sum(1 for w in words if not re.search(r"[a-zA-Z]", w))
        if non_alpha / len(words) > 0.60:
            return "mostly_numbers_or_symbols"

        # Navigation-menu heuristic: >5 lines where >70 % are very short
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) > 5:
            short_lines = sum(1 for ln in lines if len(ln.split()) < 8)
            if short_lines / len(lines) > 0.70:
                return "navigation_menu"

        return "ok"

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _log_stats(self, total_docs: int) -> None:
        kept         = len(self._word_counts)
        total_skip   = sum(self._skip_stats.values())

        if self._word_counts:
            avg_wc = sum(self._word_counts) / kept
            min_wc = min(self._word_counts)
            max_wc = max(self._word_counts)
        else:
            avg_wc = min_wc = max_wc = 0

        logger.info("── Chunk Statistics ─────────────────────────────────")
        logger.info(f"  Documents processed : {total_docs}")
        logger.info(f"  Chunks kept         : {kept}")
        logger.info(f"  Chunks skipped      : {total_skip}")
        for reason, count in self._skip_stats.most_common():
            logger.info(f"    ↳ {reason:<35} {count}")
        logger.info(f"  Avg chunk size      : {avg_wc:.0f} words")
        logger.info(f"  Min chunk size      : {min_wc} words")
        logger.info(f"  Max chunk size      : {max_wc} words")
        logger.info("─────────────────────────────────────────────────────")
