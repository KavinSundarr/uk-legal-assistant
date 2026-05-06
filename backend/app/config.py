from pydantic_settings import BaseSettings
from typing import Dict


LEGAL_CATEGORIES: Dict[str, str] = {
    "immigration": "Immigration, visas, and right to remain",
    "student":     "International student rights and visa rules",
    "driving":     "Traffic, vehicle, and driving laws",
    "employment":  "Worker rights and employment law",
    "housing":     "Tenant rights and housing law",
    "healthcare":  "NHS access and healthcare rights",
    "benefits":    "Benefits, tax, and financial support",
    "criminal":    "Police rights and criminal law",
}


class Settings(BaseSettings):
    # --- LLM ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # --- Runtime ---
    environment: str = "development"

    # --- Retrieval ---
    max_chunks: int = 5
    chunk_size: int = 200
    chunk_overlap: int = 40

    # --- Models ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Paths ---
    index_path: str = "data/index"
    raw_data_path: str = "data/raw"
    processed_data_path: str = "data/processed"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
