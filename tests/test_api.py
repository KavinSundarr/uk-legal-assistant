"""
Integration tests for the FastAPI app — the RAGPipeline is mocked so no
ML models or network calls are required.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.models import (
    QueryData,
    QueryMetadata,
    QueryResponse,
    SourceChunk,
)


# ── Shared mock pipeline ──────────────────────────────────────────────────────

def _mock_response(query: str = "test query") -> QueryResponse:
    chunk = SourceChunk(
        content="You need a certificate of sponsorship.",
        document="Skilled Worker visa: overview",
        url="https://www.gov.uk/skilled-worker-visa",
        category="immigration",
        relevance_score=0.82,
        last_updated="2024-01-01",
    )
    return QueryResponse(
        status="success",
        data=QueryData(
            answer="You need a valid job offer and a certificate of sponsorship.",
            legal_category="Immigration, visas, and right to remain",
            sources=[chunk],
            disclaimer="This information is for general guidance only.",
            seek_advice="Always consult an immigration solicitor for your specific situation.",
            confidence="high",
        ),
        metadata=QueryMetadata(
            query=query,
            category_detected="immigration",
            documents_searched=321,
            chunks_retrieved=5,
            conversation_id="test-conv-id-1234",
            latency_ms=1234.5,
        ),
    )


@pytest.fixture(scope="module")
def client():
    """
    Start the app with a mocked pipeline so that no ML models are loaded.
    Uses the context-manager form so the lifespan runs (app.state is populated).
    """
    mock_pipeline = MagicMock()
    mock_pipeline.query.side_effect = lambda req: _mock_response(req.query)

    with patch("app.rag.pipeline.RAGPipeline", return_value=mock_pipeline):
        from app.main import app
        with TestClient(app) as c:
            yield c


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_has_status_field(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_health_has_components(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data
        assert isinstance(data["components"], dict)

    def test_ready_endpoint(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_root_redirects_to_docs(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code in (301, 302, 307, 308)
        assert "/docs" in resp.headers.get("location", "")


# ── POST /law/query — validation ──────────────────────────────────────────────

class TestQueryValidation:
    def test_missing_query_returns_422(self, client):
        resp = client.post("/law/query", json={})
        assert resp.status_code == 422

    def test_query_too_short_returns_422(self, client):
        resp = client.post("/law/query", json={"query": "Too short"})
        assert resp.status_code == 422

    def test_query_too_long_returns_422(self, client):
        resp = client.post("/law/query", json={"query": "x" * 1001})
        assert resp.status_code == 422

    def test_limit_out_of_range_returns_422(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "How do I apply for a skilled worker visa?", "limit": 0},
        )
        assert resp.status_code == 422

    def test_limit_too_high_returns_422(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "How do I apply for a skilled worker visa?", "limit": 21},
        )
        assert resp.status_code == 422


# ── POST /law/query — success ─────────────────────────────────────────────────

class TestQuerySuccess:
    def test_valid_query_returns_200(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "How do I apply for a skilled worker visa?"},
        )
        assert resp.status_code == 200

    def test_response_has_status_success(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "What are the penalty points for speeding?"},
        )
        data = resp.json()
        assert data["status"] == "success"

    def test_response_has_data_fields(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "Can my landlord evict me without notice?"},
        )
        data = resp.json()["data"]
        for field in ("answer", "legal_category", "sources", "disclaimer", "seek_advice", "confidence"):
            assert field in data, f"Missing field: {field}"

    def test_response_has_metadata(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "How do I claim universal credit for the first time?"},
        )
        meta = resp.json()["metadata"]
        for field in ("query", "category_detected", "documents_searched",
                      "chunks_retrieved", "conversation_id", "latency_ms"):
            assert field in meta, f"Missing metadata field: {field}"

    def test_sources_is_list(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "My employer wants to make me redundant — what are my rights?"},
        )
        sources = resp.json()["data"]["sources"]
        assert isinstance(sources, list)

    def test_optional_category_accepted(self, client):
        resp = client.post(
            "/law/query",
            json={
                "query":    "What is a section 21 eviction notice?",
                "category": "housing",
            },
        )
        assert resp.status_code == 200

    def test_optional_conversation_id_accepted(self, client):
        resp = client.post(
            "/law/query",
            json={
                "query":           "What documents do I need for the application?",
                "conversation_id": "prev-conv-id-5678",
            },
        )
        assert resp.status_code == 200

    def test_confidence_valid_value(self, client):
        resp = client.post(
            "/law/query",
            json={"query": "I was arrested by the police — what are my rights?"},
        )
        confidence = resp.json()["data"]["confidence"]
        assert confidence in ("high", "medium", "low")


# ── POST /law/query/{category} ────────────────────────────────────────────────

class TestQueryByCategory:
    @pytest.mark.parametrize("category", [
        "immigration", "student", "driving", "employment",
        "housing", "healthcare", "benefits", "criminal",
    ])
    def test_valid_category_returns_200(self, client, category):
        resp = client.post(
            f"/law/query/{category}",
            json={"query": "What are my rights and obligations under UK law?"},
        )
        assert resp.status_code == 200

    def test_invalid_category_returns_400(self, client):
        resp = client.post(
            "/law/query/taxlaw",
            json={"query": "What are my rights and obligations under UK law?"},
        )
        assert resp.status_code == 400

    def test_invalid_category_error_message(self, client):
        resp = client.post(
            "/law/query/taxlaw",
            json={"query": "What are my rights and obligations under UK law?"},
        )
        detail = resp.json().get("detail", "")
        assert "taxlaw" in detail.lower() or "unknown" in detail.lower()

    def test_short_query_in_category_route_returns_422(self, client):
        resp = client.post(
            "/law/query/housing",
            json={"query": "short"},
        )
        assert resp.status_code == 422


# ── GET /law/categories ────────────────────────────────────────────────────────

class TestCategories:
    def test_returns_200(self, client):
        resp = client.get("/law/categories")
        assert resp.status_code == 200

    def test_has_eight_categories(self, client):
        resp = client.get("/law/categories")
        data = resp.json()
        assert data["total_categories"] == 8
        assert len(data["categories"]) == 8

    def test_category_fields(self, client):
        resp = client.get("/law/categories")
        for cat in resp.json()["categories"]:
            for field in ("key", "description", "document_count", "example_questions"):
                assert field in cat, f"Missing field '{field}' in category {cat.get('key')}"

    def test_all_known_keys_present(self, client):
        resp = client.get("/law/categories")
        keys = {c["key"] for c in resp.json()["categories"]}
        expected = {"immigration", "student", "driving", "employment",
                    "housing", "healthcare", "benefits", "criminal"}
        assert keys == expected

    def test_has_total_documents(self, client):
        resp = client.get("/law/categories")
        assert "total_documents" in resp.json()
        assert isinstance(resp.json()["total_documents"], int)


# ── POST /law/batch ────────────────────────────────────────────────────────────

class TestBatch:
    def test_valid_batch_returns_200(self, client):
        resp = client.post(
            "/law/batch",
            json={"queries": [
                {"query": "How do I apply for a skilled worker visa?"},
                {"query": "What are the penalty points for speeding?"},
            ]},
        )
        assert resp.status_code == 200

    def test_response_total_matches_input(self, client):
        queries = [
            {"query": "How do I apply for a skilled worker visa?"},
            {"query": "What are my rights when I am arrested by the police?"},
            {"query": "How do I claim universal credit for the first time?"},
        ]
        resp = client.post("/law/batch", json={"queries": queries})
        data = resp.json()
        assert data["total"] == 3

    def test_too_many_queries_returns_422(self, client):
        queries = [
            {"query": "How do I apply for a skilled worker visa?"},
        ] * 6
        resp = client.post("/law/batch", json={"queries": queries})
        assert resp.status_code == 422

    def test_empty_batch_returns_422(self, client):
        resp = client.post("/law/batch", json={"queries": []})
        assert resp.status_code == 422


# ── GET /law/capabilities ─────────────────────────────────────────────────────

class TestCapabilities:
    def test_returns_200(self, client):
        resp = client.get("/law/capabilities")
        assert resp.status_code == 200

    def test_has_name_and_version(self, client):
        data = resp = client.get("/law/capabilities").json()
        assert "name" in data
        assert "version" in data

    def test_has_endpoints(self, client):
        data = client.get("/law/capabilities").json()
        assert "endpoints" in data
        assert len(data["endpoints"]) > 0

    def test_has_index_stats(self, client):
        data = client.get("/law/capabilities").json()
        assert "index_stats" in data
        assert "total_chunks" in data["index_stats"]
