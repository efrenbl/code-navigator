#!/usr/bin/env python3
"""Codenav MCP Server - Token-efficient code navigation for AI assistants.

This server implements the Model Context Protocol (MCP) using FastMCP to expose
Codenav's code navigation capabilities to Claude Desktop, Claude Code, and
other MCP-compatible AI assistants.

Usage:
    python -m codenav.mcp
    codenav-mcp
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..code_navigator import CodeNavigator
from ..code_search import CodeSearcher
from ..line_reader import LineReader

# Optional imports
try:
    from ..token_efficient_renderer import TokenEfficientRenderer

    HAS_RENDERER = True
except ImportError:
    HAS_RENDERER = False

logger = logging.getLogger(__name__)

# ==============================================================================
# SYSTEM PROMPT - Instructions for AI agents
# ==============================================================================

SYSTEM_PROMPT = """# Code Navigator - Token-Efficient Code Navigation

You have access to Code Navigator, an MCP server that helps you explore codebases efficiently while minimizing token usage.

## Recommended Workflow

1. **Scan first** (`codenav_scan`): Generate a code map for the project. This creates `.codenav.json` which indexes all symbols.
2. **Search by symbol** (`codenav_search`): Find functions, classes, methods by name or pattern. Returns file:line locations.
3. **Read surgically** (`codenav_read`): Load only the specific lines you need, not entire files.

## Token-Efficiency Best Practices

- **Never read entire files** - Use `codenav_search` to find exact line ranges, then `codenav_read` with those ranges.
- **Use `codenav_get_structure`** before reading a file to see what symbols it contains.
- **Check `codenav_stats`** to understand codebase size before diving in.
- **Use `codenav_get_hubs`** to identify the most important files to review first.

## Auto-Detection

If you call search/stats/hubs/structure/dependencies without first scanning, and no `.codenav.json` exists, you'll get an error asking you to run `codenav_scan` first.

## Available Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `codenav_scan` | Index codebase | First step for any new project |
| `codenav_search` | Find symbols | Looking for specific function/class |
| `codenav_read` | Read lines | After finding symbol location |
| `codenav_stats` | Codebase overview | Understanding project size |
| `codenav_get_hubs` | Find central files | Architecture analysis |
| `codenav_get_structure` | File outline | Before reading a file |
| `codenav_get_dependencies` | Import graph | Understanding coupling |

## Example Session

```
User: "Fix the payment bug"

1. codenav_scan(path="/project")           # Index the codebase
2. codenav_search(query="payment")         # Find: payments.py:45-89
3. codenav_read(file_path="payments.py", start_line=45, end_line=89)  # Read only those lines
4. Make targeted fix with exact line numbers
```

