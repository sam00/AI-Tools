# Introduction to TokenTrim

**TokenTrim is the context-compression layer for AI agents.** It sits
between your agent and the LLM and shrinks everything the model reads — tool
outputs, logs, RAG chunks, source files, and conversation history — *before* it
costs you tokens, latency, and context window. Same answers, a fraction of the
input.

---

## The problem

Most of what an AI agent reads is **low-density**. A 5,000-line log is mostly
identical heartbeats wrapped around one `FATAL`. A 200-record JSON dump has three
rows that matter. An agent re-reads the same file, the same traceback, the same
system prompt turn after turn. You pay full price — in dollars, latency, and a
crowded context window — for tokens that carry almost no signal.

The usual fixes each have a catch:

- **Truncate / sliding window** — cheap, but irreversibly drops information and
  is blind to structure (it'll cut a JSON array in half).
- **Summarize with another LLM call** — adds cost and latency, is
  non-deterministic, and can hallucinate or silently lose the one detail you
  needed.
- **Do nothing** — bills pile up and the context window fills with noise.

TokenTrim takes a different path: **structure-aware, deterministic,
reversible compression that keeps the signal and drops the redundancy.**

---

## What it does — capabilities

| Capability | What it gives you |
| --- | --- |
| **Content-aware routing** | Detects each payload's type and sends it to a dedicated compressor instead of one blunt strategy. |
| **JSON `SmartCrusher`** | Collapses big record arrays into *schema + sample rows + count* — the shape and a taste, not 200 near-identical objects. |
| **Code compressor (AST)** | Keeps imports, signatures, and docstrings; elides function bodies. The "API surface" survives; the boilerplate doesn't. |
| **Log compressor** | Templates repeated lines into `× N` and **always preserves WARN/ERROR/FATAL** plus surrounding context. |
| **RAG compressor** | Ranks chunks by TF-IDF cosine to the query and keeps only what's relevant, within a budget. |
| **Prose compressor + TokenOpt** | Ranks sentences by salience, preserves order/headings, and strips markdown/whitespace noise. |
| **Dedup engine** | Collapses exact **and near-duplicate** blocks (SimHash + sequence ratio) and re-pasted messages across a conversation — where ~70% of long-thread tokens hide. |
| **Quality gate** | Scores answer-token retention and **reverts lossy prose compression to the original** if too much signal would be lost. Compress hard, never silently. |
| **Reversible store (CCR)** | Every compressed block can carry a short reference id; the original is cached locally and recoverable on demand. |
| **Secret redaction** | Masks API keys, tokens, and private keys **before** compression or caching. |
| **Cost accounting** | Converts token savings into dollars using per-model pricing, reported per call and in telemetry. |
| **Three ways to run** | A Python library, a drop-in **chat-completions proxy** (with optional exact-match response cache), and an **MCP server**. |

On the bundled sample workloads, `tokentrim perf` shows **~88–90% fewer input
tokens** overall (60–98% per content type), with prose protected by the quality
gate and structured types fully recoverable.

---

## How it works (in one line)

```
redact → route → dedup → compress → quality-gate → cache (reversible) → account
```

Every stage is **deterministic**, single-pass, and **fail-open**: malformed input,
or anything that wouldn't shrink (or wouldn't keep enough of the answer), is
passed through unchanged.

---

## How it's better than other tools

TokenTrim isn't trying to be a smarter summarizer — it's a different,
complementary layer. Here's how it compares to the common alternatives:

| Approach | Limitation | TokenTrim |
| --- | --- | --- |
| **Naive truncation / sliding window** | Blind to structure; irreversibly drops data; can cut JSON/code mid-object. | Structure-aware per type; **reversible** via reference ids. |
| **LLM summarization** | Extra API call (cost + latency); non-deterministic; can hallucinate or drop the key detail. | No model call; **deterministic**; never invents text; signal preserved or reverted. |
| **ML prompt-pruning** | Powerful but needs a model + heavy deps (often a GPU); probabilistic; not tuned for JSON/log/diff structure; not reversible. | **Zero-dependency core**, pure stdlib; structure-specific compressors; reversible; runs anywhere, including CI. |
| **Prompt / response caches** | Only help on *repeat* traffic; do nothing for a large first-time payload. | Reduces **first-call** tokens too — and still ships an exact-match response cache in the proxy for the repeat case. |
| **Other heuristic compressors** | Often carry ML extras; less deterministic; typically no built-in redaction/quality gate/dedup/cost. | Adds a **dependency-free core, deterministic tests, a fidelity quality gate, a near-duplicate dedup engine, secret redaction, and dollar accounting.** |

### What makes it stand out

- **Local-first & private.** Compression happens on your machine; the core has
  **zero third-party runtime dependencies**. Your data isn't shipped to a
  compression service.
- **Reversible by design.** Compression is lossy *for the prompt*, not for you —
  originals are recoverable on demand, so aggressive savings stay safe.
- **Quality you can trust.** A measurable fidelity gate protects prose from
  losing the answer, instead of hoping a summarizer got it right.
- **Honest economics.** It reports the dollars it saves per model, so the value
  is visible, not assumed.
- **Drops into any stack.** Library call, chat-completions base-URL swap, or MCP
  tool — no rewrite required.

---

## Who it's for

- **Agent builders** paying for bloated tool outputs and long histories.
- **RAG pipelines** that over-stuff context with marginally-relevant chunks.
- **Anyone on a token budget** who wants bigger effective context windows and
  lower bills without sacrificing answer quality.

> Start with `tokentrim perf` to see the savings on sample data, then point your
> agent at the library, proxy, or MCP server. See [`README.md`](./README.md) for
> usage and [`REQUIREMENTS.md`](./REQUIREMENTS.md) for the full spec.
