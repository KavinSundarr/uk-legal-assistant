"""
Tests for RAGPipeline — Groq and heavy ML components are mocked so the suite
runs without network access or GPU.
"""

import pytest
from unittest.mock import MagicMock, patch

from app.models import QueryRequest, SourceChunk
from app.rag.pipeline import RAGPipeline, _CATEGORY_KEYWORDS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_chunk(category="immigration", score=0.8) -> SourceChunk:
    return SourceChunk(
        content="Applicants must provide evidence of their qualifications.",
        document="Skilled Worker visa: overview",
        url="https://www.gov.uk/skilled-worker-visa",
        category=category,
        relevance_score=score,
        last_updated="2024-01-01",
    )


def _make_pipeline() -> RAGPipeline:
    """Return a RAGPipeline with all heavy components replaced by mocks."""
    p = RAGPipeline.__new__(RAGPipeline)

    p.retriever = MagicMock()
    p.retriever.retrieve.return_value = [_make_chunk()]
    p.retriever.chunk_count = 321

    p.reranker = MagicMock()
    p.reranker.rerank.return_value = [_make_chunk(score=0.85)]

    p.generator = MagicMock()
    p.generator.generate.return_value = (
        "You need to meet points requirements and have a valid job offer."
    )

    from app.rag.memory import ConversationMemory
    p.memory = ConversationMemory()

    return p


# ── Category detection ────────────────────────────────────────────────────────

class TestDetectCategory:
    """detect_category() must correctly classify queries for all 8 domains."""

    @pytest.fixture(scope="class")
    def pipeline(self):
        return _make_pipeline()

    @pytest.mark.parametrize("query,expected", [
        ("How do I apply for a skilled worker visa?",               "immigration"),
        ("I want to get indefinite leave to remain in the UK",      "immigration"),
        ("Can I work part-time on my student visa?",                "student"),
        ("What are the English language requirements for student route?", "student"),
        ("How many penalty points before I lose my driving licence?", "driving"),
        ("What happens if I drive without car insurance?",          "driving"),
        ("My employer wants to make me redundant — what are my rights?", "employment"),
        ("What is the minimum wage in the UK?",                     "employment"),
        ("My landlord is trying to evict me with a section 21 notice", "housing"),
        ("How much deposit can a landlord legally ask for?",        "housing"),
        ("Am I entitled to free NHS treatment as a foreign national?", "healthcare"),
        ("How do I make a complaint about NHS treatment?",          "healthcare"),
        ("How do I claim universal credit for the first time?",     "benefits"),
        ("Can I appeal a PIP decision from DWP?",                   "benefits"),
        ("I was arrested by the police — what are my rights?",      "criminal"),
        ("What happens at a magistrates court hearing?",            "criminal"),
    ])
    def test_detects_category(self, pipeline, query, expected):
        detected = pipeline.detect_category(query)
        assert detected == expected, (
            f"Query '{query}' → expected '{expected}', got '{detected}'"
        )

    def test_returns_none_for_unrelated(self, pipeline):
        detected = pipeline.detect_category("What is the weather like today?")
        assert detected is None

    def test_student_beats_immigration_for_student_visa(self, pipeline):
        """'student visa' (2-word phrase) should outscore plain 'visa' (1 word)."""
        detected = pipeline.detect_category("How do I apply for a student visa?")
        assert detected == "student"

    def test_all_categories_have_keywords(self):
        from app.config import LEGAL_CATEGORIES
        for cat in LEGAL_CATEGORIES:
            assert cat in _CATEGORY_KEYWORDS, f"Missing keywords for category '{cat}'"
            assert len(_CATEGORY_KEYWORDS[cat]) >= 5


# ── Full pipeline.query() ─────────────────────────────────────────────────────

