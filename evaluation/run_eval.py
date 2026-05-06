"""
RAG Evaluation Runner
=====================
Runs all 24 golden questions through the pipeline and reports:
  BLEU-1 / 2 / 4 · ROUGE-1 / 2 / L · BERTScore F1 · METEOR
  Answer F1 · Answer Correctness · Faithfulness · Hallucination %

Usage
-----
  # With real Groq API (GROQ_API_KEY must be set in .env):
  python evaluation/run_eval.py

  # With a mock LLM (tests the pipeline without an API key):
  python evaluation/run_eval.py --mock

  # Evaluate a single category only:
  python evaluation/run_eval.py --category student

  # Save results to JSON:
  python evaluation/run_eval.py --save
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))           # so 'evaluation' package is importable
os.chdir(ROOT)                          # so relative data paths resolve

from evaluation.metrics import (        # noqa: E402
    answer_correctness,
    answer_f1,
    bertscore_f1,
    bleu_n,
    faithfulness,
    hallucination_pct,
    meteor,
    rouge_l,
    rouge_n,
)
from app.models import QueryRequest     # noqa: E402
from app.rag.pipeline import RAGPipeline  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_dataset(category_filter: str | None) -> List[Dict]:
    path = Path(__file__).parent / "golden_dataset.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    if category_filter:
        items = [i for i in items if i["category"] == category_filter]
    return items


def _build_mock_pipeline() -> RAGPipeline:
    """Return a pipeline whose LLM call echoes the reference answer."""
    return RAGPipeline()          # LLM is patched per-call in evaluate()


def _context_from_response(resp) -> str:
    return " ".join(s.content for s in resp.data.sources)


def _clean_for_faithfulness(answer: str) -> str:
    """
    Strip parts of the answer that are deliberately added by the system and
    should not be penalised as hallucinations:

    1. Disclaimer block — everything from the first "---" or "⚠" separator
       onward.  The disclaimer is already stored separately in
       resp.data.disclaimer so it is not information loss to exclude it.
    2. Citation markers — [1], [2], … tokens are extracted as bare digits by
       the tokeniser and flagged as ungrounded even though they are grounding
       evidence, not factual claims.
    """
    # 1. Drop disclaimer block (separator can be "---" or the warning emoji)
    for sep in ("---", "⚠"):          # ⚠ == ⚠
        if sep in answer:
            answer = answer.split(sep)[0]

    # 2. Strip [N] citation markers
    answer = re.sub(r"\[\d+\]", "", answer)

    return answer.strip()


# ── Core evaluation loop ──────────────────────────────────────────────────────

def evaluate(
    dataset: List[Dict],
    pipeline: RAGPipeline,
    mock: bool,
) -> List[Dict]:
    rows: List[Dict] = []
    predictions: List[str] = []
    references:  List[str] = []

    total = len(dataset)
    print(f"\nEvaluating {total} questions...\n")

    for idx, item in enumerate(dataset, 1):
        query = item["query"]
        ref   = item["reference_answer"]
        cat   = item.get("category")

        print(f"  [{idx:02d}/{total}] {item['id']}  {query[:65]}...")

        req = QueryRequest(query=query, category=cat, limit=5)

        if mock:
            # In mock mode the LLM returns the reference answer so metric
            # code can be verified without spending API credits.
            mock_resp = MagicMock()
            mock_resp.choices[0].message.content = ref
            mock_resp.usage.prompt_tokens     = 0
            mock_resp.usage.completion_tokens = 0
            mock_resp.usage.total_tokens      = 0
            with patch.object(pipeline.generator, "_call_api", return_value=mock_resp):
                resp = pipeline.query(req)
        else:
            resp = pipeline.query(req)

        pred    = resp.data.answer
        context = _context_from_response(resp)

        # Faithfulness is measured on the substantive answer only —
        # disclaimer block and [N] citation markers are stripped first so
        # that deliberate system additions are not penalised as hallucinations.
        pred_for_faith = _clean_for_faithfulness(pred)

        row = {
            "id":               item["id"],
            "category":         cat,
            "query":            query,
            "prediction":       pred,
            "reference":        ref,
            "confidence":       resp.data.confidence,
            # — n-gram / semantic metrics (full prediction, disclaimer included) —
            "bleu_1":           round(bleu_n(pred, ref, 1), 4),
            "bleu_2":           round(bleu_n(pred, ref, 2), 4),
            "bleu_4":           round(bleu_n(pred, ref, 4), 4),
            "rouge_1":          round(rouge_n(pred, ref, 1)["f1"], 4),
            "rouge_2":          round(rouge_n(pred, ref, 2)["f1"], 4),
            "rouge_l":          round(rouge_l(pred, ref)["f1"],    4),
            "meteor":           round(meteor(pred, ref),            4),
            "answer_f1":        round(answer_f1(pred, ref),         4),
            "answer_correctness": round(answer_correctness(pred, ref), 4),
            # — grounding metrics (cleaned prediction: no disclaimer, no [N]) —
            "faithfulness":     round(faithfulness(pred_for_faith, context),     4),
            "hallucination_pct": round(hallucination_pct(pred_for_faith, context), 2),
        }
        rows.append(row)
        predictions.append(pred)
        references.append(ref)

    # BERTScore requires a batch call
    print("\n  Computing BERTScore F1 (batch)...")
    bert_scores = bertscore_f1(predictions, references)
    for row, bs in zip(rows, bert_scores):
        row["bertscore_f1"] = bs

    return rows


# ── Display ───────────────────────────────────────────────────────────────────

METRIC_COLS = [
    ("BLEU-1",        "bleu_1"),
    ("BLEU-2",        "bleu_2"),
    ("BLEU-4",        "bleu_4"),
    ("ROUGE-1",       "rouge_1"),
    ("ROUGE-2",       "rouge_2"),
    ("ROUGE-L",       "rouge_l"),
    ("BERTScore F1",  "bertscore_f1"),
    ("METEOR",        "meteor"),
    ("Answer F1",     "answer_f1"),
    ("Ans. Correct.", "answer_correctness"),
    ("Faithfulness",  "faithfulness"),
    ("Hallucin. %",   "hallucination_pct"),
]


def _avg(rows: List[Dict], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return round(sum(vals) / len(vals), 4) if vals else 0.0


def print_results(rows: List[Dict]) -> None:
    cats = sorted({r["category"] for r in rows})

    # ── Per-question table ────────────────────────────────────────────────
    col_w    = 14
    id_w     = 10
    metric_header = "".join(f"{label:>{col_w}}" for label, _ in METRIC_COLS)
    sep = "-" * (id_w + len(metric_header))

    print("\n" + "=" * len(sep))
    print("PER-QUESTION RESULTS")
    print("  Note: Faithfulness / Hallucination % measured on substantive answer only")
    print("        (disclaimer block and [N] citation markers stripped before scoring)")
    print("=" * len(sep))
    print(f"{'ID':<{id_w}}" + metric_header)
    print(sep)

    for row in rows:
        vals = "".join(
            f"{row[key]:>{col_w}.4f}" if key != "hallucination_pct"
            else f"{row[key]:>{col_w}.1f}"
            for _, key in METRIC_COLS
        )
        print(f"{row['id']:<{id_w}}" + vals)

    # ── Per-category averages ─────────────────────────────────────────────
    print("\n" + "=" * len(sep))
    print("CATEGORY AVERAGES")
    print("=" * len(sep))
    print(f"{'Category':<{id_w}}" + metric_header)
    print(sep)

    for cat in cats:
        cat_rows = [r for r in rows if r["category"] == cat]
        vals = "".join(
            f"{_avg(cat_rows, key):>{col_w}.4f}" if key != "hallucination_pct"
            else f"{_avg(cat_rows, key):>{col_w}.1f}"
            for _, key in METRIC_COLS
        )
        print(f"{cat:<{id_w}}" + vals)

    # ── Overall averages ──────────────────────────────────────────────────
    print(sep)
    vals = "".join(
        f"{_avg(rows, key):>{col_w}.4f}" if key != "hallucination_pct"
        else f"{_avg(rows, key):>{col_w}.1f}"
        for _, key in METRIC_COLS
    )
    print(f"{'OVERALL':<{id_w}}" + vals)
    print("=" * len(sep))

    # ── Metric explanation ────────────────────────────────────────────────
    print("""
