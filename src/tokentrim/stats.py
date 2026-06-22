"""Lightweight, thread-safe telemetry for compression savings."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class Stats:
    calls: int = 0
    blocks: int = 0
    original_tokens: int = 0
    compressed_tokens: int = 0
    secrets_redacted: int = 0
    cost_saved_usd: float = 0.0
    reverted_low_quality: int = 0
    fidelity_sum: float = 0.0
    fidelity_n: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    @property
    def avg_fidelity(self) -> float:
        return (self.fidelity_sum / self.fidelity_n) if self.fidelity_n else 1.0

    @property
    def saved_tokens(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return 1.0 - (self.compressed_tokens / self.original_tokens)

    def to_dict(self) -> dict:
        return {
            "calls": self.calls,
            "blocks": self.blocks,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "saved_tokens": self.saved_tokens,
            "reduction_pct": round(self.ratio * 100, 1),
            "cost_saved_usd": round(self.cost_saved_usd, 4),
            "avg_fidelity": round(self.avg_fidelity, 3),
            "reverted_low_quality": self.reverted_low_quality,
            "secrets_redacted": self.secrets_redacted,
            "by_kind": dict(self.by_kind),
        }


class _Telemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats = Stats()

    def record(
        self,
        *,
        original: int,
        compressed: int,
        kind: str,
        secrets: int = 0,
        cost_saved: float = 0.0,
        fidelity: float | None = None,
        reverted: bool = False,
        is_call: bool = False,
    ) -> None:
        with self._lock:
            if is_call:
                self._stats.calls += 1
            self._stats.blocks += 1
            self._stats.original_tokens += original
            self._stats.compressed_tokens += compressed
            self._stats.secrets_redacted += secrets
            self._stats.cost_saved_usd += cost_saved
            if reverted:
                self._stats.reverted_low_quality += 1
            if fidelity is not None:
                self._stats.fidelity_sum += fidelity
                self._stats.fidelity_n += 1
            self._stats.by_kind[kind] = self._stats.by_kind.get(kind, 0) + (original - compressed)

    def snapshot(self) -> Stats:
        with self._lock:
            s = self._stats
            return Stats(
                calls=s.calls,
                blocks=s.blocks,
                original_tokens=s.original_tokens,
                compressed_tokens=s.compressed_tokens,
                secrets_redacted=s.secrets_redacted,
                cost_saved_usd=s.cost_saved_usd,
                reverted_low_quality=s.reverted_low_quality,
                fidelity_sum=s.fidelity_sum,
                fidelity_n=s.fidelity_n,
                by_kind=dict(s.by_kind),
            )

    def reset(self) -> None:
        with self._lock:
            self._stats = Stats()


TELEMETRY = _Telemetry()


def get_stats() -> Stats:
    return TELEMETRY.snapshot()


def reset_stats() -> None:
    TELEMETRY.reset()
