# TokenTrim — Requirements & Engineering Guide

**Author:** Sam Gupta
**Status:** v0.1 (Beta)
**Audience:** Engineers integrating TokenTrim into any IDE, agent, or framework.

This document is both the **product/engineering requirements specification** and a
**step-by-step install & configuration guide**. It is structured so it can be
reviewed as a design doc and later merged into a shared GitHub repository.

---

## 1. Overview

TokenTrim is a local-first **context compression layer** that sits between
an AI agent and its LLM provider. It compresses everything the agent reads — tool
outputs, logs, RAG chunks, files, and conversation history — before those tokens
reach the model, preserving the answer while cutting 60–95% of the tokens.

It can be consumed three ways:

1. **Library** — `from tokentrim import compress, compress_block, compress_rag`
2. **Proxy** — a drop-in chat-completions HTTP endpoint (zero code changes)
3. **MCP server** — `tokentrim_compress` / `tokentrim_retrieve` / `tokentrim_stats`
   tools for any MCP client

---

## 2. Goals & Non-Goals

### Goals
- **G1** Reduce input tokens by ≥60% on typical agent workloads with no loss of the operative answer.
- **G2** Run fully **local** — no content leaves the host; **no required network or ML dependencies** in the core.
- **G3** Be **reversible** — every compression is recoverable on demand within a TTL (CCR).
- **G4** Be **drop-in** — integrate into any IDE/agent without code changes (proxy) or via MCP.
- **G5** Be **deterministic & testable** — identical input ⇒ identical output; full unit-test coverage of compressors.
- **G6** **Fail safe** — never raise on malformed input; pass content through unchanged if it wouldn't shrink.

### Non-Goals
- **NG1** Not a model/inference server — it does not run an LLM.
- **NG2** Not a semantic re-writer — it does not paraphrase with an LLM (deterministic, extractive only).
- **NG3** Not a vector database — RAG ranking is in-request TF-IDF, not a persistent index.

---

## 3. Functional Requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Classify a payload into JSON / code / log / diff / table / text. |
| FR-2 | Compress JSON record arrays into *shape + samples + elided count*. |
| FR-3 | Compress source code into imports + signatures + docstrings; elide bodies (Python via AST). |
| FR-4 | Collapse repeated/templated log lines into `× N`, always preserving WARN/ERROR/FATAL + context. |
| FR-5 | Rank RAG chunks against a query (TF-IDF cosine) and keep only the relevant ones within a budget. |
| FR-6 | Compress prose extractively by sentence salience, preserving order and headings. |
| FR-7 | Compress a chat `messages[]` array, preserving the system prompt and the most recent N messages. |
| FR-8 | Store originals locally and recover them by reference id (CCR), honoring a TTL. |
| FR-9 | Redact secrets (API keys, tokens, private keys) before compression. |
| FR-10 | Expose a CLI (`compress`, `perf`, `retrieve`, `stats`, `proxy`, `mcp`, `version`). |
| FR-11 | Provide a chat-completions proxy that compresses `messages` and transparently forwards everything else. |
| FR-12 | Provide an MCP server exposing compress/retrieve/stats tools. |
| FR-13 | Emit telemetry (tokens in/out, savings, secrets redacted, by-kind breakdown). |
| FR-14 | **Quality gate:** measure fidelity (important-token recall) and revert lossy prose compression below `quality_threshold` to the original. |
| FR-15 | **Dedup:** collapse exact + near-duplicate blocks (SimHash + sequence ratio) within a payload and re-pasted messages across a conversation. |
| FR-16 | **TokenOpt:** strip markdown emphasis and collapse redundant whitespace on prose. |
| FR-17 | **Cost accounting:** convert token savings to USD via per-model pricing (overridable); report in results and telemetry. |
| FR-18 | **Response cache (proxy):** optionally skip identical upstream LLM calls via an exact-match cache. |

---

## 4. Non-Functional Requirements

| ID | Requirement |
| --- | --- |
| NFR-1 | **Performance:** compress ≤ ~1 MB of text in well under the network round-trip it saves (single pass, no model). |
| NFR-2 | **Security:** local-only; secrets masked pre-compression; CCR store is file-permission scoped to the user. |
| NFR-3 | **Portability:** Python 3.9+; core has **zero** third-party runtime deps; runs in sandboxes/CI. |
| NFR-4 | **Reliability:** never raises on bad input; memory-only fallback when the filesystem is read-only. |
| NFR-5 | **Observability:** `tokentrim stats` and proxy `/stats` expose cumulative savings; proxy adds `x-tokentrim-tokens-saved`. |
| NFR-6 | **Compatibility:** proxy speaks the standard `/v1/chat/completions` schema (streaming and non-streaming). |

---

## 5. Architecture

```
redact → route → compress → cache(CCR) → annotate
```

