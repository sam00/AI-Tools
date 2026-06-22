"""Token estimation.

By default TokenTrim uses a fast, dependency-free heuristic so that it can
run anywhere (IDEs, sandboxes, CI). If ``tiktoken`` is installed and the tokenizer
backend is set to ``tiktoken``, exact counts are used instead.

The heuristic is intentionally simple and slightly conservative: it blends a
character-based estimate with a whitespace word estimate, which tracks real BPE
tokenizers within a few percent for typical English + code + JSON content.
"""

from __future__ import annotations

import re
from functools import lru_cache

_WORD_RE = re.compile(r"\w+|[^\w\s]")


def _heuristic_count(text: str) -> int:
    if not text:
        return 0
    # ~4 characters per token is the common rule of thumb for English.
    char_estimate = len(text) / 4.0
    # Punctuation-heavy / code content splits into more tokens than chars/4 implies,
    # so blend with a token-ish word count and take the larger of the two.
    word_estimate = len(_WORD_RE.findall(text)) * 0.75
    return max(1, int(round(max(char_estimate, word_estimate))))


@lru_cache(maxsize=4)
def _get_tiktoken_encoder(model: str):  # pragma: no cover - exercised only when installed
    import tiktoken

    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


class TokenCounter:
    """Counts tokens for strings using the configured backend."""

    def __init__(self, backend: str = "heuristic", model: str = "default") -> None:
        self.backend = backend
        self.model = model
        self._encoder = None
        if backend == "tiktoken":
            try:
                self._encoder = _get_tiktoken_encoder(model)
            except Exception:
                # Fall back gracefully if tiktoken is unavailable at runtime.
                self.backend = "heuristic"

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoder is not None:  # pragma: no cover - requires tiktoken
            return len(self._encoder.encode(text))
        return _heuristic_count(text)


_DEFAULT = TokenCounter()


def count_tokens(text: str) -> int:
    """Count tokens with the default heuristic counter."""
    return _DEFAULT.count(text)
