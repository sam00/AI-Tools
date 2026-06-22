from tokentrim.router import ContentType, detect


def test_detect_json_array():
    assert detect('[{"a": 1}, {"a": 2}]') == ContentType.JSON


def test_detect_json_object():
    assert detect('{"name": "x", "items": [1, 2, 3]}') == ContentType.JSON


def test_detect_code_python():
    src = "import os\n\ndef foo(x):\n    return x + 1\n"
    assert detect(src) == ContentType.CODE


def test_detect_log():
    log = "\n".join(f"2026-06-20T10:00:{i:02d} INFO heartbeat" for i in range(10))
    assert detect(log) == ContentType.LOG


def test_detect_diff():
    diff = "diff --git a/x b/x\n@@ -1 +1 @@\n-old\n+new\n"
    assert detect(diff) == ContentType.DIFF


def test_detect_text_default():
    assert detect("Just a plain English sentence about nothing in particular.") == ContentType.TEXT


def test_detect_empty():
    assert detect("") == ContentType.TEXT
