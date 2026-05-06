from __future__ import annotations

import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.models import ErrorDetail, ErrorResponse

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- startup ----
    app.state.start_time = time.time()
    logger.remove()
    logger.add(
        sys.stderr,
        level="DEBUG" if settings.environment == "development" else "INFO",
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>"
        ),
    )
    logger.info("Starting UK Legal Assistant API …")
    logger.info(f"Environment : {settings.environment}")
    logger.info(f"LLM model   : {settings.groq_model}")
    logger.info(f"Index path  : {settings.index_path}")

    # Initialise the RAG pipeline (models load lazily on first query)
    from app.rag.pipeline import RAGPipeline
    app.state.pipeline = RAGPipeline()
    logger.info("RAGPipeline initialised (models load lazily on first query).")

    yield  # application runs here

    # ---- shutdown ----
    uptime = time.time() - app.state.start_time
    logger.info(f"Shutting down after {uptime:.0f}s.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="UK Legal Assistant API",
    description=(
        "A Retrieval-Augmented Generation (RAG) system for answering "
        "questions about UK law. Covers immigration, student rights, driving, "
        "employment, housing, healthcare, benefits, and criminal law. "
        "All answers are sourced from gov.uk and citizensadvice.org.uk, "
        "and include citations and a category-specific legal disclaimer.\n\n"
        "**Start here:** `GET /law/capabilities` returns a full machine-readable "
        "description of everything this API covers."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log every request with method, path, status code, and duration.
    Query parameters and body content are intentionally excluded to avoid
    logging personally identifiable information.
    """
    t0       = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - t0) * 1000

    # Skip noisy health-probe logging in production
    path = request.url.path
    if not (settings.environment == "production" and path in ("/health", "/health/ready")):
        logger.info(
            f"{request.method} {path} → {response.status_code} "
            f"({duration:.1f} ms)"
        )

    return response

# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            status="error",
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="An unexpected error occurred. Please try again.",
            ),
        ).model_dump(),
    )

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.routes import health, query  # noqa: E402 — after app is defined

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(query.router,  prefix="/law",    tags=["Legal Queries"])

# ---------------------------------------------------------------------------
# Root redirect to docs
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
