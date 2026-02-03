"""Codenav MCP Server - Model Context Protocol integration.

This module exposes Codenav's functionality as MCP tools and resources,
enabling seamless integration with Claude Code, Claude Desktop, and
other MCP-compatible AI assistants.

Usage:
    # Start the server
    python -m codenav.mcp

    # Or use the CLI
    codenav mcp-server
"""

from .server import create_server, main, run_server

__all__ = [
    "create_server",
    "run_server",
    "main",
]
