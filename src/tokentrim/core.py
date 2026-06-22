"""Core compression pipeline.

Public entry points:

- :func:`compress_block`  — compress one string, returns a rich result
- :func:`compress_text`   — compress one string, returns a string
- :func:`compress`        — compress a list of chat messages (conversation-aware)
- :func:`compress_rag`    — compress a list of retrieved chunks against a query
- :func:`retrieve`        — recover an original from the CCR store by reference

The pipeline order mirrors a stable lifecycle:

    redact → route → compress → (cache original for CCR) → annotate
"""

from __future__ import annotations

import re
from typing import Any

from .compressors import get_compressor
from .compressors.base import CompressResult
from .compressors.rag_compressor import RagCompressor
from .config import Config, get_config
from .dedup import dedup_blocks, find_duplicate
from .fidelity import fidelity as compute_fidelity
from .pricing import cost_for_tokens
from .redact import redact
from .router import ContentType, detect
from .stats import TELEMETRY
from .store import REF_MARKER_PREFIX, get_store
from .tokens import TokenCounter

_RAG = RagCompressor()
_REF_RE = re.compile(rf"\[{REF_MARKER_PREFIX}\s+([0-9a-f]{{6,}})")

# Kinds where extractive loss could drop the answer *in place* → guard with the
# quality gate. Structured kinds (json/log/code/diff) are excluded: they keep
# strong structural guarantees and are recoverable via CCR, so low visible
# token-recall does not mean the answer was lost.
GATED_KINDS = {ContentType.TEXT.value, ContentType.TABLE.value}
_GATED_KINDS = GATED_KINDS
# Kinds that benefit from block-level dedup before the type compressor runs.
_DEDUP_KINDS = {ContentType.TEXT.value, ContentType.LOG.value, ContentType.CODE.value, ContentType.DIFF.value, ContentType.TABLE.value}


def _counter(config: Config) -> TokenCounter:
    return TokenCounter(backend=config.tokenizer, model=config.model)


def _annotate(compressed: str, ref: str | None, saved: int) -> str:
    if ref is None:
        return compressed
    return f"{compressed}\n[{REF_MARKER_PREFIX} {ref} +{saved} tokens — call tokentrim_retrieve to expand]"


def compress_block(
    text: str,
    config: Config | None = None,
    *,
    content_type: ContentType | None = None,
) -> CompressResult:
    """Compress a single block of content."""
    cfg = config or get_config()
    counter = _counter(cfg)
    original_tokens = counter.count(text)

    if not cfg.enabled or original_tokens < cfg.min_tokens:
        return CompressResult(
            text=text,
            kind="passthrough",
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
        )

    secrets = 0
    working = text
    if cfg.redact_secrets:
        working, secrets = redact(working)

    ctype = content_type or detect(working)

    # Pre-pass: collapse exact + near-duplicate blocks (repeated tracebacks, etc.).
    if cfg.dedup and ctype.value in _DEDUP_KINDS:
        working = dedup_blocks(working)

    compressor = get_compressor(ctype)
    compressed = compressor.compress(working, cfg)

    # Quality gate: for lossy extractive kinds, revert to the original if too much
    # answer-bearing content was dropped. Structured/reversible kinds are exempt.
    measured_fidelity = compute_fidelity(text, compressed)
    reverted = False
    if (
        cfg.quality_threshold > 0
        and ctype.value in _GATED_KINDS
        and compressed != text
        and measured_fidelity < cfg.quality_threshold
    ):
        reverted = True
        TELEMETRY.record(
            original=original_tokens,
            compressed=original_tokens,
            kind=ctype.value,
            secrets=secrets,
            fidelity=measured_fidelity,
            reverted=True,
        )
        return CompressResult(
            text=text,
            kind=ctype.value,
            original_tokens=original_tokens,
            compressed_tokens=original_tokens,
            fidelity=measured_fidelity,
            reverted=True,
        )

    compressed_tokens = counter.count(compressed)
    saved = max(0, original_tokens - compressed_tokens)

    ref = None
    if cfg.reversible and saved > 0 and compressed != text:
        ref = get_store(cfg.store_dir, cfg.store_ttl).put(text, kind=ctype.value)
        compressed = _annotate(compressed, ref, saved)
        compressed_tokens = counter.count(compressed)
        saved = max(0, original_tokens - compressed_tokens)

    cost_saved = cost_for_tokens(saved, cfg.model)

    TELEMETRY.record(
        original=original_tokens,
        compressed=compressed_tokens,
        kind=ctype.value,
        secrets=secrets,
        cost_saved=cost_saved,
        fidelity=measured_fidelity,
    )

    return CompressResult(
        text=compressed,
        kind=ctype.value,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        reversible=ref is not None,
        ref=ref,
        fidelity=measured_fidelity,
        cost_saved_usd=cost_saved,
        reverted=reverted,
    )