This approach uses ~500 tokens instead of ~15,000 tokens from reading entire files.
"""

# ==============================================================================
# SERVER INITIALIZATION
# ==============================================================================

# Create FastMCP server with instructions
mcp = FastMCP(
    "codenav",
    instructions=SYSTEM_PROMPT,
)

# Global handler instance (initialized per-session)
_handler: Optional["CodenavToolHandler"] = None


def get_handler() -> "CodenavToolHandler":
    """Get or create the tool handler."""
    global _handler
    if _handler is None:
        _handler = CodenavToolHandler()
    return _handler


# ==============================================================================
# TOOL HANDLER CLASS
# ==============================================================================


class CodenavToolHandler:
    """Handles execution of Codenav MCP tools."""

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = workspace_root or os.getcwd()
        self._code_map_cache: dict[str, dict] = {}
        self._navigator_cache: dict[str, CodeNavigator] = {}

    def _get_map_path(self, path: str) -> Path:
        """Get the .codenav.json path for a directory."""
        return Path(path) / ".codenav.json"

    def _check_map_exists(self, path: str) -> tuple[bool, str]:
        """Check if .codenav.json exists and return helpful error if not."""
        map_path = self._get_map_path(path)
        if not map_path.exists():
            return False, (
                f"No .codenav.json found in {path}. "
                "Run `codenav_scan` first to index the codebase."
            )
        return True, ""

    def _get_navigator(self, path: str) -> CodeNavigator:
        """Get or create a CodeNavigator for the given path."""
        abs_path = os.path.abspath(path)
        if abs_path not in self._navigator_cache:
            self._navigator_cache[abs_path] = CodeNavigator(abs_path)
        return self._navigator_cache[abs_path]

    def _get_code_map(self, path: str, force_rescan: bool = False) -> dict:
        """Get or load a code map for the given path."""
        abs_path = os.path.abspath(path)

        # Check cache
        if not force_rescan and abs_path in self._code_map_cache:
            return self._code_map_cache[abs_path]

        # Load from file
        map_path = self._get_map_path(abs_path)
        if map_path.exists():
            with open(map_path, encoding="utf-8") as f:
                code_map = json.load(f)
                self._code_map_cache[abs_path] = code_map
                return code_map

        return {}

    def _format_search_results_compact(self, results: list, limit: int) -> str:
        """Format search results in compact single-line format."""
        if not results:
            return "No matching symbols found."

        lines = [f"Found {len(results)} matches:"]

        for r in results[:limit]:
            # Compact format: file:L{start}-{end} [type] name
            end_line = r.lines[1] if len(r.lines) > 1 else r.lines[0]
            type_abbr = {"function": "fn", "class": "cls", "method": "mth"}.get(r.type, r.type[:3])
            lines.append(f"{r.file}:L{r.lines[0]}-{end_line} [{type_abbr}] {r.name}")

        if len(results) > limit:
            lines.append(f"... +{len(results) - limit} more")

        return "\n".join(lines)

    def _format_hubs_compact(self, hubs: list) -> str:
        """Format hub files in compact list format."""
        if not hubs:
            return "No hub files found."

        lines = ["Architectural hubs (most imported):"]
        for i, hub in enumerate(hubs, 1):
            symbols_preview = ", ".join(hub.get("symbols", [])[:3])
            if len(hub.get("symbols", [])) > 3:
                symbols_preview += "..."
            lines.append(f"{i}. {hub['file']} ({hub['imports']}← imports) [{symbols_preview}]")

        return "\n".join(lines)

    def _format_stats_compact(self, stats: dict) -> str:
        """Format stats as compact key-value pairs."""
        lines = [
            f"root: {stats.get('root', 'unknown')}",
            f"files: {stats.get('files', 0)}",
            f"symbols: {stats.get('total_symbols', 0)}",
        ]

        by_type = stats.get("by_type", {})
        if by_type:
            type_parts = [f"{k}:{v}" for k, v in sorted(by_type.items())]
            lines.append(f"by_type: {', '.join(type_parts)}")

        if stats.get("generated_at"):
            lines.append(f"generated: {stats['generated_at']}")

        return "\n".join(lines)


# ==============================================================================
# MCP TOOLS
# ==============================================================================


@mcp.tool()
def codenav_scan(
    path: str,
    ignore_patterns: list[str] | None = None,
    git_only: bool = False,
    max_depth: int = 0,
) -> str:
    """Scan a codebase and generate a structural map with all symbols.

    Use this tool first when starting work on any codebase. It creates a
    .codenav.json index file containing all functions, classes, and methods
    with their exact line numbers.

    Args:
        path: Root directory to scan (absolute or relative path)
        ignore_patterns: Glob patterns to ignore (e.g., ['*.test.py', 'vendor/'])
        git_only: Only scan files tracked by git
        max_depth: Maximum directory depth to display (0=unlimited)

    Returns:
        Token-efficient summary showing file tree with symbol metadata
    """
    handler = get_handler()

    try:
        abs_path = os.path.abspath(path)
        navigator = CodeNavigator(
            abs_path,
            ignore_patterns=ignore_patterns or [],
            git_only=git_only,
        )
        code_map = navigator.scan()
        handler._code_map_cache[abs_path] = code_map

        # Use token-efficient rendering if available
        if HAS_RENDERER:
            renderer = TokenEfficientRenderer(code_map, root_path=abs_path)
            return renderer.render_skeleton_tree(
                max_depth=max_depth,
                show_meta=True,
                show_summary=True,
            )
        else:
            # Compact summary fallback
            files = code_map.get("files", {})
            total_symbols = sum(len(f.get("symbols", [])) for f in files.values())
            return f"Scanned {len(files)} files, found {total_symbols} symbols. Map saved to .codenav.json"

    except Exception as e:
        logger.exception(f"Error scanning {path}")
        return f"Error: {e}"


@mcp.tool()
def codenav_search(
    query: str,
    symbol_type: str = "any",
    file_pattern: str | None = None,
    limit: int = 20,
    path: str | None = None,
) -> str:
    """Search for symbols (functions, classes, methods) by name or pattern.

    Use this after scanning to find where specific code is defined.
    Returns compact file:line locations for efficient reading.

    Args:
        query: Search query (name, pattern, or regex)
        symbol_type: Filter by type: 'function', 'class', 'method', 'variable', or 'any'
        file_pattern: Filter by file glob pattern (e.g., '*.py', 'src/**/*.ts')
        limit: Maximum results to return
        path: Root directory (uses current dir if not specified)

    Returns:
        Compact list: file:L{start}-{end} [type] name
    """
    handler = get_handler()
    search_path = os.path.abspath(path or handler.workspace_root)

    # Check if map exists
    exists, error_msg = handler._check_map_exists(search_path)
    if not exists:
        return error_msg

    try:
        map_path = handler._get_map_path(search_path)
        searcher = CodeSearcher(str(map_path))

        # Search based on type
        if symbol_type == "any":
            results = searcher.search_symbol(query, limit=limit)
        else:
            results = searcher.search_symbol(query, symbol_type=symbol_type, limit=limit)

        # Filter by file pattern if specified
        if file_pattern:
            import fnmatch

            results = [r for r in results if fnmatch.fnmatch(r.file, file_pattern)]

        return handler._format_search_results_compact(results, limit)

    except Exception as e:
        logger.exception(f"Error searching for {query}")
        return f"Error: {e}"


@mcp.tool()
def codenav_read(
    file_path: str,
    start_line: int,
    end_line: int,
    context: int = 0,
) -> str:
    """Read specific lines from a file with optional context.

    Use this after finding a symbol's location to read its implementation.
    Much more token-efficient than reading entire files.

    Args:
        file_path: Path to the file to read
        start_line: First line to read (1-indexed)
        end_line: Last line to read (inclusive)
        context: Additional lines before/after the range

    Returns:
        The requested lines with line numbers
    """
    handler = get_handler()

    try:
        reader = LineReader(root_path=handler.workspace_root)
        content = reader.read_lines(file_path, start_line, end_line, context=context)
        return content

    except Exception as e:
        logger.exception(f"Error reading {file_path}")
        return f"Error: {e}"


@mcp.tool()
def codenav_stats(path: str | None = None) -> str:
    """Get statistics about the indexed codebase.

    Shows file count, symbol count, and breakdown by type.
    Useful for understanding project size before diving in.

    Args:
        path: Root directory (uses current dir if not specified)

    Returns:
        Compact stats: files, symbols, breakdown by type
    """
    handler = get_handler()
    stats_path = os.path.abspath(path or handler.workspace_root)

    # Check if map exists
    exists, error_msg = handler._check_map_exists(stats_path)
    if not exists:
        return error_msg

    try:
        map_path = handler._get_map_path(stats_path)
        searcher = CodeSearcher(str(map_path))
        stats = searcher.get_stats()
        return handler._format_stats_compact(stats)

    except Exception as e:
        logger.exception(f"Error getting stats for {stats_path}")
        return f"Error: {e}"


@mcp.tool()
def codenav_get_hubs(
    path: str,
    top_n: int = 10,
    min_imports: int = 3,
) -> str:
    """Identify architectural hub files - the most central files in the codebase.

    Hub files are heavily imported by other files, making them critical
    for understanding the architecture. Review these first.

    Args:
        path: Root directory to analyze
        top_n: Number of top hubs to return
        min_imports: Minimum import count to be considered a hub

    Returns:
        Ranked list of hub files with import counts
    """
    handler = get_handler()
    abs_path = os.path.abspath(path)

    # Check if map exists
    exists, error_msg = handler._check_map_exists(abs_path)
    if not exists:
        return error_msg

    try:
        code_map = handler._get_code_map(abs_path)

        # Calculate hub scores
        import_counts: dict[str, int] = {}
        file_symbols: dict[str, list[str]] = {}

        for fpath, file_info in code_map.get("files", {}).items():
            file_symbols[fpath] = [s["name"] for s in file_info.get("symbols", [])]
            for imp in file_info.get("imports", []):
                import_counts[imp] = import_counts.get(imp, 0) + 1

        hubs = []
        for file_path, count in import_counts.items():
            if count >= min_imports:
                hubs.append(
                    {
                        "file": file_path,
                        "imports": count,
                        "symbols": file_symbols.get(file_path, []),
                    }
                )

        hubs = sorted(hubs, key=lambda x: x["imports"], reverse=True)[:top_n]
        return handler._format_hubs_compact(hubs)

    except Exception as e:
        logger.exception(f"Error getting hubs for {path}")
        return f"Error: {e}"


@mcp.tool()
def codenav_get_dependencies(
    path: str,
    file: str | None = None,
    direction: str = "both",
    depth: int = 1,
) -> str:
    """Get the dependency graph for a file or the entire project.

    Shows what a file imports and what imports it.
    Useful for understanding coupling between modules.

    Args:
        path: Root directory or specific file to analyze
        file: Specific file to get dependencies for (optional)
        direction: 'imports', 'imported_by', or 'both'
        depth: How many levels deep to traverse

    Returns:
        Import/export relationships in compact format
    """
    handler = get_handler()
    abs_path = os.path.abspath(path)

    # Check if map exists
    exists, error_msg = handler._check_map_exists(abs_path)
    if not exists:
        return error_msg

    try:
        code_map = handler._get_code_map(abs_path)

        if file:
            # Find the file
            file_info = None
            for fpath, info in code_map.get("files", {}).items():
                if fpath == file or file in fpath:
                    file_info = info
                    file_info["path"] = fpath
                    break

            if not file_info:
                return f"File not found: {file}"

            lines = [f"Dependencies for {file_info['path']}:"]

            if direction in ("imports", "both"):
                imports = file_info.get("imports", [])
                lines.append(f"imports ({len(imports)}): {', '.join(imports[:10])}")
                if len(imports) > 10:
                    lines[-1] += f" +{len(imports)-10} more"

            if direction in ("imported_by", "both"):
                imported_by = []
                for fpath, info in code_map.get("files", {}).items():
                    if file_info["path"] in info.get("imports", []):
                        imported_by.append(fpath)
                lines.append(f"imported_by ({len(imported_by)}): {', '.join(imported_by[:10])}")
                if len(imported_by) > 10:
                    lines[-1] += f" +{len(imported_by)-10} more"

            return "\n".join(lines)
        else:
            # Project-wide summary
            files = code_map.get("files", {})
            connections = [(fpath, len(info.get("imports", []))) for fpath, info in files.items()]
            connections.sort(key=lambda x: x[1], reverse=True)

            lines = [f"Project dependencies ({len(files)} files):", "Most connected:"]
            for fpath, count in connections[:10]:
                lines.append(f"  {fpath}: {count} imports")

            return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting dependencies for {path}")
        return f"Error: {e}"


@mcp.tool()
def codenav_get_structure(
    file_path: str,
    include_private: bool = False,
) -> str:
    """Get the structure of a specific file showing all its symbols.

    Use this to see what's in a file before reading it.
    Helps decide which parts to read in detail.

    Args:
        file_path: Path to the file to analyze
        include_private: Include private symbols (starting with _)

    Returns:
        Hierarchical list of symbols with types and line numbers
    """
    handler = get_handler()

    # Determine the project root from file path
    file_dir = os.path.dirname(os.path.abspath(file_path)) or handler.workspace_root

    # Check if map exists (try parent directories)
    search_path = file_dir
    map_found = False
    while search_path and search_path != "/":
        if handler._get_map_path(search_path).exists():
            map_found = True
            break
        search_path = os.path.dirname(search_path)

    if not map_found:
        return "No .codenav.json found. Run `codenav_scan` first to index the codebase."

    try:
        code_map = handler._get_code_map(search_path)
        abs_file_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_file_path, search_path)

        # Find the file in the code map
        file_info = None
        for fpath, info in code_map.get("files", {}).items():
            if fpath == rel_path or fpath == abs_file_path or rel_path in fpath:
                file_info = info
                break

        if not file_info:
            return f"File not found in code map: {file_path}"

        symbols = file_info.get("symbols", [])
        if not include_private:
            symbols = [s for s in symbols if not s["name"].startswith("_")]

        # Group and format
        classes = [s for s in symbols if s.get("type") == "class"]
        functions = [s for s in symbols if s.get("type") == "function"]
        methods = [s for s in symbols if s.get("type") == "method"]

        lines = [f"Structure of {rel_path}:"]

        if classes:
            lines.append(f"classes ({len(classes)}):")
            for c in classes:
                end = c.get("end_line", c["lines"][1] if len(c.get("lines", [])) > 1 else "?")
                lines.append(f"  {c['name']} L{c['lines'][0]}-{end}")

        if functions:
            lines.append(f"functions ({len(functions)}):")
            for f in functions:
                end = f.get("end_line", f["lines"][1] if len(f.get("lines", [])) > 1 else "?")
                lines.append(f"  {f['name']} L{f['lines'][0]}-{end}")

        if methods:
            lines.append(f"methods ({len(methods)}):")
            for m in methods[:15]:
                lines.append(f"  {m['name']} L{m['lines'][0]}")
            if len(methods) > 15:
                lines.append(f"  ... +{len(methods)-15} more")

        return "\n".join(lines)

    except Exception as e:
        logger.exception(f"Error getting structure for {file_path}")
        return f"Error: {e}"


# ==============================================================================
# MCP RESOURCES
# ==============================================================================


@mcp.resource("codenav://code-map")
def get_code_map_resource() -> str:
    """The current codebase structural map as JSON."""
    handler = get_handler()
    code_map = handler._get_code_map(handler.workspace_root)
    return json.dumps(code_map, indent=2)


@mcp.resource("codenav://dependencies")
def get_dependencies_resource() -> str:
    """File dependency relationships as JSON."""
    handler = get_handler()
    code_map = handler._get_code_map(handler.workspace_root)
    deps = {fpath: info.get("imports", []) for fpath, info in code_map.get("files", {}).items()}
    return json.dumps(deps, indent=2)


# ==============================================================================
# MCP PROMPTS
# ==============================================================================


@mcp.prompt()
def analyze_architecture(path: str) -> str:
    """Analyze the architecture of a codebase.

    Args:
        path: Path to the codebase
    """
    return f"""Analyze the architecture of the codebase at {path}.

