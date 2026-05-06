from __future__ import annotations

from typing import List

import numpy as np
import torch
from loguru import logger

from app.config import settings


class Embedder:
    """
    Wraps BAAI/bge-small-en-v1.5 (or any sentence-transformer) to produce
    L2-normalised dense embeddings.

    * Uses GPU automatically if available, falls back to CPU.
    * Model is loaded eagerly in __init__ so the first query has no latency spike.
    * encode() / encode_batch() always return float32 numpy arrays.
    """

    def __init__(self, model_name: str | None = None):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name or settings.embedding_model
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"Loading embedding model '{self.model_name}' on {self.device} …")
        self._model = SentenceTransformer(self.model_name, device=self.device)
        logger.info("Embedding model loaded.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, text: str) -> np.ndarray:
        """Encode a single string → (dim,) float32 L2-normalised vector."""
        return self._model.encode(
            [text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)[0]

    def encode_batch(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        """
        Encode a list of strings → (N, dim) float32 L2-normalised matrix.
        Shows a progress bar when N > 100.
        """
        return self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 100,
        ).astype(np.float32)

    # ------------------------------------------------------------------
    # Aliases kept for internal callers (indexer, retriever)
    # ------------------------------------------------------------------

    def embed_query(self, text: str) -> np.ndarray:
        return self.encode(text)

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        return self.encode_batch(texts)

    @property
    def dim(self) -> int:
        return self._model.get_sentence_embedding_dimension()
