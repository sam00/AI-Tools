"""Secret redaction.

Runs before compression so that credentials never leave the machine inside a
compressed prompt. Redaction is reversible-aware: the redacted token records the
secret kind so logs remain readable while values are masked.
"""

from __future__ import annotations

import re

# (kind, pattern) — ordered most-specific first.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    (
        "bearer_token",
        re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._-]{16,}"),
    ),
    (
        "assignment_secret",
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*(?:password|passwd|secret|api[_-]?key|token|access[_-]?key))"
            r"\b\s*[:=]\s*[\"']?([^\s\"',}]{6,})[\"']?"
        ),
    ),
]


def redact(text: str) -> tuple[str, int]:
    """Mask secrets in ``text``.

    Returns the redacted text and the number of secrets masked.
    """
    if not text:
        return text, 0

    count = 0

    def _mask_assignment(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}=<redacted:assignment_secret>"

    def _mask_bearer(m: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)} <redacted:bearer_token>"

    out = text
    for kind, pattern in _PATTERNS:
        if kind == "assignment_secret":
            out, n = pattern.subn(_mask_assignment, out)
            count += 0  # counted inside callback
        elif kind == "bearer_token":
            out, n = pattern.subn(_mask_bearer, out)
        else:
            out, n = pattern.subn(f"<redacted:{kind}>", out)
            count += n
    return out, count