def compress_text(text: str, config: Config | None = None, **overrides: Any) -> str:
    """Compress a single string and return the compressed string."""
    cfg = (config or get_config()).merged(**overrides)
    return compress_block(text, cfg).text


def _message_text(message: dict) -> tuple[str, bool]:
    """Return (text, is_structured). Supports str content and content-part lists."""
    content = message.get("content")
    if isinstance(content, str):
        return content, False
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return "\n".join(parts), True
    return "", False


def _set_message_text(message: dict, new_text: str, is_structured: bool) -> dict:
    out = dict(message)
    if not is_structured:
        out["content"] = new_text
        return out
    new_parts = []
    replaced = False
    for part in message.get("content", []):
        if isinstance(part, dict) and part.get("type") == "text" and not replaced:
            np = dict(part)
            np["text"] = new_text
            new_parts.append(np)
            replaced = True
        else:
            new_parts.append(part)
    out["content"] = new_parts
    return out


def compress(
    messages: list[dict],
    config: Config | None = None,
    *,
    keep_last: int = 4,
    **overrides: Any,
) -> list[dict]:
    """Compress a list of chat messages (standard role/content style).

    Strategy:
      - The system message is preserved verbatim (it anchors the prompt cache).
      - The most recent ``keep_last`` messages are preserved verbatim (recency).
      - Earlier messages that are near-duplicates of a previous message (repeated
        file pastes, re-pasted tracebacks) collapse to a back-pointer.
      - All other messages — especially ``tool`` / ``function`` outputs — are
        routed through the per-content-type compressors.
    """
    cfg = (config or get_config()).merged(**overrides)
    if not cfg.enabled or not messages:
        return messages

    n = len(messages)
    protected_tail = set(range(max(0, n - keep_last), n))

    out: list[dict] = []
    seen_texts: list[str] = []  # parallel to messages, "" where not eligible
    any_compressed = False
    for i, message in enumerate(messages):
        role = message.get("role")
        text, structured = _message_text(message)

        # Always keep the system prompt and the recent tail verbatim.
        if role == "system" or i in protected_tail or not text:
            out.append(message)
            seen_texts.append("")
            continue

        # Cross-message dedup: collapse a near-duplicate of an earlier message.
        if cfg.dedup and len(text) > 200:
            dup = find_duplicate(text, seen_texts)
            if dup is not None:
                ref = None
                if cfg.reversible:
                    ref = get_store(cfg.store_dir, cfg.store_ttl).put(text, kind="conversation")
                marker = f"[tokentrim: identical to message #{dup}; elided" + (
                    f" — tokentrim_retrieve {ref}]" if ref else "]"
                )
                any_compressed = True
                out.append(_set_message_text(message, marker, structured))
                seen_texts.append(text)
                continue

        # Tool outputs are the juiciest target — compress regardless of recency
        # unless they fall inside the protected tail (handled above).
        result = compress_block(text, cfg)
        if result.compressed_tokens < result.original_tokens:
            any_compressed = True
            out.append(_set_message_text(message, result.text, structured))
        else:
            out.append(message)
        seen_texts.append(text)

    if any_compressed:
        TELEMETRY.record(original=0, compressed=0, kind="conversation", is_call=True)
    return out


def compress_rag(
    chunks: list[str],
    query: str,
    config: Config | None = None,
    *,
    max_chunks: int | None = None,
    **overrides: Any,
) -> list[str]:
    """Rank retrieved chunks against ``query`` and compress the survivors."""
    cfg = (config or get_config()).merged(**overrides)
    if not cfg.enabled or not chunks:
        return chunks
    counter = _counter(cfg)
    before = sum(counter.count(c) for c in chunks)
    compressed = _RAG.compress_chunks(chunks, query, cfg, max_chunks=max_chunks)
    after = sum(counter.count(c) for c in compressed)
    TELEMETRY.record(original=before, compressed=after, kind="rag", is_call=True)
    return compressed


def retrieve(ref_or_text: str, config: Config | None = None) -> str | None:
    """Recover an original from the CCR store.

    Accepts a bare reference id or any string containing a ``[tokentrim:ref …]``
    marker (so an agent can paste the compressed block back in).
    """
    cfg = config or get_config()
    ref = ref_or_text.strip()
    match = _REF_RE.search(ref_or_text)
    if match:
        ref = match.group(1)
    return get_store(cfg.store_dir, cfg.store_ttl).retrieve(ref)
