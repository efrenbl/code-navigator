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
import json
import os
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional

__version__ = "1.0.1"


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
    parser.add_argument("-l", "--limit", type=int, default=10, help="Maximum results (default: 10)")
    parser.add_argument("--no-fuzzy", action="store_true", help="Disable fuzzy matching")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

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
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
