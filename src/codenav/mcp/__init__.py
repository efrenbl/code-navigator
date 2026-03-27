"""Codenav MCP Server - Model Context Protocol integration.

This module exposes Codenav's functionality as MCP tools and resources,
enabling seamless integration with Claude Code (CLI and VS Code),
Claude Desktop, and other MCP-compatible AI assistants.

Requires the ``mcp`` extra: ``pip install codenav[mcp]``

Usage:
    # Entry point (recommended)
    codenav-mcp

    # Or as a Python module
    python -m codenav.mcp
"""

try:
    from .server import create_server, main, mcp, run_server

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    mcp = None  # type: ignore
    create_server = None  # type: ignore
    run_server = None  # type: ignore

    def main():  # type: ignore
        raise SystemExit(
            "MCP dependencies not installed. Install with: pip install codenav[mcp]"
        )


__all__ = [
    "MCP_AVAILABLE",
    "mcp",
    "create_server",
    "run_server",
    "main",
]
