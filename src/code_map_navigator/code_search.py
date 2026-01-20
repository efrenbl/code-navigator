#!/usr/bin/env python3
"""Code Search - Search through the code map to find symbols, files, and locations.

This module provides search functionality over a pre-built code map, enabling
token-efficient navigation by returning only the locations of relevant code
without reading file contents.

Example:
    Command line usage:
        $ code-search "process_payment" --type function
        $ code-search --structure src/api.py
        $ code-search --deps "calculate_total"

    Python API usage:
        >>> searcher = CodeSearcher('.codemap.json')
        >>> results = searcher.search_symbol('payment', symbol_type='function')
        >>> for r in results:
        ...     print(f"{r.name} in {r.file}:{r.lines}")
"""

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Union

from .colors import get_colors

__version__ = "1.2.0"


@dataclass
class SearchResult:
    """Represents a search result from the code map.

    Attributes:
        name: Symbol name (e.g., 'process_payment').
        type: Symbol type ('function', 'class', 'method', etc.).
        file: File path relative to project root.
        lines: [start_line, end_line] tuple.
        signature: Function/class signature if available.
        docstring: Truncated docstring if available.
        parent: Parent class name for methods.
        score: Relevance score (0.0 to 1.0).

    Example:
        >>> result = SearchResult(
        ...     name='process_payment',
        ...     type='function',
        ...     file='src/billing.py',
        ...     lines=[45, 89],
        ...     score=1.0
        ... )
        >>> print(result.to_dict())
    """

    name: str
    type: str
    file: str
    lines: List[int]
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent: Optional[str] = None
    score: float = 0.0

    def to_dict(self) -> Dict:
        """Convert the search result to a dictionary.

        Returns:
            Dict representation suitable for JSON serialization.
        """
        result = {
            "name": self.name,
            "type": self.type,
            "file": self.file,
            "lines": self.lines,
            "score": round(self.score, 2),
        }
        if self.signature:
            result["signature"] = self.signature
        if self.docstring:
            result["docstring"] = self.docstring
        if self.parent:
            result["parent"] = self.parent
        return result


