from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query:           str           = Field(..., min_length=10, max_length=1000)
    category:        Optional[str] = None
    conversation_id: Optional[str] = None
    limit:           int           = Field(default=5, ge=1, le=20)


# ---------------------------------------------------------------------------
# Response — leaf types first, composites after
# ---------------------------------------------------------------------------

class SourceChunk(BaseModel):
    content:         str
    document:        str
    url:             str
    category:        str
    relevance_score: float
    last_updated:    str


class QueryData(BaseModel):
    answer:         str
    legal_category: str
    sources:        List[SourceChunk]
    disclaimer:     str
    seek_advice:    str
    confidence:     str   # "high" | "medium" | "low"


class QueryMetadata(BaseModel):
    query:               str
    category_detected:   str
    documents_searched:  int
    chunks_retrieved:    int
    conversation_id:     str
    latency_ms:          float


class QueryResponse(BaseModel):
    status:   str
    data:     QueryData
    metadata: QueryMetadata


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

class BatchQueryRequest(BaseModel):
    queries: List[QueryRequest] = Field(..., min_length=1, max_length=5)


class BatchQueryResponse(BaseModel):
    results: List[QueryResponse]
    total:   int
    failed:  int


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

class CategoryInfo(BaseModel):
    key:               str
    description:       str
    document_count:    int
    example_questions: List[str]


class CategoriesResponse(BaseModel):
    categories:      List[CategoryInfo]
    total_categories: int
    total_documents:  int


# ---------------------------------------------------------------------------
# Capabilities  (AI-agent-readable API description)
# ---------------------------------------------------------------------------

class EndpointInfo(BaseModel):
    method:      str
    path:        str
    description: str
    example:     Optional[Dict] = None


class CapabilitiesResponse(BaseModel):
    name:        str
    version:     str
    description: str
    sources:     List[str]
    categories:  List[CategoryInfo]
    endpoints:   List[EndpointInfo]
    index_stats: Dict


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class ComponentHealth(BaseModel):
    status: str    # "ok" | "degraded" | "unavailable"
    detail: str


class DetailedHealthResponse(BaseModel):
    status:         str    # "healthy" | "degraded" | "unhealthy"
    version:        str
    environment:    str
    uptime_seconds: float
    components:     Dict[str, ComponentHealth]


# Kept for backward-compat (health route used this)
class HealthResponse(BaseModel):
    status:      str
    version:     str
    environment: str


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------

class ConversationTurn(BaseModel):
    role:      str   # "user" | "assistant"
    content:   str
    timestamp: str   # ISO-8601


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    code:    str
    message: str
    field:   Optional[str] = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error:  ErrorDetail


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestRequest(BaseModel):
    urls:          Optional[List[str]] = None
    force_reindex: bool                = False
