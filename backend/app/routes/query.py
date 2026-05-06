from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from app.config import LEGAL_CATEGORIES, settings
from app.models import (
    BatchQueryRequest,
    BatchQueryResponse,
    CapabilitiesResponse,
    CategoriesResponse,
    CategoryInfo,
    EndpointInfo,
    QueryRequest,
    QueryResponse,
)
from app.rag.pipeline import RAGPipeline

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependency — shared pipeline from app.state
# ---------------------------------------------------------------------------

def _get_pipeline(request: Request) -> RAGPipeline:
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised — server is still starting.")
    return pipeline


# ---------------------------------------------------------------------------
# Per-category example questions  (static — no DB needed)
# ---------------------------------------------------------------------------

_EXAMPLES: dict[str, list[str]] = {
    "immigration": [
        "How do I apply for a Skilled Worker visa?",
        "What documents do I need for indefinite leave to remain?",
        "How long can I stay in the UK on a visitor visa?",
    ],
    "student": [
        "What are the English language requirements for a Student visa?",
        "How much money do I need to show for a Student visa?",
        "Can I work part-time on a Student visa?",
    ],
    "driving": [
        "How many penalty points before I lose my licence?",
        "What are the rules for driving without insurance?",
        "How do I appeal a driving ban?",
    ],
    "employment": [
        "What is the minimum notice period my employer must give me?",
        "Can my employer make me redundant without warning?",
        "What are my rights to statutory sick pay?",
    ],
    "housing": [
        "What is a Section 21 eviction notice?",
        "How much deposit can my landlord legally ask for?",
        "What can I do if my landlord won't return my deposit?",
    ],
    "healthcare": [
        "Am I entitled to free NHS treatment?",
        "How do I make a complaint about NHS treatment?",
        "What is the NHS health surcharge for visa applicants?",
    ],
    "benefits": [
        "How do I claim Universal Credit?",
        "What is the two-child benefit cap?",
        "Can I appeal a PIP decision?",
    ],
    "criminal": [
        "What are my rights when arrested by the police?",
        "Do I have to answer police questions without a solicitor?",
        "What happens at a first magistrates court hearing?",
    ],
}


def _get_doc_counts() -> dict[str, int]:
    """Count chunks per category from chunks.json if the index exists."""
    chunks_path = Path(settings.index_path) / "chunks.json"
    if not chunks_path.exists():
        return {k: 0 for k in LEGAL_CATEGORIES}
    try:
        chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        counts: dict[str, int] = {k: 0 for k in LEGAL_CATEGORIES}
        for chunk in chunks:
            cat = chunk.get("category", "")
            if cat in counts:
                counts[cat] += 1
        return counts
    except Exception:
        return {k: 0 for k in LEGAL_CATEGORIES}


def _build_category_list(doc_counts: dict[str, int] | None = None) -> list[CategoryInfo]:
    if doc_counts is None:
        doc_counts = _get_doc_counts()
    return [
        CategoryInfo(
            key=key,
            description=desc,
            document_count=doc_counts.get(key, 0),
            example_questions=_EXAMPLES.get(key, []),
        )
        for key, desc in LEGAL_CATEGORIES.items()
    ]


