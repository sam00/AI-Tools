"""Extractive text compressor (dependency-free).

Prose, docs, and RAG passages are compressed by ranking sentences with a TF-based
salience score (term frequency of content words + positional prior + a bonus for
sentences that carry signal terms such as numbers, identifiers, or imperative
verbs). The highest-ranked sentences are kept in their original order so the
output reads naturally. Markdown headings are always preserved as anchors.

No model download, no network — runs anywhere an agent runs.
"""

from __future__ import annotations

import math
import re

from ..config import Config

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]+")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_SIGNAL = re.compile(r"(?i)\b(must|should|never|always|error|fail|because|therefore|note|warning|important|return|raises?)\b")

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "it", "this", "that",
    "these", "those", "as", "at", "by", "from", "into", "than", "then", "so",
    "if", "we", "you", "they", "he", "she", "i", "our", "your", "their", "its",
    "can", "will", "would", "could", "may", "might", "do", "does", "did", "not",
}

_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)


def normalize_text(text: str) -> str:
    """TokenOpt pass: drop markdown emphasis markers and collapse whitespace.

    These markers cost tokens but carry no information a model needs. Code is not
    routed here, so this is safe for prose/tables.
    """
    out = _EMPHASIS.sub(r"\2", text)
    out = _TRAILING_WS.sub("", out)
    out = _MULTISPACE.sub(" ", out)
    out = _MULTINEWLINE.sub("\n\n", out)
    return out


def _split_blocks(text: str) -> list[str]:
    # Preserve paragraph boundaries.
    return [b for b in re.split(r"\n\s*\n", text) if b.strip()]


def _sentences(block: str) -> list[str]:
    parts = _SENT_SPLIT.split(block.strip())
    return [p.strip() for p in parts if p.strip()]


def _content_words(s: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(s) if w.lower() not in _STOPWORDS and len(w) > 2]


class TextCompressor:
    kind = "text"

    def compress(self, text: str, config: Config) -> str:
        if getattr(config, "normalize_whitespace", False):
            text = normalize_text(text)
        if len(text) < 400:
            return text

        blocks = _split_blocks(text)

        # Build a corpus-wide term frequency table.
        tf: dict[str, int] = {}
        sentences: list[tuple[int, str, bool]] = []  # (global_index, sentence, is_heading)
        idx = 0
        for block in blocks:
            if _HEADING.match(block):
                sentences.append((idx, block.strip(), True))
                idx += 1
                continue
            for sent in _sentences(block):
                for w in _content_words(sent):
                    tf[w] = tf.get(w, 0) + 1
                sentences.append((idx, sent, False))
                idx += 1

        if not tf:
            return text

        max_tf = max(tf.values())

        def score(global_index: int, sent: str) -> float:
            words = _content_words(sent)
            if not words:
                return 0.0
            base = sum(tf.get(w, 0) / max_tf for w in words) / math.sqrt(len(words))
            position = 1.0 if global_index < 2 else 0.0  # lead bias
            signal = 0.6 if _SIGNAL.search(sent) else 0.0
            return base + position + signal

        non_heading = [(i, s) for (i, s, h) in sentences if not h]
        scored = sorted(non_heading, key=lambda x: score(x[0], x[1]), reverse=True)

        target = max(1, int(len(non_heading) * config.keep_ratio))
        keep_indices = {i for (i, _s) in scored[:target]}

        out: list[str] = []
        for global_index, sent, is_heading in sentences:
            if is_heading or global_index in keep_indices:
                out.append(sent)

        result = " ".join(out)
        # Re-insert blank lines around headings for readability.
        result = re.sub(r"(?m)^(\s{0,3}#{1,6}\s.*)$", r"\n\1\n", result).strip()
        if len(result) >= len(text):
            return text
        return result
