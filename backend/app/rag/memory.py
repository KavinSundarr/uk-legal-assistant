from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional


class ConversationMemory:
    """
    In-memory conversation store keyed by conversation_id.

    Constraints:
    * Maximum 10 turns stored per conversation (older turns are dropped).
    * Conversations auto-expire after 1 hour of inactivity.
    * format_history_for_prompt() returns the last 5 turns as a plain-text
      block suitable for injection into the LLM prompt.
    """

    _MAX_TURNS    = 10
    _EXPIRY_SECS  = 3600  # 1 hour

    def __init__(self) -> None:
        # {conversation_id: {"turns": [...], "last_access": float}}
        self._store: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def generate_conversation_id() -> str:
        """Return a new random UUID string."""
        return str(uuid.uuid4())

    def add_turn(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """
        Append one turn.  *role* should be "user" or "assistant".
        Trims to the last _MAX_TURNS after insertion.
        """
        self._touch(conversation_id)
        self._store[conversation_id]["turns"].append(
            {"role": role, "content": content, "ts": time.time()}
        )
        # Keep only the most recent MAX_TURNS entries
        self._store[conversation_id]["turns"] = (
            self._store[conversation_id]["turns"][-self._MAX_TURNS:]
        )

    def get_history(
        self,
        conversation_id: Optional[str],
        max_turns: int = 5,
    ) -> List[Dict]:
        """Return up to *max_turns* recent turns, or [] if unknown/expired."""
        if not conversation_id:
            return []
        self._evict_expired()
        entry = self._store.get(conversation_id)
        if entry is None:
            return []
        self._store[conversation_id]["last_access"] = time.time()
        return entry["turns"][-max_turns:]

    def format_history_for_prompt(
        self,
        conversation_id: Optional[str],
        max_turns: int = 5,
    ) -> str:
        """
        Return recent conversation as a formatted string for prompt injection.

        Example output:
            User: what is a student visa?
            Assistant: A student visa allows you to ...
            User: how long is it valid?
        """
        turns = self.get_history(conversation_id, max_turns=max_turns)
        if not turns:
            return ""
        lines = []
        for turn in turns:
            role_label = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{role_label}: {turn['content']}")
        return "\n".join(lines)

    def clear(self, conversation_id: str) -> None:
        """Delete all history for this conversation."""
        self._store.pop(conversation_id, None)

    # ------------------------------------------------------------------
    # Legacy compatibility (pipeline used add/get with question+answer)
    # ------------------------------------------------------------------

    def add(
        self,
        conversation_id: Optional[str],
        question: str,
        answer: str,
    ) -> None:
        if not conversation_id:
            return
        self.add_turn(conversation_id, "user",      question)
        self.add_turn(conversation_id, "assistant", answer)

    def get(
        self,
        conversation_id: Optional[str],
        max_turns: int = 5,
    ) -> List[Dict]:
        """Return history as list of {question, answer} dicts (legacy format)."""
        turns = self.get_history(conversation_id, max_turns=max_turns * 2)
        # Re-pair user/assistant turns into the old {question, answer} shape
        paired: List[Dict] = []
        it = iter(turns)
        for turn in it:
            if turn["role"] == "user":
                try:
                    nxt = next(it)
                    if nxt["role"] == "assistant":
                        paired.append(
                            {"question": turn["content"], "answer": nxt["content"]}
                        )
                except StopIteration:
                    pass
        return paired[-max_turns:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _touch(self, conversation_id: str) -> None:
        """Create entry if absent; update last_access timestamp."""
        self._evict_expired()
        if conversation_id not in self._store:
            self._store[conversation_id] = {"turns": [], "last_access": time.time()}
        else:
            self._store[conversation_id]["last_access"] = time.time()

    def _evict_expired(self) -> None:
        """Remove conversations that have been idle for more than _EXPIRY_SECS."""
        cutoff = time.time() - self._EXPIRY_SECS
        expired = [
            cid
            for cid, entry in self._store.items()
            if entry["last_access"] < cutoff
        ]
        for cid in expired:
            del self._store[cid]
