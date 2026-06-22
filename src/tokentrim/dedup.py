"""Deduplication — the biggest single lever for agent token bills.

Long agent conversations are ~70% redundant: the same system preamble, the same
file pasted twice, the same traceback after every retry. This module removes that
redundancy two ways:

- **Exact** — identical blocks/lines collapse to one with a ``× N`` note.
- **Near-duplicate** — a 64-bit SimHash over token shingles detects blocks that
  are *almost* identical (e.g. a traceback that differs only by a timestamp) and
  collapses them too.

Everything is pure-Python and deterministic. Collapsed content remains recoverable
because the original block is what gets cached in the CCR store upstream.
"""

from __future__ import annotations

import difflib
import hashlib
import re

_TOKEN = re.compile(r"\w+")

# Comparing more than this many characters with difflib is rarely worth the cost;
# re-pasted content matches on the prefix anyway, and originals stay reversible.
_RATIO_CHAR_CAP = 6000


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _shingles(tokens: list[str], k: int = 3) -> list[str]:
    if len(tokens) < k:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]


def simhash(text: str, bits: int = 64) -> int:
    """Compute a 64-bit SimHash fingerprint of ``text``."""
    shingles = _shingles(_tokens(text))
    if not shingles:
        return 0
    vector = [0] * bits
    for shingle in shingles:
        h = int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for i in range(bits):
            vector[i] += 1 if (h >> i) & 1 else -1
    fingerprint = 0
    for i in range(bits):
        if vector[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _shingle_set(text: str, k: int = 3) -> set[str]:
    return set(_shingles(_tokens(text), k))


def jaccard(a: str, b: str, k: int = 3) -> float:
    """Token-shingle Jaccard similarity in [0, 1] — robust across text lengths."""
    sa, sb = _shingle_set(a, k), _shingle_set(b, k)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


# Default similarity required to treat two blocks/messages as duplicates. Tuned for
# re-pasted files and repeated tracebacks (which sit well above 0.85), while avoiding
# false positives on merely-similar prose.
NEAR_DUP_THRESHOLD = 0.85


def similarity(a: str, b: str) -> float:
    """Sequence similarity in [0, 1] for re-paste detection.

    Uses difflib's ratio (handles internal repetition correctly, unlike set
    Jaccard) with a cheap length-ratio prefilter and a size cap for performance.
    """
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    if min(la, lb) / max(la, lb) < 0.6:
        return 0.0  # too different in length to be a re-paste
    sa, sb = a[:_RATIO_CHAR_CAP], b[:_RATIO_CHAR_CAP]
    matcher = difflib.SequenceMatcher(None, sa, sb, autojunk=True)
    if matcher.quick_ratio() < 0.6:
        return matcher.quick_ratio()
    return matcher.ratio()


def near_duplicate(a: str, b: str, threshold: float = NEAR_DUP_THRESHOLD) -> bool:
    """True if ``a`` and ``b`` are near-identical (sequence similarity ≥ threshold)."""
    return similarity(a, b) >= threshold


def _split_blocks(text: str) -> list[str]:
    return re.split(r"(\n\s*\n)", text)


def dedup_blocks(text: str, threshold: float = NEAR_DUP_THRESHOLD) -> str:
    """Collapse runs of exact + near-duplicate blocks within a single payload."""
    parts = _split_blocks(text)
    blocks = parts[::2]  # content blocks (odd entries are separators)
    seps = parts[1::2]
    if len(blocks) < 3:
        return text

    pending_repeat = 0
    out: list[str] = []

    def flush() -> None:
        nonlocal pending_repeat
        if pending_repeat:
            out.append(f"\n[× {pending_repeat + 1} near-identical blocks collapsed]\n")
            pending_repeat = 0

    last_block: str | None = None
    for i, block in enumerate(blocks):
        stripped = block.strip()
        if not stripped:
            out.append(block + (seps[i] if i < len(seps) else ""))
            continue
        if last_block is not None and similarity(stripped, last_block) >= threshold:
            pending_repeat += 1
            continue
        flush()
        out.append(block + (seps[i] if i < len(seps) else ""))
        last_block = stripped
    flush()

    result = "".join(out)
    return result if len(result) < len(text) else text


def find_duplicate(text: str, prior: list[str], threshold: float = NEAR_DUP_THRESHOLD) -> int | None:
    """Return the index in ``prior`` that is a near-duplicate of ``text``, else None."""
    for i, candidate in enumerate(prior):
        if candidate and similarity(text, candidate) >= threshold:
            return i
    return None
