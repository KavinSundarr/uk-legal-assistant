"""
Tests for HybridRetriever — requires the built index at data/index/.
"""

import numpy as np
import pytest

from app.rag.retriever import HybridRetriever
from app.models import SourceChunk


# ── Shared fixture (index loads once per session) ────────────────────────────

@pytest.fixture(scope="session")
def retriever():
    r = HybridRetriever()
    r._ensure_loaded()   # eager-load so first test isn't slow
    return r


# ── Dense search ─────────────────────────────────────────────────────────────

class TestDenseSearch:
    def test_returns_list(self, retriever):
        vec = retriever._embedder.encode("skilled worker visa requirements")
        results = retriever.dense_search(vec, k=10)
        assert isinstance(results, list)

    def test_respects_k(self, retriever):
        vec = retriever._embedder.encode("penalty points driving licence")
        for k in (1, 5, 10):
            results = retriever.dense_search(vec, k=k)
            assert len(results) <= k

    def test_returns_tuples_of_int_float(self, retriever):
        vec = retriever._embedder.encode("universal credit claim")
        results = retriever.dense_search(vec, k=5)
        for idx, score in results:
            assert isinstance(idx, int)
            assert isinstance(score, float)
            assert 0 <= idx < retriever.chunk_count

    def test_indices_within_bounds(self, retriever):
        vec = retriever._embedder.encode("tenant eviction notice section 21")
        results = retriever.dense_search(vec, k=20)
        for idx, _ in results:
            assert 0 <= idx < retriever.chunk_count


# ── Sparse (BM25) search ─────────────────────────────────────────────────────

class TestSparseSearch:
    def test_returns_list(self, retriever):
        results = retriever.sparse_search(["visa", "skilled", "worker"], k=10)
        assert isinstance(results, list)

    def test_respects_k(self, retriever):
        tokens = ["driving", "licence", "penalty"]
        for k in (1, 5, 10):
            results = retriever.sparse_search(tokens, k=k)
            assert len(results) <= k

    def test_returns_tuples_of_int_float(self, retriever):
        results = retriever.sparse_search(["universal", "credit"], k=5)
        for idx, score in results:
            assert isinstance(idx, int)
            assert isinstance(score, float)
            assert idx >= 0

    def test_known_keyword_ranks_highly(self, retriever):
        """A chunk whose category is 'criminal' should appear in BM25 top-20
        when searching for 'arrest police rights'."""
        results = retriever.sparse_search(["arrest", "police", "rights"], k=20)
        top_indices = [idx for idx, _ in results[:20]]
        top_categories = [retriever._chunks[i]["category"] for i in top_indices]
        assert "criminal" in top_categories, (
            "Expected at least one criminal-law chunk in BM25 top-20 "
            "for query 'arrest police rights'"
        )


# ── RRF fusion ───────────────────────────────────────────────────────────────

class TestRRFFusion:
    def test_returns_sorted_descending(self, retriever):
        dense  = [(0, 0.9), (1, 0.8), (2, 0.7)]
        sparse = [(2, 5.0), (0, 4.0), (3, 3.0)]
        fused  = retriever.rrf_fusion(dense, sparse)
        scores = [s for _, s in fused]
        assert scores == sorted(scores, reverse=True)

    def test_all_ids_present(self, retriever):
        dense  = [(0, 0.9), (1, 0.7)]
        sparse = [(1, 4.0), (2, 3.0)]
        fused  = retriever.rrf_fusion(dense, sparse)
        fused_ids = {idx for idx, _ in fused}
        assert fused_ids == {0, 1, 2}

    def test_score_formula(self, retriever):
        """Index 0 ranked 1st in dense, 2nd in sparse → score = 1/61 + 1/62."""
        dense  = [(0, 1.0), (1, 0.5)]
        sparse = [(1, 2.0), (0, 1.0)]
        fused  = dict(retriever.rrf_fusion(dense, sparse))
        expected_0 = 1 / (60 + 1) + 1 / (60 + 2)
        assert abs(fused[0] - expected_0) < 1e-9

    def test_empty_inputs(self, retriever):
        assert retriever.rrf_fusion([], []) == []

    def test_one_empty_list(self, retriever):
        dense  = [(5, 0.9), (3, 0.8)]
        fused  = retriever.rrf_fusion(dense, [])
        assert len(fused) == 2


# ── Category filtering ────────────────────────────────────────────────────────

class TestCategoryFilter:
    def test_filters_correctly(self, retriever):
        # Build artificial results covering multiple categories
        housing_indices  = [i for i, c in enumerate(retriever._chunks) if c["category"] == "housing"]
        criminal_indices = [i for i, c in enumerate(retriever._chunks) if c["category"] == "criminal"]
        assert housing_indices and criminal_indices, "Index must have housing and criminal chunks"

        mixed = [(housing_indices[0], 0.9), (criminal_indices[0], 0.8)]
        filtered = retriever.filter_by_category(mixed, "housing")
        assert all(
            retriever._chunks[idx]["category"] == "housing"
            for idx, _ in filtered
        )

    def test_falls_back_when_no_match(self, retriever):
        """If no chunks match the category, return the original list."""
        results = [(0, 0.9), (1, 0.8)]
        filtered = retriever.filter_by_category(results, "nonexistent_category")
        assert filtered == results


# ── Full retrieve() pipeline ─────────────────────────────────────────────────

class TestRetrieve:
    @pytest.mark.parametrize("query,expected_cat", [
        ("How do I apply for a skilled worker visa?",  "immigration"),
        ("What are the penalty points for speeding?",  "driving"),
        ("Can I work part-time on a student visa?",    "student"),
        ("My landlord won't return my deposit",        "housing"),
        ("What is universal credit and how do I claim","benefits"),
        ("I was arrested — what are my rights?",       "criminal"),
        ("How much notice must my employer give me?",  "employment"),
    ])
    def test_returns_source_chunks(self, retriever, query, expected_cat):
        chunks = retriever.retrieve(query, k=5)
        assert len(chunks) > 0
        assert all(isinstance(c, SourceChunk) for c in chunks)

    def test_respects_limit(self, retriever):
        for k in (1, 3, 5):
            chunks = retriever.retrieve("visa requirements UK", k=k)
            assert len(chunks) <= k

    def test_category_filter_narrows_results(self, retriever):
        chunks_all  = retriever.retrieve("visa requirements", k=10)
        chunks_imm  = retriever.retrieve("visa requirements", category="immigration", k=10)
        # All returned chunks should belong to the requested category (or fall back)
        categories  = {c.category for c in chunks_imm}
        assert "immigration" in categories

    def test_relevance_scores_are_floats(self, retriever):
        chunks = retriever.retrieve("NHS dental treatment costs", k=5)
        assert all(isinstance(c.relevance_score, float) for c in chunks)

    def test_chunk_count_matches_index(self, retriever):
        assert retriever.chunk_count == 3734
