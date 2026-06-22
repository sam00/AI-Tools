"""TokenTrim — the context compression layer for AI agents.

Compress everything your agent reads — tool outputs, logs, RAG chunks, files, and
conversation history — before it reaches the LLM. Same answers, a fraction of the
tokens. Local-first, reversible, dependency-free core.

Author: Sam Gupta
License: Apache-2.0
"""

from __future__ import annotations

from .compressors.base import CompressResult
from .config import Config, get_config, set_config
from .core import (
    compress,
    compress_block,
    compress_rag,
    compress_text,
    retrieve,
)
from .dedup import near_duplicate, simhash
from .fidelity import fidelity
from .pricing import cost_for_tokens, set_price
from .router import ContentType, detect
from .stats import Stats, get_stats, reset_stats
from .tokens import count_tokens

__version__ = "0.1.0"
__author__ = "Sam Gupta"

__all__ = [
    "Config",
    "CompressResult",
    "ContentType",
    "Stats",
    "compress",
    "compress_block",
    "compress_rag",
    "compress_text",
    "cost_for_tokens",
    "count_tokens",
    "detect",
    "fidelity",
    "get_config",
    "get_stats",
    "near_duplicate",
    "reset_stats",
    "retrieve",
    "set_config",
    "set_price",
    "simhash",
    "__version__",
    "__author__",
]
