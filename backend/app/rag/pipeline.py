from __future__ import annotations

import time
from typing import Dict, List, Optional

from loguru import logger

from app.config import LEGAL_CATEGORIES, settings
from app.models import (
    QueryData,
    QueryMetadata,
    QueryRequest,
    QueryResponse,
)
from app.rag.generator import GroqGenerator
from app.rag.memory import ConversationMemory
from app.rag.reranker import CrossEncoderReranker
from app.rag.retriever import HybridRetriever
from app.utils.disclaimer import get_disclaimer, get_seek_advice

# ---------------------------------------------------------------------------
# Keyword catalogue for category detection
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "immigration": [
        "visa", "passport", "leave", "remain", "ukvi", "immigration",
        "asylum", "refugee", "biometric", "residence permit", "tier",
        "skilled worker", "points-based", "deportation", "entry clearance",
        "right to remain", "indefinite leave", "naturalisation", "citizenship",
        "eea", "settled status", "pre-settled", "brp", "biometric residence",
        "sponsor", "certificate of sponsorship", "work permit",
    ],
    "student": [
        "student visa", "student route", "university", "college", "tuition",
        "international student", "studying uk", "study permit", "cas",
        "confirmation of acceptance", "student finance", "maintenance funds",
        "academic progress", "attendance monitoring", "term time", "ucas",
        "postgraduate", "phd", "master", "undergraduate", "enrolment",
        # cross-category: overlap with healthcare / benefits / housing queries
        "tier 4", "study", "graduate visa", "ukcisa", "20 hours",
        "student loan", "tuition fee", "council tax student",
    ],
    "driving": [
        "driving licence", "licence", "speeding", "speed", "mot", "insurance",
        "dvla", "road tax", "vehicle", "penalty points", "ban", "disqualified",
        "drink drive", "drug drive", "careless driving", "dangerous driving",
        "highway code", "theory test", "practical test", "provisional",
        "tachograph", "hgv", "lgv", "pcn", "parking fine", "clamped",
    ],
    "employment": [
        "salary", "wage", "fired", "dismissed", "redundancy", "contract",
        "employment", "employer", "employee", "holiday pay", "sick pay",
        "maternity", "paternity", "discrimination", "unfair dismissal",
        "tribunal", "acas", "zero hours", "minimum wage", "national living wage",
        "notice period", "settlement", "grievance", "disciplinary",
        "constructive dismissal", "self-employed", "ir35",
        # cross-category: work visa / work rights overlaps
        "employment rights", "work rights", "right to work",
    ],
    "housing": [
        "rent", "tenant", "landlord", "eviction", "section 21", "section 8",
        "deposit", "tenancy", "lease", "housing", "council house",
        "social housing", "homeless", "homelessness", "repossession",
        "mortgage", "shared ownership", "right to buy", "housing benefit",
        "universal credit housing", "disrepair", "mould", "damp",
        "shelter", "notice to quit",
        # cross-category: student + housing overlap
        "council tax", "student accommodation", "halls of residence",
    ],
    "healthcare": [
        "nhs", "doctor", "gp", "hospital", "prescription", "treatment",
        "healthcare", "medical", "dentist", "optician", "mental health",
        "social care", "care home", "carer", "disability", "complaint",
        "pals", "clinical negligence", "medical negligence", "waiting list",
        "referral", "overseas visitor", "health surcharge",
        # cross-category: student + NHS / entitlement overlaps
        "health", "entitle", "free treatment", "nhs surcharge",
        "nhs treatment", "free nhs", "medical care",
    ],
    "benefits": [
        "benefit", "universal credit", "esa", "pip", "dla", "jsa",
        "jobseeker", "housing benefit", "council tax support", "child benefit",
        "working tax credit", "child tax credit", "pension credit",
        "attendance allowance", "carer's allowance", "statutory sick pay",
        "maternity allowance", "bereavement", "appeal", "sanction",
        "dwp", "hmrc", "tax credit", "free school meals",
        # cross-category: student + benefits overlap
        "council tax exemption", "council tax reduction",
    ],
    "criminal": [
        "arrest", "police", "crime", "criminal", "court", "conviction",
        "sentence", "probation", "parole", "solicitor", "defendant",
        "charge", "prosecution", "magistrate", "crown court", "jury",
        "bail", "caution", "penalty", "fine", "community service",
        "restraining order", "injunction", "discrimination", "assault",
        "theft", "fraud", "rights", "stop and search",
    ],
}


