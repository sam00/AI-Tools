"""Command-line interface for TokenTrim.

    tokentrim compress [PATH]     compress a file or stdin, print result
    tokentrim perf                run the built-in savings demo
    tokentrim retrieve REF        recover an original from the CCR store
    tokentrim stats               show in-process telemetry
    tokentrim proxy               run the compressing chat-completions proxy
    tokentrim mcp                 run the MCP server (stdio)
    tokentrim setup               generate/write MCP client config
    tokentrim doctor              check install, extras, and config
    tokentrim quickstart          print copy-paste onboarding steps
    tokentrim version             print version
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys

from . import __version__
from .config import get_config
from .core import compress_block, retrieve
from .samples import SAMPLES
from .stats import get_stats
from .tokens import TokenCounter


def _read_input(path: str | None) -> str:
    if path and path != "-":
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return sys.stdin.read()


def _cmd_compress(args: argparse.Namespace) -> int:
    cfg = get_config().merged(level=args.level, min_tokens=args.min_tokens)
    text = _read_input(args.path)
    result = compress_block(text, cfg)
    sys.stdout.write(result.text)
    if not result.text.endswith("\n"):
        sys.stdout.write("\n")
    pct = round(result.ratio * 100, 1)
    sys.stderr.write(
        f"[tokentrim] kind={result.kind} "
        f"{result.original_tokens} → {result.compressed_tokens} tokens "
        f"({pct}% saved){' · reversible' if result.reversible else ''}\n"
    )
    return 0


def _cmd_perf(args: argparse.Namespace) -> int:
    from .core import GATED_KINDS
    from .pricing import cost_for_tokens, input_price_per_mtok

    cfg = get_config().merged(level=args.level, model=args.model, min_tokens=0)
    counter = TokenCounter(backend=cfg.tokenizer, model=cfg.model)
    total_before = total_after = 0
    gated_fidelities: list[float] = []
    print(f"TokenTrim perf demo  (level={cfg.level}, model={cfg.model}, "
          f"${input_price_per_mtok(cfg.model):.2f}/Mtok)\n")
    print(f"{'content':<9}{'before':>9}{'after':>9}{'saved':>8}{'quality':>10}{'$ saved':>10}")
    print("-" * 55)
    for kind, payload in SAMPLES.items():
        result = compress_block(payload, cfg)
        before = counter.count(payload)
        after = result.compressed_tokens
        total_before += before
        total_after += after
        pct = round((1 - after / before) * 100, 1) if before else 0.0
        saved_usd = cost_for_tokens(before - after, cfg.model)
        # Prose is quality-gated on measured fidelity; structured kinds are
        # reversible (originals recoverable on demand), shown as "rev".
        if result.kind in GATED_KINDS:
            gated_fidelities.append(result.fidelity)
            quality = f"{result.fidelity:.2f}"
        else:
            quality = "rev"
        print(f"{kind:<9}{before:>9}{after:>9}{pct:>7}%{quality:>10}{saved_usd:>10.5f}")
    print("-" * 55)
    overall = round((1 - total_after / total_before) * 100, 1) if total_before else 0.0
    total_saved_usd = cost_for_tokens(total_before - total_after, cfg.model)
    print(f"{'TOTAL':<9}{total_before:>9}{total_after:>9}{overall:>7}%{'':>10}{total_saved_usd:>10.5f}")
    if gated_fidelities:
        avg_fid = sum(gated_fidelities) / len(gated_fidelities)
        print(f"\nProse fidelity (quality-gated): {avg_fid:.2f}   "
              f"·  structured kinds are reversible via tokentrim_retrieve")
    print(f"Projected savings @ 10k calls/day: "
          f"${total_saved_usd * 10_000:.2f}/day  ·  ${total_saved_usd * 10_000 * 30:.2f}/month")
    return 0


def _cmd_retrieve(args: argparse.Namespace) -> int:
    original = retrieve(args.ref)
    if original is None:
        sys.stderr.write(f"[tokentrim] no entry for ref '{args.ref}' (expired or unknown)\n")
        return 1
    sys.stdout.write(original)
    if not original.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def _cmd_stats(_args: argparse.Namespace) -> int:
    import json

    print(json.dumps(get_stats().to_dict(), indent=2))
    return 0


def _cmd_proxy(args: argparse.Namespace) -> int:
    try:
        from .proxy import run_proxy
    except ImportError:
        sys.stderr.write(
            "[tokentrim] proxy extras not installed. Run: pip install 'tokentrim[proxy]'\n"
        )
        return 1
    run_proxy(host=args.host, port=args.port, upstream=args.upstream)
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    try:
        from .mcp_server import run_mcp
    except ImportError:
        sys.stderr.write(
            "[tokentrim] mcp extras not installed. Run: pip install 'tokentrim[mcp]'\n"
        )
        return 1
    run_mcp()
    return 0


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f"tokentrim {__version__}")
    return 0


_MCP_SERVER_NAME = "tokentrim"

QUICKSTART = """\
TokenTrim quickstart
====================

