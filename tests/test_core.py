import json

import pytest

from tokentrim import (
    Config,
    compress,
    compress_block,
    compress_rag,
    compress_text,
    retrieve,
)
from tokentrim.config import set_config


@pytest.fixture()
def cfg(tmp_path):
    config = Config(
        level="balanced",
        min_tokens=50,
        store_dir=str(tmp_path / "store"),
        store_ttl=3600,
    )
    set_config(config)
    return config


def test_passthrough_small_content(cfg):
    result = compress_block("short", cfg)
    assert result.kind == "passthrough"
    assert result.text == "short"


def test_block_compresses_large_json(cfg):
    records = [{"id": i, "status": "ok"} for i in range(200)]
    result = compress_block(json.dumps(records), cfg)
    assert result.compressed_tokens < result.original_tokens
    assert result.reversible is True
    assert result.ref is not None


def test_reversible_roundtrip(cfg):
    records = [{"id": i, "status": "ok", "payload": "x" * 20} for i in range(200)]
    original = json.dumps(records)
    result = compress_block(original, cfg)
    recovered = retrieve(result.text, cfg)  # pass full annotated text
    assert recovered == original


def test_retrieve_by_bare_ref(cfg):
    records = [{"id": i} for i in range(200)]
    original = json.dumps(records)
    result = compress_block(original, cfg)
    assert retrieve(result.ref, cfg) == original


def test_compress_messages_preserves_system_and_tail(cfg):
    big_log = "\n".join(f"2026-06-20T10:00:{i % 60:02d} INFO heartbeat ok" for i in range(200))
    messages = [
        {"role": "system", "content": "You are a helpful agent."},
        {"role": "user", "content": "Investigate the logs."},
        {"role": "tool", "content": big_log},
        {"role": "assistant", "content": "Looking now."},
        {"role": "user", "content": "Any errors?"},
    ]
    out = compress(messages, cfg, keep_last=2)
    assert out[0]["content"] == "You are a helpful agent."  # system preserved
    assert out[-1]["content"] == "Any errors?"  # tail preserved
    # The tool message (index 2) is outside the protected tail and should shrink.
    assert len(out[2]["content"]) < len(big_log)


def test_compress_rag_drops_offtopic(cfg):
    chunks = [
        "Bananas are yellow." * 30,
        "The payment service charges cards via the gateway and records txn ids." * 30,
        "The weather is sunny today." * 30,
    ]
    out = compress_rag(chunks, "payment service charge cards", cfg, max_chunks=1)
    assert len(out) == 1
    assert "payment" in out[0].lower()


def test_compress_text_convenience(cfg):
    text = "Important note: never share state between tests. " * 40
    out = compress_text(text, cfg)
    assert isinstance(out, str)
    assert len(out) <= len(text)