| Component | File | Responsibility |
| --- | --- | --- |
| `Config` | `config.py` | Settings resolution (kwargs > env > defaults), levels. |
| `TokenCounter` | `tokens.py` | Heuristic (default) or tiktoken token counts. |
| `redact` | `redact.py` | Mask secrets before anything else. |
| `ContentRouter` | `router.py` | Detect content type cheaply. |
| Compressors | `compressors/` | JSON / code / log / RAG / text crushers. |
| Dedup | `dedup.py` | Exact + near-duplicate (SimHash + sequence ratio) collapse. |
| Fidelity | `fidelity.py` | Important-token recall score for the quality gate. |
| Pricing | `pricing.py` | Per-model USD/MTok → dollar savings. |
| `ContentStore` | `store.py` | File-backed reversible cache (CCR) with TTL. |
| Pipeline | `core.py` | `compress_block` / `compress` / `compress_rag` / `retrieve` + quality gate. |
| Telemetry | `stats.py` | Thread-safe cumulative savings, cost, fidelity. |
| CLI | `cli.py` | User-facing commands. |
| Proxy | `proxy.py` | Chat-completions compressing proxy (FastAPI). |
| MCP | `mcp_server.py` | MCP tool surface. |

Full pipeline order: `redact → route → dedup → compress → quality-gate → cache(CCR) → annotate → account`.

**Data flow guarantees:** deterministic, single-pass, fail-open. The compressed
output embeds `[tokentrim:ref <id> +<n> tokens]` so any consumer can retrieve the
original via the CLI, library, or the `tokentrim_retrieve` MCP tool.

---

## 6. Prerequisites

- **Python 3.9+** (`python3 --version`)
- `pip` ≥ 21
- For the proxy: the `[proxy]` extra (FastAPI, uvicorn, httpx)
- For MCP: the `[mcp]` extra (the `mcp` SDK)
- An LLM provider API key if you use the proxy (e.g. `OPENAI_API_KEY`)

---

## 7. Installation (step by step)

### 7.1 Install from source (current state of this repo)

```bash
# 1. Clone / open the repository
cd tokentrim

# 2. Create an isolated environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install (pick the extras you need)
pip install -e ".[all]"          # library + proxy + mcp + tokens
#   or minimal:  pip install -e .

# 4. Verify
tokentrim version
tokentrim perf                   # prints a savings table
```

### 7.2 Install as a published package (after it ships to PyPI)

```bash
pip install "tokentrim[all]"
```

### 7.3 Configure (optional)

```bash
cp .env.example .env             # edit values as needed
# Settings are read from the environment; see the table in section 9.
```

---

## 8. IDE & Agent Integration

TokenTrim plugs into any IDE, agent, or framework through **two patterns**:

- **Pattern A — MCP tools:** the IDE/agent calls `tokentrim_compress` on big blobs
  before reasoning over them, and `tokentrim_retrieve` if it needs the original.
  Best for clients with first-class MCP support.
- **Pattern B — Proxy:** point the client's chat API base URL at the local proxy so
  *all* prompts are compressed automatically. Best for any client that speaks the
  standard `/v1/chat/completions` API.

> **Easiest path (no hand-editing JSON):** after installing, run `tokentrim setup`
> to print the MCP entry with the absolute `tokentrim` path already filled in, or
> `tokentrim setup --write --config-path <FILE>` to merge it into your client's JSON
> config. Then run `tokentrim doctor` to verify.

### 8.1 MCP clients (Pattern A)

Most MCP clients read a JSON config with a top-level `mcpServers` object. Add an
entry for TokenTrim — run `tokentrim setup` to generate it with the correct path:

```json
{
  "mcpServers": {
    "tokentrim": {
      "command": "/absolute/path/to/tokentrim",
      "args": ["mcp"],
      "env": {
        "TOKENTRIM_LEVEL": "balanced",
        "TOKENTRIM_STORE_DIR": "/absolute/path/to/.tokentrim/store"
      }
    }
  }
}
```

Reload the client and confirm the `tokentrim_compress`, `tokentrim_retrieve`, and
`tokentrim_stats` tools appear. If your client supports custom agent rules, add one
so it compresses automatically:

> "Before reasoning over any tool output, log, or file larger than ~300 tokens,
> call `tokentrim_compress` and work from the compressed result. Call
> `tokentrim_retrieve` only if you need an elided detail."

### 8.2 Proxy clients (Pattern B)

For any client or SDK that speaks the standard `/v1/chat/completions` API:

1. `tokentrim proxy --port 8787 --upstream <your-provider>/v1`
2. Set the client's API base URL (often `base_url` / `apiBase` / an "Override Base
   URL" setting) to `http://127.0.0.1:8787/v1` and keep your real API key.
3. Non-chat endpoints (models, embeddings, …) are forwarded transparently.

### 8.3 Library (your own code / framework)

Call the API directly in a pre-send hook:

```python
from tokentrim import compress, compress_block, compress_rag

messages = compress(messages)        # whole chat history
blob = compress_block(tool_output)   # a single large blob
```

---

## 9. Configuration Reference

