#!/usr/bin/env python3
"""
test_category_detection.py
==========================
Tests category detection and retrieval quality for the 4 cross-category
queries identified as problematic. For each query shows:
  - Raw keyword scores per category
  - Final decision and reason
  - Number of chunks retrieved
  - Top chunk relevance score and its category
  - Whether the answer appears grounded in relevant chunks

Usage
-----
  python test_category_detection.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.rag.pipeline import RAGPipeline, _CATEGORY_KEYWORDS  # noqa: E402

# ---------------------------------------------------------------------------
# Test queries
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "label": "(a) NHS treatment as international student",
        "query": "Am I entitled to free NHS treatment as an international student?",
        "expected_decision": "None (tie: student + healthcare)",
        "relevant_cats": {"student", "healthcare"},
    },
    {
        "label": "(b) Housing benefit on student visa",
        "query": "Can I get housing benefit while on a student visa?",
        "expected_decision": "None (multi-category)",
        "relevant_cats": {"student", "housing", "benefits"},
    },
    {
        "label": "(c) Employment rights on work visa",
        "query": "What are my employment rights if I'm on a work visa?",
        "expected_decision": "None (tie: employment + immigration)",
        "relevant_cats": {"employment", "immigration"},
    },
    {
        "label": "(d) Council tax as international student",
        "query": "Do I need to pay council tax as an international student?",
        "expected_decision": "None (multi-category)",
        "relevant_cats": {"student", "benefits", "housing"},
    },
]

# ---------------------------------------------------------------------------
# Scoring helper — mirrors pipeline logic exactly
# ---------------------------------------------------------------------------

_MIN_SCORE = RAGPipeline._CATEGORY_MIN_SCORE


def _score_query(query: str):
    query_lower = query.lower()
    scores = {}
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        s = sum(1 for kw in keywords if kw in query_lower)
        if s:
            scores[cat] = s
    return scores


def _decide(scores: dict) -> tuple[str | None, str]:
    """Return (category_or_None, reason_string)."""
    if not scores:
        return None, "no keyword matches"
    best_score = max(scores.values())
    if best_score < _MIN_SCORE:
        return None, f"top score {best_score} < min threshold {_MIN_SCORE} — uncertain"
    winners = [c for c, s in scores.items() if s == best_score]
    if len(winners) > 1:
        return None, f"tie between {winners} at score={best_score}"
    return winners[0], f"clear winner (score={best_score})"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 70)
    print("  Category Detection + Retrieval Quality Test")
    print("=" * 70)

    pipeline = RAGPipeline()

    for item in QUERIES:
        label   = item["label"]
        query   = item["query"]
        rel_cats = item["relevant_cats"]
        expected = item["expected_decision"]

        print(f"\n{'-' * 70}")
        print(f"  Query: {label}")
        print(f"  Text : \"{query}\"")
        print(f"{'-' * 70}")

        # ── Category detection ──────────────────────────────────────────────
        scores  = _score_query(query)
        cat, reason = _decide(scores)

        # Sort scores descending for display
        sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
        print(f"\n  Keyword scores (count per category):")
        for c, s in sorted_scores:
            marker = " <-- winner" if c == cat else ""
            print(f"    {c:<14} {s}{marker}")

        print(f"\n  Decision   : {cat!r}")
        print(f"  Reason     : {reason}")
        print(f"  Expected   : {expected}")
        ok = "PASS" if cat is None else "NOTE (category applied)"
        print(f"  Status     : {ok}")

        # ── Retrieval ───────────────────────────────────────────────────────
        from app.models import QueryRequest
        req = QueryRequest(query=query, category=None, limit=5)
        # Use detected category (pipeline will also call detect_category)
        chunks = pipeline.retriever.retrieve(query, category=cat, k=15)
        top5   = pipeline.reranker.rerank(query, chunks, top_k=5)

        print(f"\n  Retrieved  : {len(chunks)} chunks (pre-rerank), top 5 after rerank:")
        print(f"  {'Rank':<5} {'Score':>7}  {'Cat':<14} {'Source'}")
        print(f"  {'-'*4} {'-'*7}  {'-'*13} {'-'*35}")
        for rank, chunk in enumerate(top5, 1):
            source_short = chunk.document[:35] if chunk.document else chunk.url[:35]
            relevant = "*" if chunk.category in rel_cats else ""
            print(
                f"  {rank:<5} {chunk.relevance_score:>7.4f}  "
                f"{chunk.category:<14} {source_short}{relevant}"
            )

        # ── Grounding check ─────────────────────────────────────────────────
        top_score      = top5[0].relevance_score if top5 else 0.0
        top_cat        = top5[0].category        if top5 else "—"
        relevant_count = sum(1 for c in top5 if c.category in rel_cats)

        grounded = top_score >= 0.5 and relevant_count >= 1
        print(f"\n  Top chunk score : {top_score:.4f}")
        print(f"  Top chunk cat   : {top_cat}")
        print(f"  Relevant chunks : {relevant_count}/5 (categories: {rel_cats})")
        print(f"  Answer grounded : {'YES' if grounded else 'NO'}")
        print(f"  (* = chunk category is relevant to this query)")

    print(f"\n{'=' * 70}")
    print("  Test complete.")
    print('=' * 70)


if __name__ == "__main__":
    main()
