#!/usr/bin/env python3
"""Codenav MCP Server - Exposes code navigation as MCP tools.

This server implements the Model Context Protocol (MCP) to expose
Codenav's code navigation capabilities to AI assistants.

Features:
    - Tools for scanning, searching, and navigating codebases
    - Resources for exposing dependency graphs and code maps
    - Token-optimized responses for efficient LLM consumption

Usage:
    python -m codenav.mcp.server
    codenav mcp-server --port 8080
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# MCP SDK imports
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolResult,
        GetPromptResult,
        ListPromptsResult,
        ListResourcesResult,
        ListToolsResult,
        Prompt,
        PromptArgument,
        PromptMessage,
        ReadResourceResult,
        Resource,
        ResourceContents,
        TextContent,
        TextResourceContents,
        Tool,
    )
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    Server = None

# Codenav imports
from .. import __version__
from ..code_navigator import CodeNavigator
from ..code_search import CodeSearcher
from ..line_reader import LineReader

# Optional imports
try:
    from ..dependency_graph import DependencyGraph
    HAS_GRAPH = True
except ImportError:
    HAS_GRAPH = False

try:
    from ..token_efficient_renderer import TokenEfficientRenderer
    HAS_RENDERER = True
except ImportError:
    HAS_RENDERER = False

logger = logging.getLogger(__name__)

# ==============================================================================
# TOOL DEFINITIONS
# ==============================================================================

TOOLS: List[Dict[str, Any]] = [
    {
        "name": "codenav_scan",
        "description": """Scan a codebase and generate a structural map with all symbols (classes, functions, methods).

USE THIS TOOL WHEN:
- You need to understand the overall structure of a project
- You're starting work on an unfamiliar codebase
- You need to find all files and their symbols

RETURNS: A token-efficient summary showing file tree with inline metadata about classes, functions, and architectural hubs.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Root directory to scan (absolute or relative path)"
                },
                "ignore_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to ignore (e.g., ['*.test.py', 'vendor/'])"
                },
                "git_only": {
                    "type": "boolean",
                    "description": "Only scan files tracked by git",
                    "default": False
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum directory depth to display (0=unlimited)",
                    "default": 0
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "codenav_search",
        "description": """Search for symbols (functions, classes, methods) in a codebase by name or pattern.

USE THIS TOOL WHEN:
- You need to find where a specific function/class is defined
- You're looking for symbols matching a pattern (e.g., all handlers)
- You need to understand what symbols exist in a file

RETURNS: Compact list of matching symbols with file:line locations and brief context.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (name, pattern, or regex)"
                },
                "symbol_type": {
                    "type": "string",
                    "enum": ["function", "class", "method", "variable", "any"],
                    "description": "Filter by symbol type",
                    "default": "any"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Filter by file glob pattern (e.g., '*.py', 'src/**/*.ts')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 20
                },
                "path": {
                    "type": "string",
                    "description": "Root directory (uses current dir if not specified)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "codenav_read",
        "description": """Read specific lines from a file with optional context.

USE THIS TOOL WHEN:
- You found a symbol and need to see its implementation
- You need to read a specific section of code
- You want to see code around a specific line

RETURNS: The requested lines with line numbers, optimized for code review.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to read"
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read (1-indexed)"
                },
                "end_line": {
                    "type": "integer",
                    "description": "Last line to read (inclusive)"
                },
                "context": {
                    "type": "integer",
                    "description": "Additional lines before/after the range",
                    "default": 0
                }
            },
            "required": ["file_path", "start_line", "end_line"]
        }
    },
    {
        "name": "codenav_get_hubs",
        "description": """Identify architectural hub files - the most important/central files in the codebase.

USE THIS TOOL WHEN:
- You need to understand the core architecture
- You want to find the most critical files to review first
- You're looking for entry points or central modules

RETURNS: Ranked list of hub files with import counts and brief description of their role.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Root directory to analyze"
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of top hubs to return",
                    "default": 10
                },
                "min_imports": {
                    "type": "integer",
                    "description": "Minimum import count to be considered a hub",
                    "default": 3
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "codenav_get_dependencies",
        "description": """Get the dependency graph for a file or the entire project.

USE THIS TOOL WHEN:
- You need to understand what a file imports/depends on
- You want to see what files depend ON a specific file
- You're analyzing the coupling between modules

RETURNS: Import/export relationships in a compact format showing dependencies.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Root directory or specific file to analyze"
                },
                "file": {
                    "type": "string",
                    "description": "Specific file to get dependencies for (optional)"
                },
                "direction": {
                    "type": "string",
                    "enum": ["imports", "imported_by", "both"],
                    "description": "Direction of dependencies to show",
                    "default": "both"
                },
                "depth": {
                    "type": "integer",
                    "description": "How many levels deep to traverse",
                    "default": 1
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "codenav_get_structure",
        "description": """Get the structure of a specific file showing all its symbols.

USE THIS TOOL WHEN:
- You need a quick overview of what's in a file
- You want to see all classes/functions without reading the whole file
- You're deciding which parts of a file to read in detail

RETURNS: Hierarchical list of symbols with types, line numbers, and signatures.""",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to analyze"
                },
                "include_private": {
                    "type": "boolean",
                    "description": "Include private symbols (starting with _)",
                    "default": False
                }
            },
            "required": ["file_path"]
        }
    },
]