| Env var | Default | Notes |
| --- | --- | --- |
| `TOKENTRIM_ENABLED` | `1` | Master switch. |
| `TOKENTRIM_LEVEL` | `balanced` | `light` (keep ~70%), `balanced` (~45%), `aggressive` (~25%). |
| `TOKENTRIM_MIN_TOKENS` | `300` | Content below this is passed through untouched. |
| `TOKENTRIM_REDACT_SECRETS` | `1` | Mask secrets before compression. |
| `TOKENTRIM_QUALITY_THRESHOLD` | `0.35` | Min prose fidelity to accept lossy compression; `0` disables the gate. |
| `TOKENTRIM_DEDUP` | `1` | Collapse exact + near-duplicate blocks and messages. |
| `TOKENTRIM_NORMALIZE_WHITESPACE` | `1` | TokenOpt whitespace/markdown pass on prose. |
| `TOKENTRIM_TOKENIZER` | `heuristic` | `tiktoken` for exact counts (requires `[tokens]`). |
| `TOKENTRIM_MODEL` | `default` | Model/tier name for cost estimates and the tiktoken backend. |
| `TOKENTRIM_INPUT_PRICE_PER_MTOK` | (auto) | Override USD/1M input tokens for unknown models. |
| `TOKENTRIM_STORE_DIR` | `.tokentrim/store` | CCR cache directory. |
| `TOKENTRIM_STORE_TTL` | `86400` | Seconds an original stays recoverable. |
| `TOKENTRIM_REVERSIBLE` | `1` | Embed retrieval markers + cache originals. |
| `TOKENTRIM_UPSTREAM_BASE_URL` | _(required)_ | Proxy upstream, e.g. `<your-provider>/v1`. |
| `TOKENTRIM_PROXY_HOST` | `127.0.0.1` | Keep loopback for security. |
| `TOKENTRIM_PROXY_PORT` | `8787` | Proxy port. |
| `TOKENTRIM_CACHE_RESPONSES` | `0` | Proxy exact-match response cache (skip identical LLM calls). |
| `TOKENTRIM_CACHE_TTL` | `3600` | Response cache TTL in seconds. |

---

## 10. Verification & Acceptance Criteria

Run these after install; all must pass.

```bash
# Unit tests + lint
pytest -q
ruff check src tests

# Functional smoke
tokentrim perf                                  # AC-1: TOTAL reduction ≥ 60%
echo '[{"a":1},{"a":2}]' | tokentrim compress - # AC-2: emits compressed JSON
tokentrim stats                                 # AC-3: telemetry renders

# Proxy smoke (in another shell)
tokentrim proxy --port 8787 &
curl -s localhost:8787/healthz                  # AC-4: {"status":"ok",...}
```

| ID | Acceptance criterion |
| --- | --- |
| AC-1 | `tokentrim perf` reports ≥60% total reduction on the bundled samples. |
| AC-2 | Compressing a 200-record JSON array yields a `__condensed_records__` summary. |
| AC-3 | A log with one `ERROR` keeps that line verbatim after compression. |
| AC-4 | `retrieve(ref)` returns a byte-identical original within TTL. |
| AC-5 | Malformed JSON / unknown content is returned unchanged (fail-open). |
| AC-6 | Proxy `/healthz` returns 200 and `/v1/chat/completions` forwards to upstream. |
| AC-7 | Secrets (e.g. `sk-…`) are masked in compressed output. |
| AC-8 | A re-pasted file / repeated traceback collapses to a back-pointer (dedup). |
| AC-9 | Lossy prose below `quality_threshold` reverts to the original (quality gate). |
| AC-10 | `tokentrim perf` reports per-row `$ saved` and projected monthly savings. |
| AC-11 | With `TOKENTRIM_CACHE_RESPONSES=1`, a repeated identical request returns `x-tokentrim-cache: hit`. |

---

## 11. Security & Privacy

- All compression happens **locally**; no content is sent anywhere except your
  chosen LLM provider (and only via the proxy you point at it).
- Secrets are **redacted before** compression and before caching.
- The CCR store is plain JSON on local disk under `TOKENTRIM_STORE_DIR`; restrict
  permissions and set a TTL appropriate to your data-retention policy. Add it to
  `.gitignore` (already done).
- Bind the proxy to `127.0.0.1` unless you intentionally need remote access; if
  you do, terminate TLS and add auth in front of it.

---

## 12. Rollout / Merge Plan (to shared GitHub)

1. Create the upstream repository (e.g. `org/tokentrim`).
2. Push this repo as the initial commit; open a PR for review against `main`.
3. CI: run `pytest` + `ruff` on push (GitHub Actions; matrix Python 3.9–3.12).
4. Tag `v0.1.0`; publish to an internal index or PyPI.
5. Announce MCP/proxy setup (sections 8.1–8.4) to engineering.
6. Track real-world savings via `tokentrim stats` / proxy `/stats` dashboards.

---

## 13. Roadmap

- Streaming **output-token** reduction (verbosity steering) in the proxy.
- Optional ML re-ranker for RAG behind an extra (kept out of the core).
- Cross-agent shared memory store with provenance + dedup.
- Per-content-type level overrides in `Config`.
- TypeScript/Node port of the library for in-process JS agents.
