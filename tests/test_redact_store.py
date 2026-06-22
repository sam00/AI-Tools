from tokentrim.redact import redact
from tokentrim.store import ContentStore


def test_redact_openai_key():
    text = "use key sk-abcdefghijklmnopqrstuvwxyz123456 to auth"
    out, n = redact(text)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out
    assert "<redacted:openai_key>" in out
    assert n >= 1


def test_redact_assignment_password():
    text = 'password="hunter2secret"'
    out, n = redact(text)
    assert "hunter2secret" not in out
    assert "redacted" in out


def test_redact_no_secret_unchanged():
    text = "nothing sensitive here, just words"
    out, n = redact(text)
    assert out == text
    assert n == 0


def test_store_put_get(tmp_path):
    store = ContentStore(str(tmp_path / "s"), ttl=3600)
    ref = store.put("hello original content", kind="text")
    assert store.retrieve(ref) == "hello original content"


def test_store_expiry(tmp_path):
    store = ContentStore(str(tmp_path / "s"), ttl=10)
    ref = store.put("transient", kind="text")
    # Backdate the entry beyond the TTL to force expiry on next access.
    store._mem[ref].created_at -= 100
    assert store.retrieve(ref) is None
