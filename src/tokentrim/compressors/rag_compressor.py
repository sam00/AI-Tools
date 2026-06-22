"""RAG chunk compressor.

Retrieval pipelines over-fetch on purpose, then dump every chunk into the prompt.
This compressor scores each chunk against the query with a TF-IDF cosine
similarity (dependency-free), keeps the most relevant chunks within a token
budget, and applies extractive compression to the survivors. Off-topic chunks are
dropped entirely (and remain retrievable via CCR).
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from ..config import Config
from .text_compressor import TextCompressor

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]+")


def _terms(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text)]


def _tfidf_vectors(docs: list[list[str]]) -> list[dict[str, float]]:
    n = len(docs)
    df: Counter[str] = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    vectors: list[dict[str, float]] = []
    for doc in docs:
        tf = Counter(doc)
        length = max(1, len(doc))
        vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = math.log((1 + n) / (1 + df[term])) + 1.0
            vec[term] = (count / length) * idf
        vectors.append(vec)
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class ScoredChunk:
    index: int
    text: str
    score: float


class RagCompressor:
    kind = "rag"

    def __init__(self) -> None:
        self._text = TextCompressor()

    def rank(self, chunks: list[str], query: str) -> list[ScoredChunk]:
        docs = [_terms(c) for c in chunks]
        vectors = _tfidf_vectors(docs + [_terms(query)])
        query_vec = vectors[-1]
        scored = [
            ScoredChunk(index=i, text=chunks[i], score=_cosine(vectors[i], query_vec))
            for i in range(len(chunks))
        ]
        return sorted(scored, key=lambda c: c.score, reverse=True)

    def compress_chunks(
        self,
        chunks: list[str],
        query: str,
        config: Config,
        max_chunks: int | None = None,
    ) -> list[str]:
        if not chunks:
            return chunks
        ranked = self.rank(chunks, query)
        if max_chunks is None:
            max_chunks = max(1, int(len(chunks) * config.keep_ratio))
        keep = {c.index for c in ranked[:max_chunks] if c.score > 0} or {ranked[0].index}
        out: list[str] = []
        for i, chunk in enumerate(chunks):
            if i in keep:
                out.append(self._text.compress(chunk, config))
        return out

    def compress(self, text: str, config: Config) -> str:
        # When used as a plain block compressor (no query), fall back to text.
        return self._text.compress(text, config)
