import json

from tokentrim.compressors.code_compressor import CodeCompressor
from tokentrim.compressors.json_compressor import JsonCompressor
from tokentrim.compressors.log_compressor import LogCompressor
from tokentrim.compressors.rag_compressor import RagCompressor
from tokentrim.compressors.text_compressor import TextCompressor
from tokentrim.config import Config

CFG = Config(level="balanced")


def test_json_record_array_collapses():
    records = [{"id": i, "status": "ok", "v": i * 2} for i in range(100)]
    out = JsonCompressor().compress(json.dumps(records), CFG)
    parsed = json.loads(out)
    assert parsed["__condensed_records__"] == 100
    assert "id" in parsed["keys"]
    assert parsed["elided"] > 0
    assert len(out) < len(json.dumps(records))


def test_json_invalid_is_safe():
    bad = "{not valid json"
    assert JsonCompressor().compress(bad, CFG) == bad


def test_log_collapses_repeats_and_keeps_errors():
    lines = [f"2026-06-20T10:00:{i:02d} INFO heartbeat ok" for i in range(40)]
    lines.append("2026-06-20T10:01:00 ERROR disk full on /dev/sda1")
    log = "\n".join(lines)
    out = LogCompressor().compress(log, CFG)
    assert "ERROR disk full" in out
    assert "similar lines" in out
    assert len(out) < len(log)


def test_code_python_skeleton_keeps_signatures():
    src = (
        "import os\n\n"
        "def add(a, b):\n"
        '    """Add two numbers."""\n'
        "    result = a + b\n"
        "    return result\n\n"
        "class Foo:\n"
        "    def bar(self):\n"
        "        x = 1\n"
        "        return x\n"
    )
    out = CodeCompressor().compress(src, CFG)
    assert "def add(a, b):" in out
    assert "class Foo:" in out
    assert "body elided" in out or "methods" in out


def test_text_extractive_shrinks():
    sentence = "The integration suite is the slowest part of the pipeline. "
    filler = "This is some filler text that repeats and adds little signal. " * 20
    text = sentence + filler
    out = TextCompressor().compress(text, CFG)
    assert len(out) < len(text)


def test_rag_ranks_relevant_chunk_first():
    chunks = [
        "Bananas are yellow and grow in tropical climates.",
        "The payment service charges credit cards via the gateway and records the txn id.",
        "The weather today is sunny with a light breeze.",
    ]
    ranked = RagCompressor().rank(chunks, "how does the payment service charge cards")
    assert ranked[0].index == 1
