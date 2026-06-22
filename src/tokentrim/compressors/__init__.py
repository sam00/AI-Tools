"""Compressor registry.

Maps a :class:`~tokentrim.router.ContentType` to a compressor instance. New
compressors can be registered without touching the core pipeline.
"""

from __future__ import annotations

from ..router import ContentType
from .base import Compressor, CompressResult
from .code_compressor import CodeCompressor
from .json_compressor import JsonCompressor
from .log_compressor import LogCompressor
from .rag_compressor import RagCompressor
from .text_compressor import TextCompressor

_TEXT = TextCompressor()

_REGISTRY: dict[ContentType, Compressor] = {
    ContentType.JSON: JsonCompressor(),
    ContentType.CODE: CodeCompressor(),
    ContentType.DIFF: CodeCompressor(),
    ContentType.LOG: LogCompressor(),
    ContentType.TABLE: _TEXT,
    ContentType.TEXT: _TEXT,
}


def get_compressor(content_type: ContentType) -> Compressor:
    return _REGISTRY.get(content_type, _TEXT)


def register(content_type: ContentType, compressor: Compressor) -> None:
    _REGISTRY[content_type] = compressor


__all__ = [
    "CompressResult",
    "Compressor",
    "CodeCompressor",
    "JsonCompressor",
    "LogCompressor",
    "RagCompressor",
    "TextCompressor",
    "get_compressor",
    "register",
]