class CodeSearcher:
    """Search through a code map for symbols and files.

    Provides various search methods including fuzzy symbol search,
    file pattern matching, dependency analysis, and structure queries.

    Attributes:
        map_path: Path to the code map JSON file.
        code_map: Loaded code map dictionary.

    Example:
        >>> searcher = CodeSearcher('.codemap.json')
        >>> results = searcher.search_symbol('user', symbol_type='class')
        >>> print(f"Found {len(results)} classes matching 'user'")

        >>> # Get file structure
        >>> structure = searcher.get_file_structure('src/models/user.py')
        >>> print(structure['classes'].keys())

        >>> # Find dependencies
        >>> deps = searcher.find_dependencies('process_payment')
        >>> print(deps['called_by'])
    """

    def __init__(self, map_path: str):
        """Initialize the code searcher.

        Args:
            map_path: Path to the .codemap.json file.

        Raises:
            FileNotFoundError: If the code map file doesn't exist.
        """
        self.map_path = map_path
        self.code_map = self._load_map()

    def _load_map(self) -> Dict:
        """Load the code map from file.

        Returns:
            Parsed code map dictionary.
        """
        with open(self.map_path, encoding="utf-8") as f:
            return json.load(f)

    def _similarity(self, a: str, b: str) -> float:
        """Calculate string similarity ratio.

        Args:
            a: First string.
            b: Second string.

        Returns:
            Similarity ratio between 0.0 and 1.0.
        """
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def search_symbol(
        self,
        query: str,
        symbol_type: Optional[str] = None,
        file_pattern: Optional[str] = None,
        limit: int = 10,
        fuzzy: bool = True,
    ) -> List[SearchResult]:
        """Search for symbols by name.

        Performs fuzzy matching against the code map index to find functions,
        classes, methods, and other symbols.

        Args:
            query: Symbol name or pattern to search for.
            symbol_type: Filter by type ('function', 'class', 'method', etc.).
            file_pattern: Regex pattern to filter by file path.
            limit: Maximum results to return.
            fuzzy: Enable fuzzy matching (default: True).

        Returns:
            List of SearchResult objects sorted by relevance score.

        Example:
            >>> results = searcher.search_symbol('payment', symbol_type='function')
            >>> for r in results:
            ...     print(f"{r.name}: {r.file}:{r.lines[0]}-{r.lines[1]}")
        """
        results = []
        query_lower = query.lower()

        index = self.code_map.get("index", {})

        # Direct lookup for exact matches
        if query_lower in index:
            for entry in index[query_lower]:
                if symbol_type and entry["type"] != symbol_type:
                    continue
                if file_pattern and not re.search(file_pattern, entry["file"], re.IGNORECASE):
                    continue

                file_info = self.code_map["files"].get(entry["file"], {})
                for sym in file_info.get("symbols", []):
                    if sym["name"].lower() == query_lower and sym["lines"] == entry["lines"]:
                        results.append(
                            SearchResult(
                                name=sym["name"],
                                type=sym["type"],
                                file=entry["file"],
                                lines=sym["lines"],
                                signature=sym.get("signature"),
                                docstring=sym.get("docstring"),
                                parent=sym.get("parent"),
                                score=1.0,
                            )
                        )

        # Fuzzy search if enabled and more results needed
        if (not results or fuzzy) and len(results) < limit:
            for file_path, file_info in self.code_map.get("files", {}).items():
                if file_pattern and not re.search(file_pattern, file_path, re.IGNORECASE):
                    continue

                for sym in file_info.get("symbols", []):
                    if symbol_type and sym["type"] != symbol_type:
                        continue

                    name_lower = sym["name"].lower()

                    # Skip if already found
                    if any(r.name.lower() == name_lower and r.file == file_path for r in results):
                        continue

                    # Calculate relevance score
                    score = 0.0

                    if name_lower == query_lower:
                        score = 1.0
                    elif query_lower in name_lower:
                        score = 0.7 + (len(query) / len(sym["name"])) * 0.2
                    elif name_lower in query_lower:
                        score = 0.5
                    elif fuzzy:
                        sim = self._similarity(query, sym["name"])
                        if sim > 0.5:
                            score = sim * 0.6

                    # Boost for signature match
                    if score > 0 and sym.get("signature"):
                        if query_lower in sym["signature"].lower():
                            score = min(1.0, score + 0.1)

                    if score > 0.3:
                        results.append(
                            SearchResult(
                                name=sym["name"],
                                type=sym["type"],
                                file=file_path,
                                lines=sym["lines"],
                                signature=sym.get("signature"),
                                docstring=sym.get("docstring"),
                                parent=sym.get("parent"),
                                score=score,
                            )
                        )

        results.sort(key=lambda x: (-x.score, x.name))
        return results[:limit]

    def search_file(self, pattern: str, limit: int = 20) -> List[Dict]:
        """Search for files by path pattern.

        Args:
            pattern: Regex pattern or substring to match against file paths.
            limit: Maximum results to return.

        Returns:
            List of dicts with file info (path, hash, symbol counts).

        Example:
            >>> files = searcher.search_file('models/')
            >>> for f in files:
            ...     print(f"{f['file']}: {f['total_symbols']} symbols")
        """
        results = []

        for file_path, file_info in self.code_map.get("files", {}).items():
            if re.search(pattern, file_path, re.IGNORECASE):
                symbols_summary = {}
                for sym in file_info.get("symbols", []):
                    sym_type = sym["type"]
                    symbols_summary[sym_type] = symbols_summary.get(sym_type, 0) + 1

                results.append(
                    {
                        "file": file_path,
                        "hash": file_info.get("hash", ""),
                        "symbols": symbols_summary,
                        "total_symbols": len(file_info.get("symbols", [])),
                    }
                )

        results.sort(key=lambda x: x["file"])
        return results[:limit]

    def get_file_structure(self, file_path: str) -> Optional[Dict]:
        """Get the structure of a specific file.

        Returns all symbols in the file organized hierarchically by type.

        Args:
            file_path: Path to the file (can be partial).

        Returns:
            Dict with classes, functions, and other symbols, or None if not found.

        Example:
            >>> structure = searcher.get_file_structure('src/models/user.py')
            >>> print(list(structure['classes'].keys()))
            ['User', 'UserProfile']
        """
        file_info = self.code_map.get("files", {}).get(file_path)
        if not file_info:
            # Try partial match
            for path, info in self.code_map.get("files", {}).items():
                if file_path in path:
                    file_info = info
                    file_path = path
                    break

        if not file_info:
            return None

        classes = {}
        functions = []
        other = []

        for sym in file_info.get("symbols", []):
            if sym["type"] == "class":
                classes[sym["name"]] = {
                    "lines": sym["lines"],
                    "signature": sym.get("signature"),
                    "docstring": sym.get("docstring"),
                    "methods": [],
                }
            elif sym["type"] == "method" and sym.get("parent"):
                if sym["parent"] in classes:
                    classes[sym["parent"]]["methods"].append(
                        {
                            "name": sym["name"],
                            "lines": sym["lines"],
                            "signature": sym.get("signature"),
                        }
                    )
            elif sym["type"] == "function":
                functions.append(
                    {
                        "name": sym["name"],
                        "lines": sym["lines"],
                        "signature": sym.get("signature"),
                        "docstring": sym.get("docstring"),
                    }
                )
            else:
                other.append({"name": sym["name"], "type": sym["type"], "lines": sym["lines"]})

        return {
            "file": file_path,
            "hash": file_info.get("hash", ""),
            "classes": classes,
            "functions": functions,
            "other": other if other else None,
        }

    def find_dependencies(self, symbol_name: str, file_path: Optional[str] = None) -> Dict:
        """Find what a symbol depends on and what depends on it.

        Args:
            symbol_name: Name of the symbol to analyze.
            file_path: Optional file path filter.

        Returns:
            Dict with 'calls' (what this symbol uses) and 'called_by' lists.

        Example:
            >>> deps = searcher.find_dependencies('process_payment')
            >>> print(f"Calls: {deps['calls']}")
            >>> print(f"Called by: {len(deps['called_by'])} functions")
        """
        deps_of = []
        depended_by = []

        target_file = None
        target_lines = None

        for fpath, file_info in self.code_map.get("files", {}).items():
            if file_path and file_path not in fpath:
                continue

            for sym in file_info.get("symbols", []):
                if sym["name"].lower() == symbol_name.lower():
                    target_file = fpath
                    target_lines = sym["lines"]
                    if sym.get("deps"):
                        deps_of = sym["deps"]
                    break

            for sym in file_info.get("symbols", []):
                if sym.get("deps") and symbol_name in sym["deps"]:
                    depended_by.append({"name": sym["name"], "file": fpath, "lines": sym["lines"]})

        return {
            "symbol": symbol_name,
            "file": target_file,
            "lines": target_lines,
            "calls": deps_of,
            "called_by": depended_by,
        }

    def get_stats(self) -> Dict:
        """Get statistics about the codebase.

        Returns:
            Dict with root path, generation time, file count, symbol count,
            and breakdown by symbol type.

        Example:
            >>> stats = searcher.get_stats()
            >>> print(f"Total: {stats['total_symbols']} symbols in {stats['files']} files")
        """
        stats = self.code_map.get("stats", {})

        type_counts = {}
        for file_info in self.code_map.get("files", {}).values():
            for sym in file_info.get("symbols", []):
                sym_type = sym["type"]
                type_counts[sym_type] = type_counts.get(sym_type, 0) + 1

        return {
            "root": self.code_map.get("root"),
            "generated_at": self.code_map.get("generated_at"),
            "files": stats.get("files_processed", len(self.code_map.get("files", {}))),
            "total_symbols": stats.get("symbols_found", 0),
            "by_type": type_counts,
        }

    def list_by_type(
        self, symbol_type: str, file_pattern: Optional[str] = None, limit: int = 100
    ) -> List[SearchResult]:
        """List all symbols of a specific type.

        Args:
            symbol_type: Type to filter by ('function', 'class', 'method', etc.).
            file_pattern: Optional regex pattern to filter by file path.
            limit: Maximum results to return.

        Returns:
            List of SearchResult objects matching the type.

        Example:
            >>> classes = searcher.list_by_type('class')
            >>> for c in classes:
            ...     print(f"{c.name} in {c.file}:{c.lines[0]}")
        """
        results = []

        for file_path, file_info in self.code_map.get("files", {}).items():
            if file_pattern and not re.search(file_pattern, file_path, re.IGNORECASE):
                continue

            for sym in file_info.get("symbols", []):
                if sym["type"] != symbol_type:
                    continue

                results.append(
                    SearchResult(
                        name=sym["name"],
                        type=sym["type"],
                        file=file_path,
                        lines=sym["lines"],
                        signature=sym.get("signature"),
                        docstring=sym.get("docstring"),
                        parent=sym.get("parent"),
                        score=1.0,
                    )
                )

                if len(results) >= limit:
                    break

            if len(results) >= limit:
                break

        # Sort by file path and name for consistent output
        results.sort(key=lambda x: (x.file, x.name))
        return results[:limit]

    def check_stale_files(self, root_path: Optional[str] = None) -> Dict:
        """Check for files that have changed since the map was generated.

        Compares current file hashes with stored hashes to detect modifications.

        Args:
            root_path: Root path of the codebase. If None, uses the root from the map.

        Returns:
            Dict with 'stale' (modified files), 'missing' (deleted files),
            'new' (untracked files in map), and 'is_stale' boolean.

        Example:
            >>> result = searcher.check_stale_files()
            >>> if result['is_stale']:
            ...     print(f"Warning: {len(result['stale'])} files changed")
        """
        root = root_path or self.code_map.get("root", "")
        if not root or not os.path.isdir(root):
            return {
                "error": f"Root path not found: {root}",
                "is_stale": False,
                "stale": [],
                "missing": [],
            }

        root_path_obj = Path(root)
        stale_files = []
        missing_files = []

        for file_path, file_info in self.code_map.get("files", {}).items():
            full_path = root_path_obj / file_path
            stored_hash = file_info.get("hash", "")

            if not full_path.exists():
                missing_files.append(file_path)
            else:
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    current_hash = hashlib.md5(content.encode()).hexdigest()[:12]
                    if current_hash != stored_hash:
                        stale_files.append(file_path)
                except Exception:
                    stale_files.append(file_path)

        return {
            "is_stale": len(stale_files) > 0 or len(missing_files) > 0,
            "stale": stale_files,
            "missing": missing_files,
            "total_checked": len(self.code_map.get("files", {})),
            "generated_at": self.code_map.get("generated_at"),
        }

    def get_changes_since_commit(self, commit: str, root_path: Optional[str] = None) -> Dict:
        """Get symbols in files that changed since a specific git commit.

        Args:
            commit: Git commit reference (hash, branch, tag, HEAD~N, etc.)
            root_path: Root path of the codebase. If None, uses the root from the map.

        Returns:
            Dict with changed files and their symbols.

        Example:
            >>> result = searcher.get_changes_since_commit('HEAD~5')
            >>> for f in result['changed_files']:
            ...     print(f"{f['file']}: {len(f['symbols'])} symbols")
        """
        import subprocess

        root = root_path or self.code_map.get("root", "")
        if not root or not os.path.isdir(root):
            return {"error": f"Root path not found: {root}", "changed_files": []}

        # Get changed files from git
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", commit, "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return {"error": f"Git error: {result.stderr.strip()}", "changed_files": []}

            changed_files = (
                set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            return {"error": f"Git not available: {e}", "changed_files": []}

        # Find symbols in changed files
        files_with_symbols = []
        for file_path, file_info in self.code_map.get("files", {}).items():
            if file_path in changed_files:
                files_with_symbols.append(
                    {
                        "file": file_path,
                        "symbols": file_info.get("symbols", []),
                    }
                )

        return {
            "commit": commit,
            "total_changed": len(changed_files),
            "tracked_changed": len(files_with_symbols),
            "changed_files": files_with_symbols,
        }


def format_search_output(
    result: Union[Dict, List],
    style: str = "json",
    compact: bool = False,
    no_color: bool = False,
) -> str:
    """Format search results for display.

    Args:
        result: Search results (dict or list of dicts).
        style: Output style ('json' or 'table').
        compact: If True, output compact JSON.
        no_color: If True, disable colored output.

    Returns:
        Formatted string representation.
    """
    if style == "json":
        if compact:
            return json.dumps(result, separators=(",", ":"))
        return json.dumps(result, indent=2)

    # Table format with colors
    c = get_colors(no_color=no_color)

    if isinstance(result, dict):
        # Handle error
        if "error" in result:
            return c.error(f"Error: {result['error']}")

        # Handle --since-commit output
        if "changed_files" in result and "commit" in result:
            if result.get("error"):
                return c.error(f"Error: {result['error']}")

            output = [c.bold(f"Changes since {c.cyan(result.get('commit', 'Unknown'))}")]
            output.append(f"  Total changed files: {c.yellow(str(result.get('total_changed', 0)))}")
            output.append(f"  Tracked in map: {c.green(str(result.get('tracked_changed', 0)))}")

            changed_files = result.get("changed_files", [])
            if changed_files:
                output.append("")
                for file_info in changed_files[:20]:
                    file_path = file_info.get("file", "?")
                    symbols = file_info.get("symbols", [])
                    output.append(f"  {c.cyan(file_path)}")
                    for sym in symbols[:5]:
                        sym_type = c.magenta(f"[{sym.get('type', '?')}]")
                        sym_name = c.green(sym.get("name", "?"))
                        lines = sym.get("lines", [0, 0])
                        output.append(f"    {sym_type} {sym_name} :{lines[0]}-{lines[1]}")
                    if len(symbols) > 5:
                        output.append(f"    {c.dim(f'... and {len(symbols) - 5} more symbols')}")

                if len(changed_files) > 20:
                    output.append(f"\n  {c.dim(f'... and {len(changed_files) - 20} more files')}")
            else:
                output.append(f"\n  {c.dim('No tracked files changed')}")

            return "\n".join(output)

        # Handle stale check
        if "is_stale" in result:
            if result.get("error"):
                return c.error(f"Error: {result['error']}")

            output = [c.bold("Stale File Check")]
            output.append(f"  Generated: {c.dim(result.get('generated_at', 'Unknown'))}")
            output.append(f"  Files checked: {c.cyan(str(result.get('total_checked', 0)))}")

            stale = result.get("stale", [])
            missing = result.get("missing", [])

            if result.get("is_stale"):
                if stale:
                    output.append(f"  {c.yellow(f'Modified ({len(stale)}):')}")
                    for f in stale[:10]:
                        output.append(f"    {c.yellow(f)}")
                    if len(stale) > 10:
                        output.append(f"    {c.dim(f'... and {len(stale) - 10} more')}")

                if missing:
                    output.append(f"  {c.magenta(f'Deleted ({len(missing)}):')}")
                    for f in missing[:10]:
                        output.append(f"    {c.magenta(f)}")
                    if len(missing) > 10:
                        output.append(f"    {c.dim(f'... and {len(missing) - 10} more')}")

                output.append("")
                output.append(c.warning("Run 'codemap map --incremental' to update the map."))
            else:
                output.append(f"  Status: {c.success('Up to date')}")

            return "\n".join(output)

        # Handle stats
        if "total_symbols" in result:
            output = [c.bold("Codebase Statistics")]
            output.append(f"  Root: {c.cyan(result.get('root', 'N/A'))}")
            output.append(f"  Files: {c.green(str(result.get('files', 0)))}")
            output.append(f"  Symbols: {c.green(str(result.get('total_symbols', 0)))}")
            if "by_type" in result:
                output.append("  By type:")
                for type_name, count in result["by_type"].items():
                    output.append(f"    {c.magenta(type_name)}: {count}")
            return "\n".join(output)

        # Handle file structure
        if "symbols" in result:
            output = [c.bold(f"Structure: {c.cyan(result.get('file', 'Unknown'))}")]
            for sym in result.get("symbols", []):
                sym_type = c.magenta(f"[{sym.get('type', '?')}]")
                sym_name = c.green(sym.get("name", "?"))
                lines = sym.get("lines", [0, 0])
                line_range = c.cyan(f":{lines[0]}-{lines[1]}")
                output.append(f"  {sym_type} {sym_name}{line_range}")
            return "\n".join(output)

        # Handle dependencies
        if "calls" in result or "called_by" in result:
            output = [c.bold(f"Dependencies: {c.green(result.get('symbol', 'Unknown'))}")]
            if result.get("calls"):
                output.append("  Calls:")
                for call in result["calls"]:
                    output.append(f"    {c.cyan(call)}")
            if result.get("called_by"):
                output.append("  Called by:")
                for caller in result["called_by"]:
                    output.append(f"    {c.cyan(caller)}")
            if not result.get("calls") and not result.get("called_by"):
                output.append(c.dim("  No dependencies found"))
            return "\n".join(output)

        # Fallback to JSON for unknown dict structures
        return json.dumps(result, indent=2)

    # Handle list of search results
    if isinstance(result, list):
        if not result:
            return c.dim("No results found")

        output = []
        for item in result:
            sym_type = c.magenta(f"[{item.get('type', '?')}]")
            sym_name = c.green(item.get("name", "?"))
            file_path = c.cyan(item.get("file", "?"))
            lines = item.get("lines", [0, 0])
            line_range = f"{lines[0]}-{lines[1]}"

            output.append(f"{sym_type} {sym_name}")
            output.append(f"    {file_path}:{c.yellow(line_range)}")

            if item.get("signature"):
                sig = item["signature"]
                if len(sig) > 60:
                    sig = sig[:57] + "..."
                output.append(f"    {c.dim(sig)}")

        return "\n".join(output)

    return str(result)


def add_search_arguments(parser: argparse.ArgumentParser) -> None:
    """Add search command arguments to a parser.

    Args:
        parser: The argument parser to add arguments to.
    """
    parser.add_argument("query", nargs="?", help="Search query (symbol name, file pattern, etc.)")
    parser.add_argument(
        "-m",
        "--map",
        default=".codemap.json",
        help="Path to code map file (default: .codemap.json)",
    )
    parser.add_argument(
        "-t",
        "--type",
        choices=["function", "class", "method", "interface", "struct", "trait", "enum"],
        help="Filter by symbol type",
    )
    parser.add_argument("-f", "--file", help="Filter by file path pattern")
    parser.add_argument("--files", action="store_true", help="Search for files instead of symbols")
    parser.add_argument("--structure", help="Show structure of a specific file")
    parser.add_argument("--deps", help="Show dependencies of a symbol")
    parser.add_argument("--stats", action="store_true", help="Show codebase statistics")
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="Check if any files have changed since map generation",
    )
    parser.add_argument(
        "--warn-stale",
        action="store_true",
        help="Warn if files are stale before showing results",
    )
    parser.add_argument(
        "--since-commit",
        metavar="COMMIT",
        help="Show symbols in files changed since COMMIT (git ref: hash, branch, HEAD~N)",
    )
    parser.add_argument("-l", "--limit", type=int, default=10, help="Maximum results (default: 10)")
    parser.add_argument("--no-fuzzy", action="store_true", help="Disable fuzzy matching")
    parser.add_argument(
        "--compact", action="store_true", help="Output compact JSON (default: pretty-printed)"
    )
    parser.add_argument(
        "-o",
        "--output",
        choices=["json", "table"],
        default="json",
        help="Output format (default: json)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")


