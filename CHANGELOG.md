# Changelog

All notable changes to TokenTrim are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — Unreleased

Initial public release.

### Added
- **Content-aware compression pipeline** routing payloads to dedicated
  compressors: JSON (`SmartCrusher`), code (AST skeletons), logs (templating +
  `× N` collapse, error-preserving), diffs, tables, and prose (salience ranking).
- **RAG compression** — TF-IDF cosine ranking of chunks against a query.
- **Conversation compression** — preserves the system prompt and most recent
  messages; compresses tool/function outputs.
- **Quality gate** (`fidelity.py`) — important-token recall score that reverts
  lossy prose compression to the original when the answer would be lost.
- **Dedup engine** (`dedup.py`) — exact + near-duplicate collapse (SimHash and
  `difflib` sequence ratio) for blocks within a payload and re-pasted messages
  across a conversation.
- **Cost accounting** (`pricing.py`) — per-model USD/MTok pricing; results and
  telemetry report dollars saved.
- **TokenOpt** — markdown-emphasis and whitespace normalization for prose.
- **Reversible store (CCR)** — originals cached locally and recoverable by a
  short reference id, with TTL.
- **Secret redaction** — API keys, tokens, and private keys masked before
  compression and caching.
- **Three ways to run** — Python library, chat-completions compressing proxy
  (with optional exact-match response cache), and an MCP server.
- **CLI** — `compress`, `perf`, `retrieve`, `stats`, `proxy`, `mcp`, `version`.
- **Zero-dependency core**; optional extras for `proxy`, `mcp`, and `tokens`.
- Test suite, CI (Python 3.9–3.12), and examples.

### Security
- Local-first: no content leaves the machine except via the LLM provider you
  point the proxy at. Secrets are redacted pre-compression.

[0.1.0]: https://github.com/sam00/AI-Tools/releases/tag/v0.1.0
