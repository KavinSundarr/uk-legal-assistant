from datetime import datetime
from typing import Dict


def build_chunk_metadata(
    source_url: str,
    title: str,
    chunk_index: int,
    total_chunks: int,
) -> Dict:
    return {
        "source_url": source_url,
        "title": title,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "indexed_at": datetime.utcnow().isoformat(),
    }


def format_source_citation(metadata: Dict) -> str:
    # TODO: return a human-readable citation string from metadata
    raise NotImplementedError
