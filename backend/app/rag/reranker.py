from __future__ import annotations

from typing import List

import torch
from loguru import logger

from app.config import settings
from app.models import SourceChunk


class CrossEncoderReranker:
    """
    Cross-encoder reranker using ms-marco-MiniLM-L-6-v2.

    * Uses GPU if available, falls back to CPU.
    * Model is loaded lazily on first rerank() call.
    * Returns a new list of SourceChunks with updated relevance_score values.
    """

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.reranker_model
        self.device     = "cuda" if torch.cuda.is_available() else "cpu"
        self._model     = None

    # ------------------------------------------------------------------
    # Lazy model loader
    # ------------------------------------------------------------------

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(
                f"Loading reranker model '{self.model_name}' on {self.device} …"
            )
            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("Reranker model loaded.")
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        chunks: List[SourceChunk],
        top_k: int = 5,
    ) -> List[SourceChunk]:
        """
        Score every (query, chunk.content) pair with the cross-encoder,
        sort descending, and return the top_k chunks with updated scores.
        """
        if not chunks:
            return chunks

        pairs  = [(query, c.content) for c in chunks]
        raw    = self.model.predict(pairs, show_progress_bar=False)

        # ms-marco cross-encoders return raw logits; sigmoid maps them to [0, 1]
        # so that relevance_score is interpretable and confidence thresholds work.
        import math
        scores = [1.0 / (1.0 + math.exp(-float(s))) for s in raw]

        ranked = sorted(
            zip(chunks, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        return [
            chunk.model_copy(update={"relevance_score": round(score, 6)})
            for chunk, score in ranked[:top_k]
        ]


# Backward-compatible alias
Reranker = CrossEncoderReranker
