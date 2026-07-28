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

from importlib.metadata import PackageNotFoundError, version

#: The mcp range codenav is built against, kept in sync with the [mcp] extra in
#: pyproject.toml. Quoted back to the user in the failure message.
MCP_REQUIREMENT = "mcp>=1.28.1,<2"


def _import_failure_message(error: BaseException) -> str:
    """Explain why ``codenav.mcp.server`` could not be imported.

    A missing mcp and an incompatible mcp both surface as ImportError, so the
    exception alone cannot tell them apart. Resolving the installed version does:
    telling someone to install a package that is already there sends them looking
    for the wrong problem.
    """
    try:
        installed = version("mcp")
    except PackageNotFoundError:
        return f"MCP dependencies not installed. Install with: pip install 'codenav[mcp]' ({MCP_REQUIREMENT})"

    return (
        f"mcp {installed} is installed but codenav requires {MCP_REQUIREMENT} — "
        "mcp 2.0 removed mcp.server.fastmcp. "
        f"Fix with: pip install '{MCP_REQUIREMENT}'. Import error: {error}"
    )


try:
    from .server import create_server, main, mcp, run_server

    MCP_AVAILABLE = True
except ImportError as import_error:
    MCP_AVAILABLE = False
    mcp = None  # type: ignore
    create_server = None  # type: ignore
    run_server = None  # type: ignore
    _IMPORT_ERROR = import_error

    def main():  # type: ignore
        raise SystemExit(_import_failure_message(_IMPORT_ERROR))


__all__ = [
    "MCP_AVAILABLE",
    "MCP_REQUIREMENT",
    "mcp",
    "create_server",
    "run_server",
    "main",
]
