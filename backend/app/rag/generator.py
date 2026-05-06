from __future__ import annotations

from typing import Dict, List

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models import SourceChunk

# ---------------------------------------------------------------------------
# Low-relevance warning — prepended to the user turn when top score < threshold
# ---------------------------------------------------------------------------

_LOW_RELEVANCE_THRESHOLD = 0.3

_LOW_RELEVANCE_WARNING = (
    "WARNING: The retrieved context has low relevance scores for this query. "
    "If the context does not directly answer the question, say so explicitly "
    "rather than generating an answer from general knowledge."
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a UK legal information assistant helping ordinary people understand \
UK laws and policies in plain English.

ABSOLUTE RULES — these cannot be broken under any circumstances:

1. USE ONLY THE PROVIDED CONTEXT
   Every single factual claim in your answer MUST come directly from the \
numbered context documents provided.
   Do not use your training knowledge to add facts, numbers, thresholds, \
dates, or procedures.

2. CITE EVERY FACTUAL CLAIM
   After every factual statement write [1], [2], [3] etc referring to the \
context document number it came from.
   Example: 'Students can work up to 20 hours per week during term time [2].'
   If you cannot cite a claim with a context number, do not make the claim.

3. WHEN CONTEXT IS INSUFFICIENT — SAY SO EXPLICITLY
   If the provided context does not contain enough information to answer the \
question fully, say exactly:
   'My knowledge base does not contain specific information about [specific \
aspect]. For accurate information on this, please visit gov.uk or contact \
[relevant authority] directly.'
   Do NOT attempt to fill gaps with general knowledge.
   Do NOT say 'generally' or 'typically' unless the context itself uses \
those words.

4. SPECIFIC NUMBERS AND THRESHOLDS
   Only state specific numbers (fines, hours, days, amounts, percentages) \
if they appear EXACTLY in the context. Never approximate or estimate.

5. PLAIN ENGLISH
   Write clearly for someone with no legal background.
   Avoid jargon. If a legal term is unavoidable, explain it in plain English \
immediately after.

6. MULTI-PART QUESTIONS
   If the question has multiple parts, answer each part separately with a \
clear label.
   Only answer parts that the context supports.

7. EMPATHY
   Many users are in stressful situations.
   Be warm, clear, and direct. Never be dismissive.

8. ALWAYS END WITH DISCLAIMER
   Every response must end with:
   ---
   ⚠️ This is general legal information only, not personal legal advice. \
Laws change regularly. For advice specific to your situation, consult a \
qualified solicitor or contact the relevant authority directly.\
"""


class GroqGenerator:
    """
    LLM answer generator using the Groq API (llama-3.1-8b-instant).

    * Groq client is created lazily on first call.
    * Rate-limit errors (HTTP 429) are retried with exponential back-off.
    * When the top reranker score is below _LOW_RELEVANCE_THRESHOLD a
      warning is prepended to the user message to suppress hallucination.
    """

    SYSTEM_PROMPT = _SYSTEM_PROMPT

    def __init__(self) -> None:
        self._client = None
        self.model   = settings.groq_model

    # ------------------------------------------------------------------
    # Lazy Groq client
    # ------------------------------------------------------------------

    @property
    def client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=settings.groq_api_key)
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        query:                str,
        chunks:               List[SourceChunk],
        conversation_history: List[Dict] | None = None,
    ) -> str:
        """
        Build a prompt from *chunks* and *conversation_history*, call the
        Groq API, log token usage, and return the answer string.

        If the top chunk relevance score is below the low-relevance threshold
        a warning is prepended to the user turn so the model prefers
        admitting insufficient context over hallucinating.
        """
        context      = self._build_context(chunks)
        top_score    = chunks[0].relevance_score if chunks else 0.0
        low_relevance = top_score < _LOW_RELEVANCE_THRESHOLD

        if low_relevance:
            logger.warning(
                f"Low relevance context (top score={top_score:.3f}) — "
                "prepending insufficiency warning to user message"
            )

        messages = self._build_messages(
            query, context, conversation_history, low_relevance=low_relevance
        )
        response = self._call_api(messages)

        usage = getattr(response, "usage", None)
        if usage:
            logger.debug(
                f"Groq token usage — prompt: {usage.prompt_tokens}, "
                f"completion: {usage.completion_tokens}, "
                f"total: {usage.total_tokens}"
            )

        return response.choices[0].message.content.strip()

    def generate_hypothesis(self, query: str) -> str:
        """
        Generate a hypothetical answer paragraph for HyDE retrieval.

        Produces a short passage (30-50 words) that might appear in an
        official UK government guide, which can then be embedded and used
        to retrieve more relevant chunks than the bare query alone.
        """
        prompt = (
            f"Write a single paragraph (30-50 words) that would appear in "
            f"an official UK government guide answering this question: {query}\n"
            f"Write only the paragraph, no introduction."
        )
        messages = [{"role": "user", "content": prompt}]
        response = self._call_api(messages, temperature=0.3)
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_context(self, chunks: List[SourceChunk]) -> str:
        """Format chunks as a numbered list the LLM can cite with [N]."""
        parts: List[str] = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(
                f"[{i}] Source: {chunk.document}\n"
                f"URL: {chunk.url}\n"
                f"{chunk.content}"
            )
        return "\n\n---\n\n".join(parts)

    def _build_messages(
        self,
        query:                str,
        context:              str,
        conversation_history: List[Dict] | None,
        low_relevance:        bool = False,
    ) -> List[Dict]:
        messages: List[Dict] = [{"role": "system", "content": self.SYSTEM_PROMPT}]

        if conversation_history:
            for turn in conversation_history:
                if "role" in turn:
                    messages.append({"role": turn["role"], "content": turn["content"]})
                else:
                    messages.append({"role": "user",      "content": turn["question"]})
                    messages.append({"role": "assistant",  "content": turn["answer"]})

        user_content = f"Legal documents:\n\n{context}\n\n---\n\nQuestion: {query}"

        if low_relevance:
            user_content = f"{_LOW_RELEVANCE_WARNING}\n\n{user_content}"

        messages.append({"role": "user", "content": user_content})
        return messages

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_api(self, messages: List[Dict], temperature: float = 0.1):
        """Retry-wrapped Groq API call — handles 429 rate-limit responses."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=1024,
            temperature=temperature,
        )


# Backward-compatible alias
Generator = GroqGenerator
