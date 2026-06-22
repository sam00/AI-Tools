import pytest

from tokentrim import (
    Config,
    compress,
    compress_block,
    cost_for_tokens,
    fidelity,
    near_duplicate,
    simhash,
)
from tokentrim.config import set_config
from tokentrim.dedup import dedup_blocks, find_duplicate
from tokentrim.pricing import input_price_per_mtok

# --- fidelity ---

def test_fidelity_identical_is_one():
    text = "Error 500 at PaymentProcessor.charge after 3 retries on host db-01"
    assert fidelity(text, text) == 1.0


def test_fidelity_drops_when_tokens_lost():
    original = "Error 500 at PaymentProcessor.charge host db-01 amount 4200 txn_id ABC123"
    compressed = "Some generic summary with no specifics."
    assert fidelity(original, compressed) < 0.3


def test_fidelity_no_important_tokens():
    assert fidelity("just some plain filler words here", "kept") == 1.0


# --- dedup ---

def test_simhash_stable_and_near_dup():
    base = (
        "the worker crashed with a connection error after several retries "
        "while contacting the primary database host in the east region cluster "
    )
    a = base + "and the latency was 142 milliseconds before timing out"
    b = base + "and the latency was 153 milliseconds before timing out"
    assert simhash(a) == simhash(a)  # deterministic fingerprint
    assert near_duplicate(a, b)      # one-number diff in a long string


def test_dedup_collapses_repeated_blocks():
    block = "Traceback (most recent call last):\n  File x, line 1\n  ConnectionError: refused"
    text = "\n\n".join([block] * 6)
    out = dedup_blocks(text)
    assert "near-identical blocks collapsed" in out
    assert len(out) < len(text)


def test_find_duplicate_index():
    long_a = (
        "the database migration completed in 12 seconds successfully after applying "
        "all 37 pending schema changes to the inventory and orders tables without errors"
    )
    long_b = long_a.replace("12 seconds", "13 seconds")
    prior = ["totally unrelated text about tropical fruit and weather patterns today", long_a]
    assert find_duplicate(long_b, prior) == 1


# --- pricing ---

def test_pricing_known_model():
    assert input_price_per_mtok("premium") == 15.00
    assert cost_for_tokens(1_000_000, "premium") == pytest.approx(15.00)


def test_pricing_unknown_model_default():
    assert input_price_per_mtok("some-unknown-model") > 0


# --- quality gate (integration) ---

@pytest.fixture()
def cfg(tmp_path):
    config = Config(min_tokens=20, store_dir=str(tmp_path / "s"), store_ttl=600)
    set_config(config)
    return config


def test_quality_gate_reverts_when_fidelity_low(cfg):
    # A high threshold forces the gate to reject lossy text compression.
    cfg = cfg.merged(quality_threshold=0.99)
    text = (
        "The pipeline has three stages named build, test, and deploy. "
        "Build produces image SHA a1b2c3. Test runs suite 7 for 420 seconds. "
        "Deploy promotes to prod behind flag FX-9. "
    ) * 6
    result = compress_block(text, cfg)
    assert result.reverted is True
    assert result.text == text  # original returned verbatim


def test_quality_gate_allows_good_compression(cfg):
    cfg = cfg.merged(quality_threshold=0.0)  # disable gate
    text = "This sentence repeats with little new signal. " * 60
    result = compress_block(text, cfg)
    assert result.compressed_tokens <= result.original_tokens


def test_block_reports_cost_saved(cfg):
    import json

    records = [{"id": i, "status": "ok"} for i in range(200)]
    result = compress_block(json.dumps(records), cfg.merged(model="premium"))
    assert result.cost_saved_usd > 0


def test_cross_message_dedup(cfg):
    pasted_file = "def handler(event):\n    return process(event)\n" + ("# comment line\n" * 40)
    messages = [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Here is the file:\n" + pasted_file},
        {"role": "assistant", "content": "Got it."},
        {"role": "user", "content": "Here is the file again:\n" + pasted_file},
        {"role": "user", "content": "now what?"},
        {"role": "user", "content": "final"},
    ]
    out = compress(messages, cfg, keep_last=2)
    # Message index 3 duplicates index 1 → collapsed to a back-pointer.
    assert "identical to message" in out[3]["content"]
    assert len(out[3]["content"]) < len(messages[3]["content"])