1. First, scan the codebase using codenav_scan
2. Identify the architectural hubs using codenav_get_hubs
3. Analyze the dependency structure using codenav_get_dependencies
4. Provide a summary of:
   - Overall structure and organization
   - Key modules and their responsibilities
   - Coupling between components
   - Potential areas for improvement"""


@mcp.prompt()
def find_entry_points(path: str) -> str:
    """Find the main entry points of an application.

    Args:
        path: Path to the codebase
    """
    return f"""Find and explain the entry points for the application at {path}.

1. Scan the codebase using codenav_scan
2. Search for common entry point patterns (main, cli, app)
3. Read the relevant files to understand how the application starts
4. Provide a summary of how to run and use the application"""


# ==============================================================================
# ENTRY POINTS
# ==============================================================================


def create_server(workspace_root: str | None = None) -> FastMCP:
    """Create and return the MCP server instance."""
    global _handler
    _handler = CodenavToolHandler(workspace_root)
    return mcp


async def run_server(workspace_root: str | None = None):
    """Run the MCP server using stdio transport."""
    global _handler
    _handler = CodenavToolHandler(workspace_root)
    await mcp.run_stdio_async()


def main():
    """Entry point for the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Codenav MCP Server")
    parser.add_argument(
        "--workspace",
        "-w",
        default=os.getcwd(),
        help="Workspace root directory",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    global _handler
    _handler = CodenavToolHandler(args.workspace)

    mcp.run()


if __name__ == "__main__":
    main()
