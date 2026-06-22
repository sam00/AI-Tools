"""ContentRouter — detect the type of a payload and pick a compressor.

Detection is heuristic and ordered from most to least specific. It is designed to
be cheap (single pass over a sample of the text) and safe (defaults to ``text``,
which is always lossless-capable).
"""

from __future__ import annotations

import json
import re
from enum import Enum

_LOG_LINE_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        \d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}   # ISO timestamp
        | \[\d{2}:\d{2}:\d{2}\]                   # [HH:MM:SS]
        | (?:trace|debug|info|warn|warning|error|fatal|critical)\b
        | \w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}     # syslog
    )
    """
)

_CODE_HINTS = re.compile(
    r"(?m)^\s*(?:def |class |import |from \w+ import |func |package |public |private |"
    r"const |let |var |#include|fn |impl |export |async def )"
)

_DIFF_HINTS = re.compile(r"(?m)^(?:diff --git|@@ |\+\+\+ |--- |index [0-9a-f]+)")


class ContentType(str, Enum):
    JSON = "json"
    CODE = "code"
    LOG = "log"
    DIFF = "diff"
    TABLE = "table"
    TEXT = "text"


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    if not s or s[0] not in "[{":
        return False
    try:
        json.loads(s)
        return True
    except (ValueError, RecursionError):
        # Tolerate JSONL (one object per line) and truncated tool output.
        head = s.splitlines()[0].strip()
        if head and head[0] in "[{":
            try:
                json.loads(head)
                return True
            except ValueError:
                return False
        return False


def _log_line_ratio(text: str, sample_lines: int = 200) -> float:
    lines = [ln for ln in text.splitlines() if ln.strip()][:sample_lines]
    if not lines:
        return 0.0
    hits = sum(1 for ln in lines if _LOG_LINE_RE.search(ln))
    return hits / len(lines)


def _table_ratio(text: str, sample_lines: int = 60) -> float:
    lines = [ln for ln in text.splitlines() if ln.strip()][:sample_lines]
    if len(lines) < 3:
        return 0.0
    pipe = sum(1 for ln in lines if ln.count("|") >= 2)
    comma = sum(1 for ln in lines if ln.count(",") >= 2)
    return max(pipe, comma) / len(lines)


def detect(text: str) -> ContentType:
    """Classify ``text`` into a :class:`ContentType`."""
    if not text or not text.strip():
        return ContentType.TEXT

    if _DIFF_HINTS.search(text):
        return ContentType.DIFF

    if _looks_like_json(text):
        return ContentType.JSON

    if _log_line_ratio(text) >= 0.4:
        return ContentType.LOG

    if _CODE_HINTS.search(text):
        return ContentType.CODE

    if _table_ratio(text) >= 0.6:
        return ContentType.TABLE

    return ContentType.TEXT