class TestPipelineQuery:
    @pytest.fixture(scope="class")
    def pipeline(self):
        return _make_pipeline()

    def test_returns_query_response(self, pipeline):
        from app.models import QueryResponse
        req  = QueryRequest(query="How do I apply for a skilled worker visa?")
        resp = pipeline.query(req)
        assert isinstance(resp, QueryResponse)
        assert resp.status == "success"

    def test_answer_is_string(self, pipeline):
        req  = QueryRequest(query="What are the penalty points for speeding?")
        resp = pipeline.query(req)
        assert isinstance(resp.data.answer, str)
        assert len(resp.data.answer) > 0

    def test_sources_list(self, pipeline):
        req  = QueryRequest(query="How much deposit can a landlord ask for?")
        resp = pipeline.query(req)
        assert isinstance(resp.data.sources, list)
        assert len(resp.data.sources) > 0
        assert all(isinstance(s, SourceChunk) for s in resp.data.sources)

    def test_disclaimer_is_present(self, pipeline):
        req  = QueryRequest(query="What is the minimum wage?")
        resp = pipeline.query(req)
        assert isinstance(resp.data.disclaimer, str)
        assert len(resp.data.disclaimer) > 10

    def test_seek_advice_is_present(self, pipeline):
        req  = QueryRequest(query="I was arrested — what are my rights?")
        resp = pipeline.query(req)
        assert isinstance(resp.data.seek_advice, str)
        assert len(resp.data.seek_advice) > 5

    def test_metadata_has_required_fields(self, pipeline):
        req  = QueryRequest(query="How do I claim universal credit?")
        resp = pipeline.query(req)
        meta = resp.metadata
        assert meta.query == req.query
        assert meta.documents_searched == 321
        assert meta.chunks_retrieved > 0
        assert isinstance(meta.conversation_id, str)
        assert len(meta.conversation_id) > 0
        assert meta.latency_ms > 0

    def test_conversation_id_persists(self, pipeline):
        req1 = QueryRequest(query="How do I apply for a skilled worker visa?")
        res1 = pipeline.query(req1)
        cid  = res1.metadata.conversation_id

        req2 = QueryRequest(
            query="What documents do I need for that application?",
            conversation_id=cid,
        )
        res2 = pipeline.query(req2)
        assert res2.metadata.conversation_id == cid

    def test_category_passed_through(self, pipeline):
        req  = QueryRequest(
            query="What are my rights when I am arrested by the police?",
            category="criminal",
        )
        resp = pipeline.query(req)
        # Retriever must have been called with the forced category
        pipeline.retriever.retrieve.assert_called()
        call_kwargs = pipeline.retriever.retrieve.call_args
        assert call_kwargs.kwargs.get("category") == "criminal" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "criminal"
        )

    def test_limit_forwarded_to_reranker(self, pipeline):
        pipeline.reranker.rerank.reset_mock()
        req  = QueryRequest(query="Skilled worker visa requirements UK", limit=3)
        pipeline.query(req)
        call_kwargs = pipeline.reranker.rerank.call_args
        top_k = (
            call_kwargs.kwargs.get("top_k")
            or (call_kwargs.args[2] if len(call_kwargs.args) > 2 else None)
        )
        assert top_k == 3


# ── Confidence scoring ────────────────────────────────────────────────────────

class TestConfidenceScoring:
    def test_high_confidence(self):
        chunks = [_make_chunk(score=0.75), _make_chunk(score=0.6)]
        assert RAGPipeline._confidence(chunks) == "high"

    def test_medium_confidence(self):
        chunks = [_make_chunk(score=0.55), _make_chunk(score=0.4)]
        assert RAGPipeline._confidence(chunks) == "medium"

    def test_low_confidence_score(self):
        chunks = [_make_chunk(score=0.3)]
        assert RAGPipeline._confidence(chunks) == "low"

    def test_low_confidence_no_chunks(self):
        assert RAGPipeline._confidence([]) == "low"


# ── Disclaimer content ────────────────────────────────────────────────────────

class TestDisclaimers:
    @pytest.mark.parametrize("category,expected_fragment", [
        ("immigration", "UKVI"),
        ("employment",  "ACAS"),
        ("housing",     "Shelter"),
        ("healthcare",  "NHS"),
        ("benefits",    "Citizens Advice"),
        ("criminal",    "solicitor"),
        ("driving",     "DVLA"),
        ("student",     "UKVI"),
    ])
    def test_category_disclaimer_contains_fragment(self, category, expected_fragment):
        from app.utils.disclaimer import get_disclaimer
        disclaimer = get_disclaimer(category)
        assert expected_fragment.lower() in disclaimer.lower(), (
            f"Disclaimer for '{category}' should mention '{expected_fragment}'"
        )

    def test_fallback_disclaimer_is_not_empty(self):
        from app.utils.disclaimer import get_disclaimer
        disclaimer = get_disclaimer(None)
        assert len(disclaimer) > 20

    @pytest.mark.parametrize("category", [
        "immigration", "employment", "housing", "healthcare",
        "benefits", "criminal", "driving", "student",
    ])
    def test_seek_advice_not_empty(self, category):
        from app.utils.disclaimer import get_seek_advice
        advice = get_seek_advice(category)
        assert isinstance(advice, str) and len(advice) > 5
