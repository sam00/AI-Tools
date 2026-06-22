"""Base types shared by all compressors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import Config


@dataclass
class CompressResult:
    """The result of compressing a single block of content."""

    text: str
    kind: str
    original_tokens: int
    compressed_tokens: int
    reversible: bool = False
    ref: str | None = None
    fidelity: float = 1.0
    cost_saved_usd: float = 0.0
    reverted: bool = False

    @property
    def saved_tokens(self) -> int:
        return max(0, self.original_tokens - self.compressed_tokens)

    @property
    def ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return 1.0 - (self.compressed_tokens / self.original_tokens)


class Compressor(Protocol):
    """Interface implemented by every content-type compressor."""

    kind: str

    def compress(self, text: str, config: Config) -> str:
        """Return a compressed representation of ``text``.

        Implementations must be deterministic and must never raise on malformed
        input — they should degrade to returning the input unchanged.
        """
        ...
