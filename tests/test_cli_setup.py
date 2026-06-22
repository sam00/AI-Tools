"""Tests for the additive onboarding commands: setup / doctor / quickstart.

These commands are configuration/printing helpers only; they must never touch
the compression pipeline or mutate global config in a way that leaks across
tests.
"""

from __future__ import annotations

import json

from tokentrim import config as config_mod
from tokentrim.cli import main


def _json_from_output(out: str) -> dict:
    """Extract the first balanced top-level JSON object from CLI output."""
    start = out.index("{")
    depth = 0
    for i in range(start, len(out)):
        if out[i] == "{":
            depth += 1
        elif out[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(out[start : i + 1])
    raise ValueError("no balanced JSON object found in output")


def test_setup_prints_mcp_snippet(capsys):
    rc = main(["setup"])
    out = capsys.readouterr().out
    assert rc == 0
    data = _json_from_output(out)
    assert "tokentrim" in data["mcpServers"]
    entry = data["mcpServers"]["tokentrim"]
    assert entry["args"][-1] == "mcp"
    assert isinstance(entry["command"], str) and entry["command"]


def test_setup_write_merges_and_preserves(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text(json.dumps({"mcpServers": {"other": {"command": "x", "args": []}}}))

    rc = main(["setup", "--write", "--config-path", str(cfg_file)])
    assert rc == 0

    data = json.loads(cfg_file.read_text())
    # Pre-existing server is preserved, ours is added.
    assert "other" in data["mcpServers"]
    assert data["mcpServers"]["tokentrim"]["args"][-1] == "mcp"


def test_setup_write_into_fresh_file(tmp_path):
    cfg_file = tmp_path / "nested" / "mcp.json"
    rc = main(["setup", "--write", "--config-path", str(cfg_file)])
    assert rc == 0
    data = json.loads(cfg_file.read_text())
    assert data["mcpServers"]["tokentrim"]["args"][-1] == "mcp"


def test_setup_default_prints_proxy_hint(capsys):
    rc = main(["setup"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "mcpServers" in out
    assert "tokentrim proxy" in out


def test_setup_write_requires_config_path(capsys):
    rc = main(["setup", "--write"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "--config-path" in err


def test_quickstart_runs(capsys):
    rc = main(["quickstart"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "TokenTrim quickstart" in out


def test_doctor_runs_without_mutating_global_config(tmp_path, capsys):
    saved = config_mod.get_config()
    try:
        config_mod.set_config(config_mod.Config(store_dir=str(tmp_path / "store")))
        rc = main(["doctor"])
    finally:
        config_mod.set_config(saved)
    out = capsys.readouterr().out
    assert rc == 0
    assert "tokentrim" in out
    assert "config" in out
    assert "self-test" in out