1) Library (in your own code)
   from tokentrim import compress_block, compress, compress_rag, retrieve
   result = compress_block(open("huge.log").read())
   print(result.text)            # compressed, with a [tokentrim:ref ...] marker
   original = retrieve(result.ref)

2) MCP server (any MCP-capable client)
   pip install "tokentrim[mcp]"
   tokentrim setup                                 # prints the MCP config entry
   tokentrim setup --write --config-path <FILE>    # merges it into your client config
   # then restart your client

3) Proxy (zero code changes, any chat-completions client)
   pip install "tokentrim[proxy]"
   tokentrim proxy --port 8787 --upstream <your-provider>/v1
   # point the client base URL at http://127.0.0.1:8787/v1

Verify anytime:  tokentrim doctor
See the savings: tokentrim perf
"""


def _resolve_mcp_command() -> tuple[str, list[str]]:
    """Return (command, args) to launch the MCP server, preferring the installed
    console script and falling back to ``python -m tokentrim``."""
    exe = shutil.which("tokentrim")
    if exe:
        return exe, ["mcp"]
    return sys.executable, ["-m", "tokentrim", "mcp"]


def _mcp_snippet() -> dict:
    command, cmd_args = _resolve_mcp_command()
    return {"mcpServers": {_MCP_SERVER_NAME: {"command": command, "args": cmd_args}}}


def _merge_mcp_config(path: str, snippet: dict) -> None:
    data: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}
    servers = data.setdefault("mcpServers", {})
    servers.update(snippet["mcpServers"])
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _cmd_setup(args: argparse.Namespace) -> int:
    snippet = _mcp_snippet()
    snippet_json = json.dumps(snippet, indent=2)

    if shutil.which("tokentrim") is None:
        sys.stderr.write(
            "[tokentrim] 'tokentrim' is not on PATH; the config uses a "
            "'python -m tokentrim' fallback.\n"
            "            For a clean global command: pipx install "
            '"git+https://github.com/sam00/AI-Tools.git"\n'
        )

    if args.write:
        if not args.config_path:
            sys.stderr.write(
                "[tokentrim] --write requires --config-path "
                "(your MCP client's JSON config file)\n"
            )
            return 1
        _merge_mcp_config(args.config_path, snippet)
        sys.stdout.write(
            f"[tokentrim] wrote MCP server entry to {args.config_path}\n"
            "[tokentrim] restart your client; confirm tokentrim_compress / "
            "tokentrim_retrieve / tokentrim_stats appear.\n"
        )
        return 0

    sys.stdout.write(
        "# MCP server entry — add to your MCP client's JSON config\n"
        '# (most clients use a top-level "mcpServers" object), or re-run with\n'
        "# --write --config-path <FILE> to merge it automatically:\n"
        f"{snippet_json}\n\n"
        "# Zero-code alternative — the proxy. Point your client's base URL at it:\n"
        "#   tokentrim proxy --port 8787 --upstream <your-provider>/v1\n"
        "#   base URL -> http://127.0.0.1:8787/v1\n"
    )
    return 0


def _store_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".tt_probe")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _cmd_doctor(_args: argparse.Namespace) -> int:
    import importlib.util

    def _have(*mods: str) -> bool:
        return all(importlib.util.find_spec(m) is not None for m in mods)

    cfg = get_config()
    exe = shutil.which("tokentrim")
    print(f"tokentrim {__version__}")
    print(
        f"  python      : {platform.python_version()} "
        f"({platform.system()} {platform.machine()})"
    )
    print(f"  executable  : {exe or '(not on PATH; try: pipx install ...)'}")
    print("  extras")
    print(f"    proxy     : {'yes' if _have('fastapi', 'uvicorn', 'httpx') else 'no'}")
    print(f"    mcp       : {'yes' if _have('mcp') else 'no'}")
    print(f"    tiktoken  : {'yes' if _have('tiktoken') else 'no'}")
    print("  config")
    print(f"    enabled   : {cfg.enabled}")
    print(f"    level     : {cfg.level}")
    print(f"    min_tokens: {cfg.min_tokens}")
    print(f"    tokenizer : {cfg.tokenizer}")
    print(f"    model     : {cfg.model}")
    print(f"    redact    : {cfg.redact_secrets}")
    print(f"    reversible: {cfg.reversible}")
    writable = _store_writable(cfg.store_dir)
    print(
        f"    store_dir : {cfg.store_dir} "
        f"({'writable' if writable else 'NOT writable'})"
    )
    sample = SAMPLES.get("log", "hello world\n" * 50)
    result = compress_block(sample, cfg.merged(min_tokens=0, reversible=False))
    print(
        f"  self-test   : log {result.original_tokens} -> "
        f"{result.compressed_tokens} tokens  (OK)"
    )
    return 0


def _cmd_quickstart(_args: argparse.Namespace) -> int:
    sys.stdout.write(QUICKSTART)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tokentrim", description=__doc__)
    parser.add_argument("--version", action="version", version=f"tokentrim {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_compress = sub.add_parser("compress", help="compress a file or stdin")
    p_compress.add_argument("path", nargs="?", default="-", help="file path or '-' for stdin")
    p_compress.add_argument("--level", choices=["light", "balanced", "aggressive"], default=None)
    p_compress.add_argument("--min-tokens", type=int, default=0, dest="min_tokens")
    p_compress.set_defaults(func=_cmd_compress)

    p_perf = sub.add_parser("perf", help="run the built-in savings demo")
    p_perf.add_argument("--level", choices=["light", "balanced", "aggressive"], default=None)
    p_perf.add_argument("--model", default=None, help="model/tier name for the cost estimate; unknown names use the default price")
    p_perf.set_defaults(func=_cmd_perf)

    p_ret = sub.add_parser("retrieve", help="recover an original by reference id")
    p_ret.add_argument("ref")
    p_ret.set_defaults(func=_cmd_retrieve)

    p_stats = sub.add_parser("stats", help="show in-process telemetry")
    p_stats.set_defaults(func=_cmd_stats)

    p_proxy = sub.add_parser("proxy", help="run the compressing chat-completions proxy")
    p_proxy.add_argument("--host", default=None)
    p_proxy.add_argument("--port", type=int, default=None)
    p_proxy.add_argument("--upstream", default=None, help="upstream base URL")
    p_proxy.set_defaults(func=_cmd_proxy)

    p_mcp = sub.add_parser("mcp", help="run the MCP server over stdio")
    p_mcp.set_defaults(func=_cmd_mcp)

    p_setup = sub.add_parser("setup", help="print/write the MCP client config entry")
    p_setup.add_argument(
        "--write", action="store_true", help="merge the entry into --config-path"
    )
    p_setup.add_argument(
        "--config-path", default=None, dest="config_path",
        help="your MCP client's JSON config file (required with --write)",
    )
    p_setup.set_defaults(func=_cmd_setup)

    p_doctor = sub.add_parser("doctor", help="check install, extras, and config")
    p_doctor.set_defaults(func=_cmd_doctor)

    p_qs = sub.add_parser("quickstart", help="print copy-paste onboarding steps")
    p_qs.set_defaults(func=_cmd_quickstart)

    p_ver = sub.add_parser("version", help="print version")
    p_ver.set_defaults(func=_cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