# ---------------------------------------------------------------------------
# POST /law/query
# ---------------------------------------------------------------------------

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Ask a UK legal question",
    responses={
        503: {"description": "Index not built — run run_indexer.py first"},
        500: {"description": "Internal pipeline error"},
    },
)
async def query_legal(
    request:  QueryRequest,
    pipeline: RAGPipeline = Depends(_get_pipeline),
) -> QueryResponse:
    """
    Submit a natural-language legal question and receive a RAG-generated
    answer with cited sources, a category-specific disclaimer, and confidence
    level.

    **Query length:** 10 – 1 000 characters.

    **Conversation continuity:** pass `conversation_id` from a previous
    response to maintain multi-turn context (up to 5 recent turns).
    """
    logger.info(
        f"POST /law/query | len={len(request.query)} | "
        f"category={request.category} | conv={request.conversation_id}"
    )
    try:
        return pipeline.query(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("Pipeline error in /law/query")
        raise HTTPException(status_code=500, detail="Internal pipeline error")


# ---------------------------------------------------------------------------
# POST /law/query/{category}
# ---------------------------------------------------------------------------

@router.post(
    "/query/{category}",
    response_model=QueryResponse,
    summary="Ask a question in a specific legal category",
    responses={
        400: {"description": "Invalid category"},
        503: {"description": "Index not built"},
    },
)
async def query_legal_category(
    category: str,
    request:  QueryRequest,
    http_req: Request,
) -> QueryResponse:
    """
    Same as `POST /law/query` but **forces** the retrieval to a specific
    legal category.  Useful when you already know the domain.

    **Valid categories:** immigration, student, driving, employment,
    housing, healthcare, benefits, criminal.
    """
    # Validate category before touching the pipeline
    if category not in LEGAL_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown category '{category}'. "
                f"Valid choices: {', '.join(sorted(LEGAL_CATEGORIES))}."
            ),
        )
    pipeline = _get_pipeline(http_req)
    request  = request.model_copy(update={"category": category})
    logger.info(
        f"POST /law/query/{category} | len={len(request.query)} | "
        f"conv={request.conversation_id}"
    )
    try:
        return pipeline.query(request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Pipeline error in /law/query/{category}")
        raise HTTPException(status_code=500, detail="Internal pipeline error")


# ---------------------------------------------------------------------------
# GET /law/categories
# ---------------------------------------------------------------------------

@router.get(
    "/categories",
    response_model=CategoriesResponse,
    summary="List all legal categories",
)
async def list_categories() -> CategoriesResponse:
    """
    Return all eight legal categories the assistant covers, together with
    a description, the number of indexed document chunks, and three example
    questions for each.
    """
    doc_counts  = _get_doc_counts()
    categories  = _build_category_list(doc_counts)
    total_docs  = sum(doc_counts.values())
    return CategoriesResponse(
        categories=categories,
        total_categories=len(categories),
        total_documents=total_docs,
    )


# ---------------------------------------------------------------------------
# POST /law/batch
# ---------------------------------------------------------------------------

@router.post(
    "/batch",
    response_model=BatchQueryResponse,
    summary="Run up to 5 queries in a single request",
    responses={
        400: {"description": "More than 5 queries submitted"},
    },
)
async def batch_query(
    batch:    BatchQueryRequest,
    pipeline: RAGPipeline = Depends(_get_pipeline),
) -> BatchQueryResponse:
    """
    Accept a list of **1 – 5** `QueryRequest` objects and return a
    `QueryResponse` for each.  Failed queries are replaced with a
    placeholder response; the `failed` counter in the response tells you
    how many did not succeed.

    Queries run sequentially to respect Groq rate limits.
    """
    results: list[QueryResponse] = []
    failed  = 0

    logger.info(f"POST /law/batch | count={len(batch.queries)}")

    for i, qreq in enumerate(batch.queries):
        try:
            results.append(pipeline.query(qreq))
        except Exception as exc:
            logger.warning(f"Batch item {i} failed: {exc}")
            failed += 1
            # Placeholder so index alignment is preserved
            from app.models import QueryData, QueryMetadata
            results.append(
                QueryResponse(
                    status="error",
                    data=QueryData(
                        answer=f"Query failed: {exc}",
                        legal_category="unknown",
                        sources=[],
                        disclaimer="",
                        seek_advice="",
                        confidence="low",
                    ),
                    metadata=QueryMetadata(
                        query=qreq.query,
                        category_detected="unknown",
                        documents_searched=0,
                        chunks_retrieved=0,
                        conversation_id="",
                        latency_ms=0.0,
                    ),
                )
            )

    return BatchQueryResponse(results=results, total=len(results), failed=failed)


# ---------------------------------------------------------------------------
# GET /law/capabilities  (AI-agent-readable API manifest)
# ---------------------------------------------------------------------------

@router.get(
    "/capabilities",
    response_model=CapabilitiesResponse,
    summary="Machine-readable API capabilities manifest",
)
async def capabilities() -> CapabilitiesResponse:
    """
    A structured description of everything this API can do, intended for
    consumption by AI agents and API clients that need to understand the
    system before using it.

    Returns: covered legal domains, available endpoints, index statistics,
    and example queries per category.
    """
    doc_counts = _get_doc_counts()
    total_docs = sum(doc_counts.values())

    endpoints = [
        EndpointInfo(
            method="POST",
            path="/law/query",
            description="Ask any UK legal question. Returns answer, sources, disclaimer, and confidence.",
            example={"query": "How do I apply for a Skilled Worker visa?", "limit": 5},
        ),
        EndpointInfo(
            method="POST",
            path="/law/query/{category}",
            description="Same as /law/query but restricts retrieval to a specific legal category.",
            example={"category": "immigration", "query": "What documents do I need for ILR?"},
        ),
        EndpointInfo(
            method="GET",
            path="/law/categories",
            description="List all supported legal categories with document counts and example questions.",
        ),
        EndpointInfo(
            method="POST",
            path="/law/batch",
            description="Submit up to 5 queries in one request. Useful for bulk lookups.",
            example={"queries": [{"query": "What is a Section 21 notice?"}, {"query": "What is the NLW?"}]},
        ),
        EndpointInfo(
            method="GET",
            path="/health",
            description="Detailed component health check (index, Groq API, pipeline).",
        ),
    ]

    return CapabilitiesResponse(
        name="UK Legal Assistant API",
        version="0.1.0",
        description=(
            "A Retrieval-Augmented Generation (RAG) system that answers questions "
            "about UK law using authoritative sources from gov.uk and "
            "citizensadvice.org.uk. Covers eight legal domains: immigration, "
            "student rights, driving, employment, housing, healthcare, benefits, "
            "and criminal law. All answers cite their sources and include a "
            "category-specific legal disclaimer."
        ),
        sources=[
            "https://www.gov.uk (UK Government — official legislation & guidance)",
            "https://www.citizensadvice.org.uk (Citizens Advice — practical legal help)",
        ],
        categories=_build_category_list(doc_counts),
        endpoints=endpoints,
        index_stats={
            "total_chunks":      total_docs,
            "embedding_model":   settings.embedding_model,
            "reranker_model":    settings.reranker_model,
            "llm_model":         settings.groq_model,
            "chunk_size_words":  settings.chunk_size,
            "chunk_overlap":     settings.chunk_overlap,
        },
    )
