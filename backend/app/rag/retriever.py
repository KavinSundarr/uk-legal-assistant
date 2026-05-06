from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from loguru import logger

from app.config import settings
from app.models import SourceChunk


class HybridRetriever:
    """
    Hybrid retriever: dense FAISS search + sparse BM25, fused with RRF.

    Index artefacts are loaded lazily on the first retrieve() call so that
    the API can start without a built index (it will return a 503 instead).
    """

    _RRF_K = 60  # standard RRF smoothing constant

    def __init__(self, index_dir: str | Path | None = None):
        self._index_dir = Path(index_dir or settings.index_path)
        self._faiss_index = None
        self._bm25        = None
        self._chunks: List[Dict] = []
        self._embedder    = None
        self._loaded      = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def chunk_count(self) -> int:
        self._ensure_loaded()
        return len(self._chunks)

    def dense_search(
        self, query_vector: np.ndarray, k: int = 20
    ) -> List[Tuple[int, float]]:
        """FAISS inner-product search.  Returns [(chunk_idx, score), ...]."""
        self._ensure_loaded()
        vec = query_vector.reshape(1, -1).astype(np.float32)
        scores, indices = self._faiss_index.search(vec, k)
        return [
            (int(idx), float(score))
            for idx, score in zip(indices[0], scores[0])
            if idx >= 0
        ]

    def sparse_search(
        self, query_tokens: List[str], k: int = 20
    ) -> List[Tuple[int, float]]:
        """BM25 search.  Returns [(chunk_idx, score), ...]."""
        self._ensure_loaded()
        scores = self._bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:k]
        return [(int(i), float(scores[i])) for i in top_indices]

    def rrf_fusion(
        self,
        dense_results:  List[Tuple[int, float]],
        sparse_results: List[Tuple[int, float]],
        k: int = 60,
    ) -> List[Tuple[int, float]]:
        """
        Reciprocal Rank Fusion.
        score(d) = Σ  1 / (k + rank_i(d))
        Returns [(chunk_idx, fused_score), ...] sorted descending.
        """
        fused: Dict[int, float] = {}
        for rank, (idx, _) in enumerate(dense_results):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
        for rank, (idx, _) in enumerate(sparse_results):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
        return sorted(fused.items(), key=lambda x: x[1], reverse=True)

    def filter_by_category(
        self,
        results: List[Tuple[int, float]],
        category: str,
    ) -> List[Tuple[int, float]]:
        """Keep only results whose chunk metadata matches *category*."""
        filtered = [
            (idx, score)
            for idx, score in results
            if self._chunks[idx].get("category") == category
        ]
        return filtered if filtered else results  # fall back to unfiltered

    def retrieve(
        self,
        query: str,
        category: Optional[str] = None,
        k: int = 20,
    ) -> List[SourceChunk]:
        """
        Full hybrid retrieval pipeline:
          1. Embed query with BGE
          2. Dense FAISS search (k*3 candidates)
          3. BM25 sparse search (k*3 candidates)
          4. RRF fusion
          5. Optional category filter
          6. Return top-k SourceChunk objects
        """
        self._ensure_loaded()
        pool = k * 3

        query_vector = self._embedder.encode(query)
        query_tokens = query.lower().split()

        dense_res  = self.dense_search(query_vector, k=pool)
        sparse_res = self.sparse_search(query_tokens, k=pool)
        fused      = self.rrf_fusion(dense_res, sparse_res)

        if category:
            fused = self.filter_by_category(fused, category)

        return [self._to_source_chunk(idx, score) for idx, score in fused[:k]]

    # ------------------------------------------------------------------
    # Lazy index loader
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return

        from app.ingestion.indexer import VectorIndexer
        from app.rag.embedder import Embedder

        self._faiss_index, self._bm25, self._chunks = (
            VectorIndexer(index_dir=self._index_dir).load()
        )
        self._embedder = Embedder()
        self._loaded   = True
        logger.info(
            f"HybridRetriever loaded: {len(self._chunks)} chunks, "
            f"{self._faiss_index.ntotal} FAISS vectors"
        )

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _to_source_chunk(self, idx: int, score: float) -> SourceChunk:
        c = self._chunks[idx]
        return SourceChunk(
            content=c.get("content", ""),
            document=c.get("title", ""),
            url=c.get("url", ""),
            category=c.get("category", ""),
            relevance_score=round(score, 6),
            last_updated=c.get("last_modified", ""),
        )


# Backward-compatible alias so existing imports don't break
Retriever = HybridRetriever
