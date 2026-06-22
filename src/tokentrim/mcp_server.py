"""MCP server exposing TokenTrim to any MCP-capable client.

Tools:
    tokentrim_compress(content, level=None)   compress a block, return text + savings
    tokentrim_retrieve(ref)                    recover an original by reference id
    tokentrim_stats()                          current session savings

Run with:  tokentrim mcp
Requires the ``mcp`` extra:  pip install 'tokentrim[mcp]'
"""

from __future__ import annotations

from .config import get_config
from .core import compress_block, retrieve
from .stats import get_stats


def build_server():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("tokentrim")

    @server.tool()
    def tokentrim_compress(content: str, level: str | None = None) -> str:
        """Compress a block of content (tool output, log, file, RAG chunk).

        Returns the compressed text. A [tokentrim:ref …] marker is appended when
        the original is recoverable via tokentrim_retrieve.
        """
        cfg = get_config().merged(level=level, min_tokens=0)
        result = compress_block(content, cfg)
        header = (
            f"[tokentrim] {result.kind}: {result.original_tokens} → "
            f"{result.compressed_tokens} tokens ({round(result.ratio * 100, 1)}% saved)\n"
        )
        return header + result.text

    @server.tool()
    def tokentrim_retrieve(ref: str) -> str:
        """Recover the original, uncompressed content for a reference id."""
        original = retrieve(ref)
        if original is None:
            return f"No stored content for ref '{ref}' (expired or unknown)."
        return original

    @server.tool()
    def tokentrim_stats() -> dict:
        """Return cumulative compression savings for this session."""
        return get_stats().to_dict()

    return server


def run_mcp() -> None:
    server = build_server()
    server.run()


if __name__ == "__main__":
    run_mcp()
