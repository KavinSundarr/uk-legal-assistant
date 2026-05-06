from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

import faiss
import numpy as np
from loguru import logger
from rank_bm25 import BM25Okapi

from app.config import settings
from app.rag.embedder import Embedder


class VectorIndexer:
    """
    Embeds chunks and persists a FAISS index plus a BM25 corpus to disk
    for use by the Retriever at query time.

    Artefacts written to ``index_path/``:
      faiss.index   – FAISS IndexFlatIP (inner product = cosine on normalised vecs)
      bm25.pkl      – serialised BM25Okapi model
      chunks.json   – chunk metadata list (same order as FAISS row indices)
    """

    _FAISS_FILE  = "faiss.index"
    _BM25_FILE   = "bm25.pkl"
    _CHUNKS_FILE = "chunks.json"

    def __init__(self, index_dir: str | Path | None = None):
        self.index_path = Path(index_dir or settings.index_path)
        self.index_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, chunks: List[Dict]) -> None:
        """Embed *chunks*, build FAISS + BM25 indices, and save them to disk."""
        if not chunks:
            raise ValueError("Cannot build index from an empty chunk list.")

        logger.info(f"Embedding {len(chunks)} chunks …")
        embedder = Embedder()
        texts = [c["content"] for c in chunks]
        vectors = embedder.embed_documents(texts)   # (N, dim) float32

        # FAISS — inner-product index (cosine because vecs are L2-normalised)
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        faiss.write_index(index, str(self.index_path / self._FAISS_FILE))
        logger.info(f"FAISS index saved  ({index.ntotal} vectors, dim={dim})")

        # BM25 — tokenise on whitespace
        tokenised = [t.lower().split() for t in texts]
        bm25 = BM25Okapi(tokenised)
        with open(self.index_path / self._BM25_FILE, "wb") as fh:
            pickle.dump(bm25, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("BM25 index saved")

        # Chunk metadata
        with open(self.index_path / self._CHUNKS_FILE, "w", encoding="utf-8") as fh:
            json.dump(chunks, fh, ensure_ascii=False, indent=None)
        logger.info(f"Chunk metadata saved  ({len(chunks)} entries)")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> Tuple[faiss.Index, BM25Okapi, List[Dict]]:
        """Return (faiss_index, bm25, chunks).  Raises FileNotFoundError if not built."""
        faiss_path  = self.index_path / self._FAISS_FILE
        bm25_path   = self.index_path / self._BM25_FILE
        chunks_path = self.index_path / self._CHUNKS_FILE

        for p in (faiss_path, bm25_path, chunks_path):
            if not p.exists():
                raise FileNotFoundError(
                    f"Index artefact not found: {p}. "
                    "Run `python run_indexer.py` to build the index first."
                )

        faiss_index = faiss.read_index(str(faiss_path))

        with open(bm25_path, "rb") as fh:
            bm25 = pickle.load(fh)

        with open(chunks_path, encoding="utf-8") as fh:
            chunks = json.load(fh)

        logger.debug(
            f"Index loaded: {faiss_index.ntotal} FAISS vectors, "
            f"{len(chunks)} chunks"
        )
        return faiss_index, bm25, chunks
