"""Log compressor.

Logs are the highest-leverage target: agents paste thousands of repetitive lines
to find a single failure. This compressor:

- normalizes each line into a *template* (numbers, hex, uuids, timestamps masked)
  so near-identical lines collapse into one "× N" entry,
- always preserves WARN / ERROR / FATAL / CRITICAL lines verbatim plus a small
  context window around them,
- keeps the head and tail of the stream for orientation.

The original is recoverable via the CCR store, so nothing is truly lost.
"""

from __future__ import annotations

import re

from ..config import Config

_SEVERITY_RE = re.compile(r"(?i)\b(error|fatal|critical|exception|traceback|panic|fail(?:ed|ure)?|warn(?:ing)?)\b")
_HARD_SEVERITY_RE = re.compile(r"(?i)\b(error|fatal|critical|exception|traceback|panic)\b")

_MASKS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<hex>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"), "<ts>"),
    (re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"), "<time>"),
    (re.compile(r"\b\d+\b"), "<n>"),
]


def _template(line: str) -> str:
    out = line
    for pattern, repl in _MASKS:
        out = pattern.sub(repl, out)
    return out.strip()


class LogCompressor:
    kind = "log"

    def compress(self, text: str, config: Config) -> str:
        lines = text.splitlines()
        if len(lines) < 8:
            return text

        keep = config.keep_ratio
        head_n = 5 if keep >= 0.4 else 3
        tail_n = 5 if keep >= 0.4 else 3
        context = 2 if keep >= 0.4 else 1

        # Indices we must keep verbatim: severity lines + surrounding context + head/tail.
        force_keep: set[int] = set(range(min(head_n, len(lines))))
        force_keep |= set(range(max(0, len(lines) - tail_n), len(lines)))
        for i, ln in enumerate(lines):
            if _SEVERITY_RE.search(ln):
                for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                    force_keep.add(j)

        out: list[str] = []
        i = 0
        run_template: str | None = None
        run_count = 0
        run_example = ""

        def flush_run() -> None:
            nonlocal run_template, run_count, run_example
            if run_template is None:
                return
            if run_count == 1:
                out.append(run_example)
            else:
                out.append(f"{run_example}    [× {run_count} similar lines]")
            run_template, run_count, run_example = None, 0, ""

        while i < len(lines):
            ln = lines[i]
            if i in force_keep:
                flush_run()
                out.append(ln)
                i += 1
                continue

            tmpl = _template(ln)
            if tmpl == run_template:
                run_count += 1
            else:
                flush_run()
                run_template, run_count, run_example = tmpl, 1, ln
            i += 1

        flush_run()

        compressed = "\n".join(out)
        # Guard: if collapsing didn't help (already-unique lines), keep original.
        if len(compressed) >= len(text):
            return text
        return compressed
