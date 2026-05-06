"""
RAG evaluation metrics — all implemented without heavy dependencies
except rouge-score and bert-score (both pip-installable).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple


# ── Tokeniser ─────────────────────────────────────────────────────────────────

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "it", "its", "this", "that",
    "these", "those", "i", "you", "he", "she", "we", "they", "what",
    "which", "who", "or", "and", "but", "if", "then", "than", "so", "not",
    "no", "your", "their", "our", "my", "his", "her", "up", "out",
    "about", "also", "more", "any", "all", "one", "two", "s",
}


def tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def content_tokens(text: str) -> List[str]:
    """Tokenize and strip stopwords."""
    return [t for t in tokenize(text) if t not in _STOPWORDS]


# ── BLEU ──────────────────────────────────────────────────────────────────────

def _ngram_counts(tokens: List[str], n: int) -> Counter:
    return Counter(tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1))


def _brevity_penalty(hyp: List[str], ref: List[str]) -> float:
    if not hyp:
        return 0.0
    if len(hyp) >= len(ref):
        return 1.0
    return math.exp(1 - len(ref) / len(hyp))


def bleu_n(hypothesis: str, reference: str, n: int) -> float:
    """Corpus BLEU-n (single sentence, clipped precision × brevity penalty)."""
    hyp = tokenize(hypothesis)
    ref = tokenize(reference)

    if len(hyp) < n or len(ref) < n:
        return 0.0

    hyp_ng = _ngram_counts(hyp, n)
    ref_ng = _ngram_counts(ref, n)

    clipped = sum(min(c, ref_ng[g]) for g, c in hyp_ng.items())
    total   = sum(hyp_ng.values())

    precision = clipped / total if total else 0.0
    return _brevity_penalty(hyp, ref) * precision


# ── ROUGE ─────────────────────────────────────────────────────────────────────

def _rouge_scores(hyp_ng: Counter, ref_ng: Counter) -> Dict[str, float]:
    overlap   = sum(min(c, ref_ng[g]) for g, c in hyp_ng.items())
    precision = overlap / sum(hyp_ng.values()) if hyp_ng else 0.0
    recall    = overlap / sum(ref_ng.values()) if ref_ng else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


def rouge_n(hypothesis: str, reference: str, n: int) -> Dict[str, float]:
    hyp = tokenize(hypothesis)
    ref = tokenize(reference)
    return _rouge_scores(_ngram_counts(hyp, n), _ngram_counts(ref, n))


def rouge_l(hypothesis: str, reference: str) -> Dict[str, float]:
    """LCS-based ROUGE-L."""
    hyp = tokenize(hypothesis)
    ref = tokenize(reference)

    if not hyp or not ref:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    m, n = len(hyp), len(ref)
    # Space-optimised LCS
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            curr[j] = (
                prev[j - 1] + 1
                if hyp[i - 1] == ref[j - 1]
                else max(curr[j - 1], prev[j])
            )
        prev = curr
    lcs = prev[n]

    precision = lcs / m if m else 0.0
    recall    = lcs / n if n else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}


# ── METEOR ────────────────────────────────────────────────────────────────────

def meteor(hypothesis: str, reference: str) -> float:
    """
    Simplified METEOR: unigram F-mean (α=0.9) with a chunk-fragmentation
    penalty.  Matches are exact-token; no stemming or synonym expansion.
    """
    hyp = tokenize(hypothesis)
    ref = tokenize(reference)

    if not hyp or not ref:
        return 0.0

    ref_pool = Counter(ref)
    matched_hyp_positions: List[int] = []

    for i, token in enumerate(hyp):
        if ref_pool.get(token, 0) > 0:
            ref_pool[token] -= 1
            matched_hyp_positions.append(i)

    m = len(matched_hyp_positions)
    if m == 0:
        return 0.0

    precision = m / len(hyp)
    recall    = m / len(ref)
    f_mean    = (
        10 * precision * recall / (9 * precision + recall)
        if (9 * precision + recall) > 0
        else 0.0
    )

    # Count contiguous chunks in matched hypothesis positions
    chunks = 1
    for a, b in zip(matched_hyp_positions, matched_hyp_positions[1:]):
        if b != a + 1:
            chunks += 1
    frag_penalty = 0.5 * (chunks / m) ** 3

    return f_mean * (1 - frag_penalty)


# ── Answer F1  (SQuAD-style token overlap) ────────────────────────────────────

def answer_f1(hypothesis: str, reference: str) -> float:
    hyp = tokenize(hypothesis)
    ref = tokenize(reference)

    common = Counter(hyp) & Counter(ref)
    num_same = sum(common.values())
    if num_same == 0:
        return 0.0

    precision = num_same / len(hyp)
    recall    = num_same / len(ref)
    return 2 * precision * recall / (precision + recall)


# ── Answer Correctness ────────────────────────────────────────────────────────

def answer_correctness(hypothesis: str, reference: str) -> float:
    """
    Measures how much of the reference's key content is covered by the answer.
    Uses content-word recall (stopwords stripped) scaled to [0, 1].
    """
    hyp_tokens = set(content_tokens(hypothesis))
    ref_tokens  = set(content_tokens(reference))

    if not ref_tokens:
        return 0.0

    covered = hyp_tokens & ref_tokens
    return len(covered) / len(ref_tokens)


# ── Faithfulness & Hallucination ──────────────────────────────────────────────

def faithfulness(answer: str, context: str) -> float:
    """
    Proportion of the answer's content words that appear in the retrieved
    context.  High faithfulness → answer is grounded in the sources.
    """
    ans_tokens = set(content_tokens(answer))
    ctx_tokens  = set(content_tokens(context))

    if not ans_tokens:
        return 0.0

    grounded = ans_tokens & ctx_tokens
    return len(grounded) / len(ans_tokens)


def hallucination_pct(answer: str, context: str) -> float:
    """100 × (1 − faithfulness)."""
    return (1.0 - faithfulness(answer, context)) * 100.0


# ── BERTScore ─────────────────────────────────────────────────────────────────

def bertscore_f1(predictions: List[str], references: List[str]) -> List[float]:
    """
    Semantic similarity via bert-score.
    Falls back to answer_f1 if the library is not installed.
    """
    try:
        from bert_score import score as _score
        _, _, F = _score(
            predictions, references,
            lang="en",
            model_type="distilbert-base-uncased",
            verbose=False,
        )
        return [round(float(f), 4) for f in F]
    except Exception:
        return [round(answer_f1(p, r), 4) for p, r in zip(predictions, references)]
