"""Fidelity scoring — estimate how much of the *answer* survived compression.

This powers the quality gate (see :mod:`tokentrim.core`). It is a deterministic,
dependency-free proxy for semantic retention, inspired by ROUGE-style recall:

    fidelity = (information-bearing tokens preserved in the compressed text)
               / (information-bearing tokens in the original)

"Information-bearing" tokens are the ones that usually carry the answer and that
a model can't guess back: numbers, identifiers (snake_case / CamelCase / dotted /
hyphenated), error/keyword signals, and capitalized terms. Common stop-prose is
ignored so that dropping filler doesn't penalize the score.

Scores range 0.0 (nothing important kept) → 1.0 (all important tokens kept).
"""

from __future__ import annotations

import re
from collections import Counter

_NUMBER = re.compile(r"\b\d[\d.,_]*\b")
_IDENTIFIER = re.compile(r"\b(?:[A-Za-z]+_[A-Za-z0-9_]+|[a-z]+[A-Z][A-Za-z0-9]+|[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+|[A-Za-z0-9]+-[A-Za-z0-9-]+)\b")
_CAPWORD = re.compile(r"\b[A-Z][a-zA-Z0-9]{2,}\b")
_SIGNAL = re.compile(r"(?i)\b(error|fatal|critical|exception|fail(?:ed|ure)?|warn(?:ing)?|must|never|always|because|return|raises?)\b")


def _important_tokens(text: str) -> Counter:
    tokens: Counter = Counter()
    for pattern in (_NUMBER, _IDENTIFIER, _CAPWORD, _SIGNAL):
        for match in pattern.findall(text):
            tokens[match.lower()] += 1
    return tokens


def fidelity(original: str, compressed: str) -> float:
    """Return the fraction of important tokens from ``original`` kept in ``compressed``."""
    original_tokens = _important_tokens(original)
    if not original_tokens:
        # No information-bearing tokens — treat any non-empty output as faithful.
        return 1.0 if compressed.strip() else 0.0

    compressed_tokens = _important_tokens(compressed)
    preserved = 0
    total = 0
    for tok, count in original_tokens.items():
        total += count
        preserved += min(count, compressed_tokens.get(tok, 0))
    return preserved / total if total else 1.0
