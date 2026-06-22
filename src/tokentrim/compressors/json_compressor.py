"""SmartCrusher — structure-aware JSON / JSONL compression.

Large tool outputs are usually arrays of near-identical records. Instead of
sending every row, the crusher keeps the *shape* (keys/types), a few
representative samples, and a count of what was elided. Nested objects are
recursed; long scalar strings are truncated. The result is still valid,
human-readable, and conveys the same answer at a fraction of the tokens.
"""

from __future__ import annotations

import json
from typing import Any

from ..config import Config

_MAX_STRING_CHARS = 280


def _truncate_str(s: str, limit: int = _MAX_STRING_CHARS) -> str:
    if len(s) <= limit:
        return s
    head = s[: limit - 20]
    return f"{head}…(+{len(s) - len(head)} chars)"


def _sample_count(level_keep: float) -> int:
    # More aggressive level => fewer sample rows.
    if level_keep >= 0.6:
        return 3
    if level_keep >= 0.4:
        return 2
    return 1


def _is_record_array(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 4
        and sum(1 for v in value if isinstance(v, dict)) >= max(3, int(len(value) * 0.6))
    )


def _key_signature(records: list[dict]) -> str:
    keys: dict[str, str] = {}
    for rec in records[:50]:
        for k, v in rec.items():
            if k not in keys:
                keys[k] = type(v).__name__
    return ", ".join(f"{k}:{t}" for k, t in keys.items())


def _crush(value: Any, keep: float, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _truncate_str(value)

    if isinstance(value, dict):
        return {k: _crush(v, keep, depth + 1) for k, v in value.items()}

    if _is_record_array(value):
        n = len(value)
        samples = _sample_count(keep)
        kept = [_crush(v, keep, depth + 1) for v in value[:samples]]
        sig = _key_signature([v for v in value if isinstance(v, dict)])
        return {
            "__condensed_records__": n,
            "keys": sig,
            "samples": kept,
            "elided": max(0, n - samples),
        }

    if isinstance(value, list):
        # Scalar / mixed array: keep head + tail, drop the middle.
        if len(value) <= 8:
            return [_crush(v, keep, depth + 1) for v in value]
        head = [_crush(v, keep, depth + 1) for v in value[:4]]
        tail = [_crush(v, keep, depth + 1) for v in value[-2:]]
        return head + [f"…(+{len(value) - 6} more items)"] + tail

    return value


class JsonCompressor:
    kind = "json"

    def compress(self, text: str, config: Config) -> str:
        stripped = text.strip()
        try:
            data = json.loads(stripped)
            crushed = _crush(data, config.keep_ratio)
            return json.dumps(crushed, ensure_ascii=False, separators=(",", ":"))
        except (ValueError, RecursionError):
            return self._compress_jsonl(stripped, config)

    def _compress_jsonl(self, text: str, config: Config) -> str:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        objs = []
        for ln in lines:
            try:
                objs.append(json.loads(ln))
            except ValueError:
                return text  # not JSONL after all — leave untouched
        if not objs:
            return text
        crushed = _crush(objs, config.keep_ratio)
        return json.dumps(crushed, ensure_ascii=False, separators=(",", ":"))