def run_search(args: argparse.Namespace) -> None:
    """Execute the search command with parsed arguments.

    Args:
        args: Parsed command-line arguments.
    """
    # Find map file
    map_path = args.map
    if not os.path.isabs(map_path) and not os.path.exists(map_path):
        cwd_map = os.path.join(os.getcwd(), ".codemap.json")
        if os.path.exists(cwd_map):
            map_path = cwd_map

    if not os.path.exists(map_path):
        print(json.dumps({"error": f"Code map not found: {map_path}"}))
        sys.exit(1)

    searcher = CodeSearcher(map_path)
    c = get_colors(no_color=args.no_color)

    # Check for stale files if requested
    if args.check_stale:
        result = searcher.check_stale_files()
        print(
            format_search_output(
                result,
                style=args.output,
                compact=args.compact,
                no_color=args.no_color,
            )
        )
        return

    # Warn about stale files if requested
    if getattr(args, "warn_stale", False):
        stale_result = searcher.check_stale_files()
        if stale_result.get("is_stale"):
            stale_count = len(stale_result.get("stale", []))
            missing_count = len(stale_result.get("missing", []))
            warnings = []
            if stale_count > 0:
                warnings.append(f"{stale_count} modified")
            if missing_count > 0:
                warnings.append(f"{missing_count} deleted")
            print(
                c.warning(
                    f"Warning: {', '.join(warnings)} files since map generation. "
                    "Run 'codemap map --incremental' to update."
                ),
                file=sys.stderr,
            )

    # Handle --since-commit
    if getattr(args, "since_commit", None):
        result = searcher.get_changes_since_commit(args.since_commit)
        print(
            format_search_output(
                result,
                style=args.output,
                compact=args.compact,
                no_color=args.no_color,
            )
        )
        return

    # Determine operation
    if args.stats:
        result = searcher.get_stats()
    elif args.structure:
        result = searcher.get_file_structure(args.structure)
        if not result:
            result = {"error": f"File not found: {args.structure}"}
    elif args.deps:
        result = searcher.find_dependencies(args.deps, args.file)
    elif args.files:
        if not args.query:
            result = {"error": "Query required for file search"}
        else:
            result = searcher.search_file(args.query, args.limit)
    elif args.query:
        results = searcher.search_symbol(
            args.query,
            symbol_type=args.type,
            file_pattern=args.file,
            limit=args.limit,
            fuzzy=not args.no_fuzzy,
        )
        result = [r.to_dict() for r in results]
    elif args.type:
        # List all symbols of specified type (no query needed)
        results = searcher.list_by_type(args.type, file_pattern=args.file, limit=args.limit)
        result = [r.to_dict() for r in results]
    else:
        result = {
            "error": "No query provided. Use --help for usage or --type to list all symbols of a type."
        }

    # Output
    print(
        format_search_output(
            result,
            style=args.output,
            compact=args.compact,
            no_color=args.no_color,
        )
    )


def main():
    """Command-line interface for code search.

    Usage:
        code-search QUERY [--type TYPE] [--file PATTERN] [--limit N]
        code-search --structure FILE
        code-search --deps SYMBOL
        code-search --stats

    Example:
        $ code-search "payment" --type function --limit 5
        $ code-search --structure src/api.py --pretty
    """
    parser = argparse.ArgumentParser(
        description="Search through a code map for symbols and files",
        epilog='Example: code-search "payment" --type function',
    )
    add_search_arguments(parser)
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()
    run_search(args)


if __name__ == "__main__":
    main()
