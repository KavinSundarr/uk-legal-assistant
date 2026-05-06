# UK Legal Assistant

> **Work in progress** — the core system is fully functional across 8 legal categories. More legal data, categories, and UI polish are actively being added.

An AI-powered RAG (Retrieval-Augmented Generation) system that answers questions about UK law in plain English, citing official sources from [GOV.UK](https://www.gov.uk) and [Citizens Advice](https://www.citizensadvice.org.uk).

## Features

- **8 legal domains**: immigration, student rights, driving, employment, housing, healthcare, benefits, and criminal law
- **Hybrid retrieval**: FAISS dense search + BM25 sparse search fused with Reciprocal Rank Fusion
- **Cross-encoder reranking**: ms-marco-MiniLM-L-6-v2 for precision relevance scoring
- **Conversation memory**: multi-turn context with 10-turn cap and 1-hour expiry
- **Category-specific disclaimers**: tailored signposting for each legal domain
- **Clean frontend**: pure CSS, mobile-friendly, no build step required

## Architecture

```
Scraper → Chunker → Embedder → FAISS + BM25 index
                                      ↓
User query → HybridRetriever → CrossEncoderReranker → GroqGenerator → Response
```

## Prerequisites

- Python 3.11+
- [Groq API key](https://console.groq.com) (free tier sufficient)

## Setup

**1. Clone and install**

```bash
git clone <repo-url>
cd uk-legal-assistant
pip install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
# Edit .env and set:  GROQ_API_KEY=your_key_here
```

**3. Scrape source documents**

```bash
python run_scraper.py
# Fetches ~30 pages from gov.uk and citizensadvice.org.uk → data/raw/
```

**4. Build the index**

```bash
python run_indexer.py
# Chunks documents, embeds with BGE-small-en-v1.5, builds FAISS+BM25 → data/index/
```

**5. Start the API**

```bash
uvicorn app.main:app --app-dir backend --reload
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

**6. Open the frontend**

```bash
cd frontend
python -m http.server 3000
# Then open http://localhost:3000 in your browser
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/law/query` | Ask any UK legal question |
| `POST` | `/law/query/{category}` | Ask within a specific legal category |
| `GET`  | `/law/categories` | List all 8 categories with doc counts |
| `POST` | `/law/batch` | Submit up to 5 queries in one request |
| `GET`  | `/law/capabilities` | Machine-readable API manifest |
| `GET`  | `/health` | Detailed component health check |
| `GET`  | `/health/ready` | Readiness probe |

### Example request

```bash
curl -X POST http://localhost:8000/law/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I apply for a Skilled Worker visa?", "limit": 5}'
```

### Example response

```json
{
  "status": "success",
  "data": {
    "answer": "To apply for a Skilled Worker visa you need...",
    "legal_category": "Immigration, visas, and right to remain",
    "sources": [{"document": "Skilled Worker visa: overview", "url": "...", "relevance_score": 0.91}],
    "disclaimer": "Immigration law is complex...",
    "seek_advice": "Consult an OISC-registered adviser for your specific situation.",
    "confidence": "high"
  },
  "metadata": {
    "query": "How do I apply for a Skilled Worker visa?",
    "category_detected": "immigration",
    "documents_searched": 321,
    "chunks_retrieved": 5,
    "conversation_id": "uuid-here",
    "latency_ms": 2340.5
  }
}
```

## Running Tests

```bash
# Full suite (117 tests)
python -m pytest tests/ -v

# Individual suites
python -m pytest tests/test_pipeline.py -v   # 49 tests — no index needed
python -m pytest tests/test_api.py -v        # 42 tests — no index needed
python -m pytest tests/test_retriever.py -v  # 26 tests — requires built index
```

## Deployment (Railway)

1. Push the repo to GitHub
2. Create a new Railway project → "Deploy from GitHub repo"
3. Set the environment variable `GROQ_API_KEY` in the Railway dashboard
4. Railway reads `railway.toml` for the build and start commands automatically

**Note:** The `data/index/` directory (FAISS + BM25 artefacts) must be committed to the repo or built as part of the Railway build step. The simplest approach is to commit the pre-built index.

## Docker

```bash
# Build (pre-built index must exist at data/index/)
docker build -t uk-legal-assistant .

# Run
docker run -p 8000:8000 -e GROQ_API_KEY=your_key uk-legal-assistant
```

## Legal Disclaimer

This tool provides AI-generated **information**, not legal advice. Do not rely on it for legal decisions. Always consult a qualified solicitor for your specific situation.

Free independent advice:
- [Citizens Advice](https://www.citizensadvice.org.uk)
- [GOV.UK](https://www.gov.uk)
- [Find a Solicitor (Law Society)](https://solicitors.lawsociety.org.uk)
