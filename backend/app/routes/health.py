from __future__ import annotations

import time
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Request
from loguru import logger

from app.config import LEGAL_CATEGORIES, settings
from app.models import ComponentHealth, DetailedHealthResponse, HealthResponse

router = APIRouter()

_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Component probes
# ---------------------------------------------------------------------------

def _probe_index() -> ComponentHealth:
    """Check that all three index artefacts exist on disk."""
    index_dir = Path(settings.index_path)
    required  = ["faiss.index", "bm25.pkl", "chunks.json"]
    missing   = [f for f in required if not (index_dir / f).exists()]
    if missing:
        return ComponentHealth(
            status="unavailable",
            detail=f"Missing artefacts: {', '.join(missing)}. Run run_indexer.py.",
        )
    return ComponentHealth(status="ok", detail=f"Index at {index_dir}")


def _probe_groq() -> ComponentHealth:
    """Check Groq API key is configured (no live call — avoids latency/cost)."""
    if not settings.groq_api_key or settings.groq_api_key == "your_groq_api_key_here":
        return ComponentHealth(
            status="unavailable",
            detail="GROQ_API_KEY not set in environment.",
        )
    return ComponentHealth(
        status="ok",
        detail=f"Groq key present, model={settings.groq_model}",
    )


def _probe_pipeline(request: Request) -> ComponentHealth:
    """Check whether the pipeline singleton is loaded on app.state."""
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        return ComponentHealth(status="unavailable", detail="Pipeline not initialised.")
    return ComponentHealth(status="ok", detail="RAGPipeline ready.")


def _overall_status(components: Dict[str, ComponentHealth]) -> str:
    statuses = {c.status for c in components.values()}
    if statuses == {"ok"}:
        return "healthy"
    if "ok" in statuses:
        return "degraded"
    return "unhealthy"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=DetailedHealthResponse,
    summary="Component health check",
    tags=["health"],
)
async def health_check(request: Request) -> DetailedHealthResponse:
    """
    Returns the health status of every system component.

    * **healthy** — all components operational.
    * **degraded** — some components unavailable; partial service possible.
    * **unhealthy** — critical components down; queries will fail.
    """
    components: Dict[str, ComponentHealth] = {
        "index":    _probe_index(),
        "groq_api": _probe_groq(),
        "pipeline": _probe_pipeline(request),
    }

    overall = _overall_status(components)
    uptime  = time.time() - getattr(request.app.state, "start_time", time.time())

    logger.debug(f"Health check: {overall}")

    return DetailedHealthResponse(
        status=overall,
        version=_VERSION,
        environment=settings.environment,
        uptime_seconds=round(uptime, 1),
        components=components,
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Kubernetes-style readiness probe",
    tags=["health"],
)
async def readiness(request: Request) -> HealthResponse:
    """
    Lightweight readiness probe.  Returns ``status: ok`` only when the
    index is present *and* a Groq key is configured.
    """
    index_ok = _probe_index().status == "ok"
    groq_ok  = _probe_groq().status  == "ok"

    status = "ok" if (index_ok and groq_ok) else "not_ready"
    return HealthResponse(
        status=status,
        version=_VERSION,
        environment=settings.environment,
    )