class RAGPipeline:
    """
    Full RAG pipeline:
    detect_category → retrieve → rerank → generate → build response.

    All heavy components (embedding model, reranker, Groq client) are
    initialised lazily so the API starts instantly without a built index.
    """

    def __init__(self) -> None:
        self.retriever = HybridRetriever()
        self.reranker  = CrossEncoderReranker()
        self.generator = GroqGenerator()
        self.memory    = ConversationMemory()

    # ------------------------------------------------------------------
    # Category detection
    # ------------------------------------------------------------------

    # Minimum keyword-match score required to apply a category filter.
    # Queries that match fewer keywords than this threshold are treated as
    # ambiguous and fall back to unconstrained (cross-category) retrieval.
    _CATEGORY_MIN_SCORE = 2

    def detect_category(self, query: str) -> Optional[str]:
        """
        Return the best-matching legal category for *query* or None.

        Scoring: one point per keyword that appears in the lowercased query
        (multi-word keywords count as one point, same as single words).

        Falls back to None (unconstrained retrieval) when:
          - no keyword matches at all
          - the top score is below _CATEGORY_MIN_SCORE (too uncertain)
          - two or more categories share the top score (tie)
        """
        query_lower = query.lower()
        scores: Dict[str, int] = {}

        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in query_lower)
            if score:
                scores[category] = score

        if not scores:
            logger.debug("Category detection: no keyword matches — unconstrained retrieval")
            return None

        best_score = max(scores.values())

        if best_score < self._CATEGORY_MIN_SCORE:
            logger.debug(
                f"Category detection: top score {best_score} < {self._CATEGORY_MIN_SCORE}"
                f" (scores={scores}) — uncertain, unconstrained retrieval"
            )
            return None

        winners = [cat for cat, s in scores.items() if s == best_score]

        if len(winners) > 1:
            logger.debug(
                f"Category detection: tie between {winners}"
                f" (score={best_score}, all scores={scores})"
                " — unconstrained retrieval"
            )
            return None

        best = winners[0]
        logger.debug(
            f"Category detected: '{best}' (score={best_score}, all scores={scores})"
        )
        return best

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def query(self, request: QueryRequest) -> QueryResponse:
        """
        Full pipeline:
          1. Detect category (if not supplied)
          2. Get conversation history
          3. Hybrid retrieval with optional category filter
          4. Cross-encoder reranking
          5. LLM answer generation
          6. Store turn in memory
          7. Build and return QueryResponse
        """
        t0 = time.monotonic()

        # 1. Category
        category = request.category or self.detect_category(request.query)

        # 2. Conversation history
        conversation_id = (
            request.conversation_id or self.memory.generate_conversation_id()
        )
        history = self.memory.get_history(conversation_id, max_turns=5)

        logger.info(
            f"query='{request.query[:60]}…' | "
            f"category={category} | conv={conversation_id[:8]}"
        )

        # 3. Retrieve
        fetch_k = (request.limit or settings.max_chunks) * 3
        chunks = self.retriever.retrieve(
            request.query,
            category=category,
            k=fetch_k,
        )
        logger.debug(f"Retrieved {len(chunks)} chunks before reranking")

        # 4. Rerank
        top_n  = request.limit or settings.max_chunks
        chunks = self.reranker.rerank(request.query, chunks, top_k=top_n)
        logger.debug(
            f"Reranked to {len(chunks)} chunks — "
            f"top score: {chunks[0].relevance_score if chunks else 'n/a'}"
        )

        # 5. Generate
        # Convert get_history turns to the format generator expects
        history_for_gen = [
            {"role": t["role"], "content": t["content"]} for t in history
        ]
        answer = self.generator.generate(request.query, chunks, history_for_gen)

        # 6. Store turn
        self.memory.add_turn(conversation_id, "user",      request.query)
        self.memory.add_turn(conversation_id, "assistant", answer)

        # 7. Build response
        latency_ms = round((time.monotonic() - t0) * 1000, 2)
        detected_category = category or (chunks[0].category if chunks else "general")

        logger.info(f"Pipeline complete in {latency_ms:.0f} ms")

        return QueryResponse(
            status="success",
            data=QueryData(
                answer=answer,
                legal_category=LEGAL_CATEGORIES.get(
                    detected_category, detected_category.title()
                ),
                sources=chunks,
                disclaimer=get_disclaimer(detected_category),
                seek_advice=get_seek_advice(detected_category),
                confidence=self._confidence(chunks),
            ),
            metadata=QueryMetadata(
                query=request.query,
                category_detected=detected_category,
                documents_searched=self.retriever.chunk_count,
                chunks_retrieved=len(chunks),
                conversation_id=conversation_id,
                latency_ms=latency_ms,
            ),
        )

    # Keep run() as an alias so the route handler doesn't need changing
    def run(self, request: QueryRequest) -> QueryResponse:
        return self.query(request)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _confidence(chunks) -> str:
        if not chunks:
            return "low"
        top = chunks[0].relevance_score
        if top >= 0.7:
            return "high"
        if top >= 0.4:
            return "medium"
        return "low"
