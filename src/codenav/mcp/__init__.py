"""Codenav MCP Server - Model Context Protocol integration.

This module exposes Codenav's functionality as MCP tools and resources,
enabling seamless integration with Claude Code (CLI and VS Code),
Claude Desktop, and other MCP-compatible AI assistants.

Usage:
    # Entry point (recommended)
    codenav-mcp

    # Or as a Python module
    python -m codenav.mcp
"""

from .server import create_server, main, mcp, run_server

__all__ = [
    "mcp",
    "create_server",
    "run_server",
    "main",
]