# ==============================================================================
# TOOL IMPLEMENTATIONS
# ==============================================================================

class CodenavToolHandler:
    """Handles execution of Codenav MCP tools."""

    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = workspace_root or os.getcwd()
        self._code_map_cache: Dict[str, Dict] = {}
        self._navigator_cache: Dict[str, CodeNavigator] = {}

    def _get_navigator(self, path: str) -> CodeNavigator:
        """Get or create a CodeNavigator for the given path."""
        abs_path = os.path.abspath(path)
        if abs_path not in self._navigator_cache:
            self._navigator_cache[abs_path] = CodeNavigator(abs_path)
        return self._navigator_cache[abs_path]

    def _get_code_map(self, path: str, force_rescan: bool = False) -> Dict:
        """Get or generate a code map for the given path."""
        abs_path = os.path.abspath(path)

        # Check cache
        if not force_rescan and abs_path in self._code_map_cache:
            return self._code_map_cache[abs_path]

        # Check for existing map file
        map_file = Path(abs_path) / ".codenav.json"
        if map_file.exists() and not force_rescan:
            with open(map_file) as f:
                code_map = json.load(f)
                self._code_map_cache[abs_path] = code_map
                return code_map

        # Generate new map
        navigator = self._get_navigator(path)
        code_map = navigator.scan()
        self._code_map_cache[abs_path] = code_map
        return code_map

    async def handle_scan(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_scan tool call."""
        path = arguments.get("path", self.workspace_root)
        ignore_patterns = arguments.get("ignore_patterns", [])
        git_only = arguments.get("git_only", False)
        max_depth = arguments.get("max_depth", 0)

        navigator = CodeNavigator(
            path,
            ignore_patterns=ignore_patterns,
            git_only=git_only,
        )
        code_map = navigator.scan()
        self._code_map_cache[os.path.abspath(path)] = code_map

        # Use token-efficient rendering if available
        if HAS_RENDERER:
            renderer = TokenEfficientRenderer(code_map, root_path=path)
            return renderer.render_skeleton_tree(
                max_depth=max_depth,
                show_meta=True,
                show_summary=True,
            )
        else:
            # Fallback to compact JSON summary
            return self._format_compact_summary(code_map, path)

    async def handle_search(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_search tool call."""
        query = arguments["query"]
        symbol_type = arguments.get("symbol_type", "any")
        file_pattern = arguments.get("file_pattern")
        limit = arguments.get("limit", 20)
        path = arguments.get("path", self.workspace_root)

        # Ensure we have a code map
        code_map = self._get_code_map(path)

        # Create a temporary map file for CodeSearcher
        map_path = Path(path) / ".codenav.json"
        if not map_path.exists():
            with open(map_path, "w") as f:
                json.dump(code_map, f)

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

        # Format results compactly
        return self._format_search_results(results, limit)

    async def handle_read(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_read tool call."""
        file_path = arguments["file_path"]
        start_line = arguments["start_line"]
        end_line = arguments["end_line"]
        context = arguments.get("context", 0)

        reader = LineReader()
        content = reader.read_lines(file_path, start_line, end_line, context=context)

        return content

    async def handle_get_hubs(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_get_hubs tool call."""
        path = arguments.get("path", self.workspace_root)
        top_n = arguments.get("top_n", 10)
        min_imports = arguments.get("min_imports", 3)

        code_map = self._get_code_map(path)

        # Calculate hub scores from the code map
        hubs = self._calculate_hubs(code_map, min_imports)

        # Sort and limit
        hubs = sorted(hubs, key=lambda x: x["score"], reverse=True)[:top_n]

        # Format output
        lines = ["# Architectural Hubs (most imported files)", ""]
        for i, hub in enumerate(hubs, 1):
            lines.append(f"{i}. **{hub['file']}** ({hub['imports']}← imports)")
            if hub.get("symbols"):
                lines.append(f"   Contains: {', '.join(hub['symbols'][:5])}")

        if not hubs:
            lines.append("No hub files found with the specified criteria.")

        return "\n".join(lines)

    async def handle_get_dependencies(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_get_dependencies tool call."""
        path = arguments.get("path", self.workspace_root)
        file = arguments.get("file")
        direction = arguments.get("direction", "both")
        depth = arguments.get("depth", 1)

        code_map = self._get_code_map(path)

        if file:
            return self._format_file_dependencies(code_map, file, direction, depth)
        else:
            return self._format_project_dependencies(code_map, direction)

    async def handle_get_structure(self, arguments: Dict[str, Any]) -> str:
        """Handle codenav_get_structure tool call."""
        file_path = arguments["file_path"]
        include_private = arguments.get("include_private", False)

        # Get the code map for the file's directory
        path = os.path.dirname(file_path) or self.workspace_root
        code_map = self._get_code_map(path)

        # Find the file in the code map
        rel_path = os.path.relpath(file_path, path)
        file_info = None
        for f in code_map.get("files", []):
            if f.get("path") == rel_path or f.get("path") == file_path:
                file_info = f
                break

        if not file_info:
            return f"File not found in code map: {file_path}"

        return self._format_file_structure(file_info, include_private)

    # --------------------------------------------------------------------------
    # Helper methods for formatting
    # --------------------------------------------------------------------------

    def _format_compact_summary(self, code_map: Dict, path: str) -> str:
        """Format code map as compact summary."""
        files = code_map.get("files", [])
        total_symbols = sum(len(f.get("symbols", [])) for f in files)

        lines = [
            f"# Code Map: {os.path.basename(path)}",
            f"Files: {len(files)} | Symbols: {total_symbols}",
            "",
            "## Top Files by Symbol Count:",
        ]

        # Sort files by symbol count
        sorted_files = sorted(files, key=lambda f: len(f.get("symbols", [])), reverse=True)
        for f in sorted_files[:15]:
            symbols = f.get("symbols", [])
            symbol_summary = self._summarize_symbols(symbols)
            lines.append(f"- {f['path']} [{symbol_summary}]")

        return "\n".join(lines)

    def _summarize_symbols(self, symbols: List[Dict]) -> str:
        """Create a compact symbol summary."""
        classes = [s for s in symbols if s.get("type") == "class"]
        functions = [s for s in symbols if s.get("type") == "function"]
        methods = [s for s in symbols if s.get("type") == "method"]

        parts = []
        if classes:
            names = ", ".join(c["name"] for c in classes[:3])
            if len(classes) > 3:
                names += f"...+{len(classes)-3}"
            parts.append(f"C:{names}")
        if functions:
            names = ", ".join(f["name"] for f in functions[:3])
            if len(functions) > 3:
                names += f"...+{len(functions)-3}"
            parts.append(f"F:{names}")
        if methods:
            parts.append(f"M:{len(methods)}")

        return " ".join(parts) if parts else "empty"

    def _format_search_results(self, results: List, limit: int) -> str:
        """Format search results compactly."""
        if not results:
            return "No matching symbols found."

        lines = [f"# Search Results ({len(results)} matches)", ""]

        for r in results[:limit]:
            # Format: file:line - type name
            location = f"{r.file}:{r.start_line}"
            type_indicator = {"function": "fn", "class": "cls", "method": "mth"}.get(r.type, r.type)
            lines.append(f"- `{location}` [{type_indicator}] **{r.name}**")

        if len(results) > limit:
            lines.append(f"\n... and {len(results) - limit} more results")

        return "\n".join(lines)

    def _calculate_hubs(self, code_map: Dict, min_imports: int) -> List[Dict]:
        """Calculate hub files based on import relationships."""
        import_counts: Dict[str, int] = {}
        file_symbols: Dict[str, List[str]] = {}

        for f in code_map.get("files", []):
            path = f.get("path", "")
            file_symbols[path] = [s["name"] for s in f.get("symbols", [])]

            for imp in f.get("imports", []):
                # Increment import count for the imported module
                import_counts[imp] = import_counts.get(imp, 0) + 1

        hubs = []
        for file_path, count in import_counts.items():
            if count >= min_imports:
                hubs.append({
                    "file": file_path,
                    "imports": count,
                    "score": count,
                    "symbols": file_symbols.get(file_path, []),
                })

        return hubs

    def _format_file_dependencies(
        self, code_map: Dict, file: str, direction: str, depth: int
    ) -> str:
        """Format dependencies for a specific file."""
        lines = [f"# Dependencies for: {file}", ""]

        # Find the file
        file_info = None
        for f in code_map.get("files", []):
            if f.get("path") == file or file in f.get("path", ""):
                file_info = f
                break

        if not file_info:
            return f"File not found: {file}"

        if direction in ("imports", "both"):
            imports = file_info.get("imports", [])
            lines.append(f"## Imports ({len(imports)})")
            for imp in imports:
                lines.append(f"  → {imp}")

        if direction in ("imported_by", "both"):
            # Find files that import this file
            imported_by = []
            for f in code_map.get("files", []):
                if file_info["path"] in f.get("imports", []):
                    imported_by.append(f["path"])

            lines.append(f"\n## Imported By ({len(imported_by)})")
            for imp in imported_by:
                lines.append(f"  ← {imp}")

        return "\n".join(lines)

    def _format_project_dependencies(self, code_map: Dict, direction: str) -> str:
        """Format project-wide dependencies."""
        files = code_map.get("files", [])

        lines = [
            f"# Project Dependencies ({len(files)} files)",
            "",
            "## Most Connected Files:",
        ]

        # Calculate connectivity
        connections = []
        for f in files:
            imports = len(f.get("imports", []))
            connections.append((f["path"], imports))

        connections.sort(key=lambda x: x[1], reverse=True)

        for path, count in connections[:10]:
            lines.append(f"- {path}: {count} imports")

        return "\n".join(lines)

    def _format_file_structure(self, file_info: Dict, include_private: bool) -> str:
        """Format file structure with symbols."""
        lines = [f"# Structure: {file_info['path']}", ""]

        symbols = file_info.get("symbols", [])
        if not include_private:
            symbols = [s for s in symbols if not s["name"].startswith("_")]

        # Group by type
        classes = [s for s in symbols if s.get("type") == "class"]
        functions = [s for s in symbols if s.get("type") == "function"]
        methods = [s for s in symbols if s.get("type") == "method"]

        if classes:
            lines.append("## Classes")
            for c in classes:
                lines.append(f"- `{c['name']}` (L{c.get('start_line', '?')}-{c.get('end_line', '?')})")

        if functions:
            lines.append("\n## Functions")
            for f in functions:
                lines.append(f"- `{f['name']}` (L{f.get('start_line', '?')}-{f.get('end_line', '?')})")

        if methods:
            lines.append(f"\n## Methods ({len(methods)})")
            for m in methods[:10]:
                lines.append(f"- `{m['name']}` (L{m.get('start_line', '?')})")
            if len(methods) > 10:
                lines.append(f"  ... and {len(methods) - 10} more")

        return "\n".join(lines)


# ==============================================================================
# MCP SERVER
# ==============================================================================

def create_server(workspace_root: Optional[str] = None) -> "Server":
    """Create and configure the MCP server."""
    if not HAS_MCP:
        raise ImportError(
            "MCP SDK not installed. Install with: pip install mcp"
        )

    server = Server("codenav")
    handler = CodenavToolHandler(workspace_root)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name=tool["name"],
                description=tool["description"],
                inputSchema=tool["inputSchema"],
            )
            for tool in TOOLS
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> Sequence[TextContent]:
        """Execute a tool and return the result."""
        try:
            if name == "codenav_scan":
                result = await handler.handle_scan(arguments)
            elif name == "codenav_search":
                result = await handler.handle_search(arguments)
            elif name == "codenav_read":
                result = await handler.handle_read(arguments)
            elif name == "codenav_get_hubs":
                result = await handler.handle_get_hubs(arguments)
            elif name == "codenav_get_dependencies":
                result = await handler.handle_get_dependencies(arguments)
            elif name == "codenav_get_structure":
                result = await handler.handle_get_structure(arguments)
            else:
                result = f"Unknown tool: {name}"

            return [TextContent(type="text", text=result)]

        except Exception as e:
            logger.exception(f"Error executing tool {name}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available resources."""
        return [
            Resource(
                uri="codenav://code-map",
                name="Code Map",
                description="The current codebase structural map",
                mimeType="application/json",
            ),
            Resource(
                uri="codenav://dependencies",
                name="Dependency Graph",
                description="File dependency relationships",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """Read a resource by URI."""
        if uri == "codenav://code-map":
            code_map = handler._get_code_map(handler.workspace_root)
            return json.dumps(code_map, indent=2)
        elif uri == "codenav://dependencies":
            code_map = handler._get_code_map(handler.workspace_root)
            # Extract just the dependencies
            deps = {
                f["path"]: f.get("imports", [])
                for f in code_map.get("files", [])
            }
            return json.dumps(deps, indent=2)
        else:
            return f"Unknown resource: {uri}"

    @server.list_prompts()
    async def list_prompts() -> list[Prompt]:
        """List available prompts."""
        return [
            Prompt(
                name="analyze-architecture",
                description="Analyze the architecture of a codebase",
                arguments=[
                    PromptArgument(
                        name="path",
                        description="Path to the codebase",
                        required=True,
                    )
                ],
            ),
            Prompt(
                name="find-entry-points",
                description="Find the main entry points of an application",
                arguments=[
                    PromptArgument(
                        name="path",
                        description="Path to the codebase",
                        required=True,
                    )
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: Dict[str, str]) -> GetPromptResult:
        """Get a prompt by name."""
        path = arguments.get("path", ".")

        if name == "analyze-architecture":
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""Analyze the architecture of the codebase at {path}.

1. First, scan the codebase using codenav_scan
2. Identify the architectural hubs using codenav_get_hubs
3. Analyze the dependency structure using codenav_get_dependencies
4. Provide a summary of:
   - Overall structure and organization
   - Key modules and their responsibilities
   - Coupling between components
   - Potential areas for improvement"""
                        ),
                    )
                ],
            )
        elif name == "find-entry-points":
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"""Find and explain the entry points for the application at {path}.

1. Scan the codebase using codenav_scan
2. Search for common entry point patterns (main, cli, app)
3. Read the relevant files to understand how the application starts
4. Provide a summary of how to run and use the application"""
                        ),
                    )
                ],
            )
        else:
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(type="text", text=f"Unknown prompt: {name}"),
                    )
                ],
            )

    return server


async def run_server(workspace_root: Optional[str] = None):
    """Run the MCP server using stdio transport."""
    server = create_server(workspace_root)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


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

    if not HAS_MCP:
        print("Error: MCP SDK not installed. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_server(args.workspace))


if __name__ == "__main__":
    main()