Metric guide
  BLEU-1/2/4      n-gram precision vs reference answer (higher = better)
  ROUGE-1/2/L     n-gram / LCS recall vs reference answer (higher = better)
  BERTScore F1    semantic similarity via DistilBERT embeddings (higher = better)
  METEOR          unigram F-mean with fragmentation penalty (higher = better)
  Answer F1       token-level F1 vs reference (SQuAD style) (higher = better)
  Ans. Correct.   key-fact coverage of reference by prediction (higher = better)
  Faithfulness    answer content grounded in retrieved context (higher = better)
  Hallucin. %     content NOT in retrieved context (lower = better)
""")


def print_summary(rows: List[Dict], elapsed: float, mock: bool) -> None:
    mode = "MOCK (reference answer used as LLM output)" if mock else "LIVE (real Groq API)"
    print(f"Mode            : {mode}")
    print(f"Questions run   : {len(rows)}")
    print(f"Wall time       : {elapsed:.1f}s")
    print(f"Avg latency/q   : {elapsed/len(rows):.1f}s")
    print()
    print(f"  Overall BLEU-1      : {_avg(rows, 'bleu_1'):.4f}")
    print(f"  Overall ROUGE-L     : {_avg(rows, 'rouge_l'):.4f}")
    print(f"  Overall BERTScore   : {_avg(rows, 'bertscore_f1'):.4f}")
    print(f"  Overall METEOR      : {_avg(rows, 'meteor'):.4f}")
    print(f"  Overall Answer F1   : {_avg(rows, 'answer_f1'):.4f}")
    print(f"  Avg Faithfulness    : {_avg(rows, 'faithfulness'):.4f}")
    print(f"  Avg Hallucination % : {_avg(rows, 'hallucination_pct'):.1f}%")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation runner")
    parser.add_argument("--mock",     action="store_true",
                        help="Use reference answers as LLM output (no API key needed)")
    parser.add_argument("--category", default=None,
                        help="Evaluate only this category (e.g. student)")
    parser.add_argument("--save",     action="store_true",
                        help="Save per-question results to evaluation/results/")
    args = parser.parse_args()

    dataset = _load_dataset(args.category)
    if not dataset:
        print(f"No questions found for category '{args.category}'")
        sys.exit(1)

    print("=" * 60)
    print("  UK Legal Assistant — RAG Evaluation")
    print("=" * 60)
    if args.mock:
        print("  Mode: MOCK  (no Groq API key required)")
    else:
        print("  Mode: LIVE  (using real Groq API)")
    print(f"  Questions: {len(dataset)}")
    if args.category:
        print(f"  Category filter: {args.category}")

    print("\nLoading pipeline (first query will warm up ML models)...")
    pipeline = _build_mock_pipeline()

    t0   = time.monotonic()
    rows = evaluate(dataset, pipeline, mock=args.mock)
    elapsed = time.monotonic() - t0

    print_results(rows)
    print_summary(rows, elapsed, mock=args.mock)

    if args.save:
        out_dir = Path(__file__).parent / "results"
        out_dir.mkdir(exist_ok=True)
        tag  = args.category or "all"
        mode = "mock" if args.mock else "live"
        ts   = time.strftime("%Y%m%d_%H%M%S")
        out  = out_dir / f"eval_{tag}_{mode}_{ts}.json"
        out.write_text(
            json.dumps(
                {
                    "mode":     mode,
                    "category": args.category,
                    "n":        len(rows),
                    "averages": {key: _avg(rows, key) for _, key in METRIC_COLS},
                    "rows":     rows,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"\nResults saved to: {out}")


if __name__ == "__main__":
    main()
