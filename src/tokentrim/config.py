"""Configuration for TokenTrim.

Settings are resolved with the precedence:

    explicit kwargs  >  environment variables  >  built-in defaults

This keeps the library zero-config for first use while remaining fully tunable
in a proxy / server deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

# Compression levels map to a target "keep ratio" used by extractive compressors
# and a verbosity budget. Lower keep ratio => more aggressive compression.
LEVELS = {
    "light": 0.70,
    "balanced": 0.45,
    "aggressive": 0.25,
}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Config:
    """Runtime configuration."""

    enabled: bool = True
    level: str = "balanced"
    min_tokens: int = 300
    redact_secrets: bool = True
    tokenizer: str = "heuristic"
    model: str = "default"
    store_dir: str = ".tokentrim/store"
    store_ttl: int = 86_400
    # When True, every compressed block embeds a retrieval marker so the original
    # can be recovered on demand via the CCR store.
    reversible: bool = True
    # Quality gate: minimum fidelity (important-token recall) required to accept a
    # lossy text/table/code compression. 0 disables the gate. See tokentrim.fidelity.
    quality_threshold: float = 0.35
    # Collapse exact + near-duplicate blocks (and repeated messages) before compressing.
    dedup: bool = True
    # Strip markdown emphasis / collapse whitespace on prose (TokenOpt).
    normalize_whitespace: bool = True
    # Per-content-type overrides may be added here later without breaking callers.
    extra: dict = field(default_factory=dict)

    @property
    def keep_ratio(self) -> float:
        return LEVELS.get(self.level, LEVELS["balanced"])

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            enabled=_env_bool("TOKENTRIM_ENABLED", True),
            level=os.getenv("TOKENTRIM_LEVEL", "balanced"),
            min_tokens=_env_int("TOKENTRIM_MIN_TOKENS", 300),
            redact_secrets=_env_bool("TOKENTRIM_REDACT_SECRETS", True),
            tokenizer=os.getenv("TOKENTRIM_TOKENIZER", "heuristic"),
            model=os.getenv("TOKENTRIM_MODEL", "default"),
            store_dir=os.getenv("TOKENTRIM_STORE_DIR", ".tokentrim/store"),
            store_ttl=_env_int("TOKENTRIM_STORE_TTL", 86_400),
            reversible=_env_bool("TOKENTRIM_REVERSIBLE", True),
            quality_threshold=_env_float("TOKENTRIM_QUALITY_THRESHOLD", 0.35),
            dedup=_env_bool("TOKENTRIM_DEDUP", True),
            normalize_whitespace=_env_bool("TOKENTRIM_NORMALIZE_WHITESPACE", True),
        )

    def merged(self, **overrides) -> Config:
        """Return a copy with the given non-None overrides applied."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)


_active: Config | None = None


def get_config() -> Config:
    """Return the process-wide config, loading from env on first use."""
    global _active
    if _active is None:
        _active = Config.from_env()
    return _active


def set_config(config: Config) -> None:
    global _active
    _active = config
