#!/usr/bin/env python3
"""DependencyGraph - Architectural importance analysis using PageRank.

This module provides graph-based analysis of file dependencies to identify
architecturally critical files ("hubs") in a codebase. Unlike simple import
counting, PageRank propagates importance transitively, giving higher scores
to files imported by other important files.

Example:
    >>> graph = DependencyGraph('/path/to/project')
    >>> graph.build()
    >>> critical = graph.get_critical_paths(top_n=10)
    >>> for file, score in critical:
    ...     print(f"{file}: {score:.4f}")
"""

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

try:
    import networkx as nx

    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    nx = None


@dataclass
class FileNode:
    """Represents a file in the dependency graph.

    Attributes:
        path: Relative path from project root.
        language: Detected programming language.
        imports: List of import strings found in the file.
        resolved_imports: List of resolved file paths this file imports.
        importers: List of files that import this file.
        pagerank: Computed PageRank score (architectural importance).
        in_degree: Number of files importing this file.
        out_degree: Number of files this file imports.
    """

    path: str
    language: str = ""
    imports: List[str] = field(default_factory=list)
    resolved_imports: List[str] = field(default_factory=list)
    importers: List[str] = field(default_factory=list)
    pagerank: float = 0.0
    in_degree: int = 0
    out_degree: int = 0


class DependencyGraph:
    """Analyzes file-level dependencies and computes architectural importance.

    This class builds a directed graph where nodes are files and edges represent
    import relationships. It uses PageRank to compute "Architectural Importance"
    scores, which are superior to simple import counting because:

    1. **Transitive propagation**: If file A is imported by B and C, and B/C are
       themselves highly important (imported by many important files), A gets
       a higher score than if B/C were leaf nodes.

    2. **Hub detection**: Identifies true architectural hubs - files that are
       central to the codebase structure, not just frequently imported utilities.

    3. **Noise resistance**: A file imported by many trivial test files won't
       rank as high as one imported by core business logic modules.

    Attributes:
        root: Absolute path to the project root.
        graph: NetworkX DiGraph representing file dependencies.
        nodes: Dict mapping file paths to FileNode objects.
        file_index: Index for fast import resolution.
        module_name: Detected module name (from go.mod, pyproject.toml, etc.).

    Example:
        >>> dg = DependencyGraph('/my/project')
        >>> dg.build()
        >>>
        >>> # Get top 10 most important files
        >>> critical = dg.get_critical_paths(top_n=10)
        >>>
        >>> # Check if a specific file is a hub
        >>> if dg.is_hub('src/core/config.py'):
        ...     print("config.py is architecturally critical!")
        >>>
        >>> # Get all connected files
        >>> connected = dg.get_connected_files('src/main.py')
    """

    # Supported file extensions by language
    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "go": [".go"],
        "rust": [".rs"],
        "java": [".java"],
        "ruby": [".rb"],
    }

    # Directories to ignore
    IGNORED_DIRS = {
        "node_modules",
        "__pycache__",
        ".git",
        ".svn",
        "venv",
        "env",
        ".env",
        "dist",
        "build",
        ".next",
        "coverage",
        "vendor",
        "target",
        ".tox",
        "eggs",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    # PageRank parameters
    DEFAULT_DAMPING = 0.85  # Standard damping factor
    DEFAULT_MAX_ITER = 100  # Maximum iterations for convergence
    DEFAULT_TOL = 1e-06  # Convergence tolerance

    def __init__(self, root: str, damping: float = None):
        """Initialize the dependency graph analyzer.

        Args:
            root: Path to the project root directory.
            damping: PageRank damping factor (default: 0.85).
                    Higher values give more weight to direct imports.

        Raises:
            ImportError: If networkx is not installed.
            ValueError: If root path doesn't exist.
        """
        if not HAS_NETWORKX:
            raise ImportError(
                "networkx is required for DependencyGraph. " "Install with: pip install networkx"
            )

        self.root = Path(root).resolve()
        if not self.root.exists():
            raise ValueError(f"Root path does not exist: {self.root}")

        self.damping = damping or self.DEFAULT_DAMPING
        self.graph: nx.DiGraph = nx.DiGraph()
        self.nodes: Dict[str, FileNode] = {}
        self.file_index: Dict[str, List[str]] = {}  # Various keys -> file paths
        self.module_name: str = ""
        self._built = False

    def build(self, languages: List[str] = None) -> "DependencyGraph":
        """Scan the project and build the dependency graph.

        Args:
            languages: List of languages to include (default: all supported).

        Returns:
            self, for method chaining.

        Example:
            >>> dg = DependencyGraph('/project').build()
            >>> dg = DependencyGraph('/project').build(languages=['python', 'typescript'])
        """
        # Detect module/package name
        self.module_name = self._detect_module_name()

        # Scan all source files
        files = self._scan_files(languages)

        # Build file index for fast import resolution
        self._build_file_index(files)

        # Extract imports from each file
        for file_path in files:
            self._analyze_file(file_path)

        # Resolve imports to actual files
        self._resolve_all_imports()

        # Build the NetworkX graph
        self._build_networkx_graph()

        # Compute PageRank scores
        self._compute_pagerank()

        self._built = True
        return self

    def _detect_module_name(self) -> str:
        """Detect the module/package name from config files."""
        # Try go.mod
        go_mod = self.root / "go.mod"
        if go_mod.exists():
            try:
                content = go_mod.read_text()
                for line in content.splitlines():
                    if line.startswith("module "):
                        return line.split()[1]
            except Exception:
                pass

        # Try pyproject.toml
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                # Simple regex for [project] name or [tool.poetry] name
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
            except Exception:
                pass

        # Try package.json
        package_json = self.root / "package.json"
        if package_json.exists():
            try:
                import json

                data = json.loads(package_json.read_text())
                return data.get("name", "")
            except Exception:
                pass

        # Fallback to directory name
        return self.root.name

    def _scan_files(self, languages: List[str] = None) -> List[str]:
        """Scan directory for source files.

        Args:
            languages: Filter by languages (None = all).

        Returns:
            List of relative file paths.
        """
        files = []
        extensions = set()

        if languages:
            for lang in languages:
                extensions.update(self.LANGUAGE_EXTENSIONS.get(lang, []))
        else:
            for exts in self.LANGUAGE_EXTENSIONS.values():
                extensions.update(exts)

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter out ignored directories in-place
            dirnames[:] = [d for d in dirnames if d not in self.IGNORED_DIRS]

            for filename in filenames:
                if any(filename.endswith(ext) for ext in extensions):
                    full_path = Path(dirpath) / filename
                    rel_path = str(full_path.relative_to(self.root))
                    files.append(rel_path)

        return files

    def _build_file_index(self, files: List[str]) -> None:
        """Build multi-key index for fast import resolution.

        Creates indexes by:
        - Exact path
        - Path without extension
        - All path suffixes (for nested packages)
        - Directory (for package imports)
        """
        self.file_index = {
            "exact": {},  # exact path -> [files]
            "no_ext": {},  # path without extension -> [files]
            "suffix": {},  # path suffix -> [files]
            "dir": {},  # directory -> [files]
            "basename": {},  # just filename -> [files]
        }

        for path in files:
            # Exact match
            self._add_to_index("exact", path, path)

            # Without extension
            no_ext = str(Path(path).with_suffix(""))
            self._add_to_index("no_ext", no_ext, path)

            # Basename
            basename = Path(path).stem
            self._add_to_index("basename", basename, path)

            # Directory
            dir_path = str(Path(path).parent)
            if dir_path != ".":
                self._add_to_index("dir", dir_path, path)

            # All suffixes (for nested package resolution)
            # e.g., "src/core/config.py" indexed as:
            #   - "core/config.py"
            #   - "config.py"
            parts = Path(path).parts
            for i in range(1, len(parts)):
                suffix = str(Path(*parts[i:]))
                self._add_to_index("suffix", suffix, path)
                # Also without extension
                suffix_no_ext = str(Path(*parts[i:]).with_suffix(""))
                self._add_to_index("suffix", suffix_no_ext, path)

    def _add_to_index(self, index_type: str, key: str, path: str) -> None:
        """Add a path to a specific index."""
        if key not in self.file_index[index_type]:
            self.file_index[index_type][key] = []
        if path not in self.file_index[index_type][key]:
            self.file_index[index_type][key].append(path)

    def _analyze_file(self, rel_path: str) -> None:
        """Extract imports from a single file."""
        full_path = self.root / rel_path
        language = self._detect_language(rel_path)

        node = FileNode(path=rel_path, language=language)

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")

            if language == "python":
                node.imports = self._extract_python_imports(content)
            elif language in ("javascript", "typescript"):
                node.imports = self._extract_js_ts_imports(content)
            elif language == "go":
                node.imports = self._extract_go_imports(content)
            elif language == "rust":
                node.imports = self._extract_rust_imports(content)
            else:
                node.imports = self._extract_generic_imports(content)

        except Exception:
            pass  # Skip files we can't read

        self.nodes[rel_path] = node

    def _detect_language(self, path: str) -> str:
        """Detect language from file extension."""
        ext = Path(path).suffix.lower()
        for lang, extensions in self.LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return lang
        return ""

    def _extract_python_imports(self, content: str) -> List[str]:
        """Extract imports from Python code using AST."""
        imports = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if node.level > 0:  # Relative import
                        imports.append("." * node.level + module)
                    else:
                        imports.append(module)
        except SyntaxError:
            pass
        return imports

    def _extract_js_ts_imports(self, content: str) -> List[str]:
        """Extract imports from JavaScript/TypeScript code."""
        imports = []
        # Match: import ... from 'path' or require('path')
        patterns = [
            r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
            r'import\s+[\'"]([^\'"]+)[\'"]',
            r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
            r'export\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]',
        ]
        for pattern in patterns:
            imports.extend(re.findall(pattern, content))
        return imports

    def _extract_go_imports(self, content: str) -> List[str]:
        """Extract imports from Go code."""
        imports = []
        # Match single import: import "path"
        imports.extend(re.findall(r'import\s+"([^"]+)"', content))
        # Match grouped imports: import ( "path1" "path2" )
        block_match = re.search(r"import\s*\((.*?)\)", content, re.DOTALL)
        if block_match:
            imports.extend(re.findall(r'"([^"]+)"', block_match.group(1)))
        return imports

    def _extract_rust_imports(self, content: str) -> List[str]:
        """Extract imports from Rust code."""
        imports = []
        # Match: use crate::path, use super::path, use path
        imports.extend(re.findall(r"use\s+([\w:]+)", content))
        # Match: mod name
        imports.extend(re.findall(r"mod\s+(\w+)", content))
        return imports

    def _extract_generic_imports(self, content: str) -> List[str]:
        """Fallback import extraction using common patterns."""
        imports = []
        patterns = [
            r'import\s+[\'"]([^\'"]+)[\'"]',
            r'require\s*[\'"]([^\'"]+)[\'"]',
            r'from\s+[\'"]([^\'"]+)[\'"]',
        ]
        for pattern in patterns:
            imports.extend(re.findall(pattern, content))
        return imports

    def _resolve_all_imports(self) -> None:
        """Resolve import strings to actual file paths."""
        for path, node in self.nodes.items():
            resolved = []
            for imp in node.imports:
                files = self._resolve_import(imp, path, node.language)
                # Only count single-file resolutions (not package imports)
                if len(files) == 1:
                    resolved.append(files[0])

            node.resolved_imports = list(set(resolved))

            # Build reverse map (importers)
            for imported_file in node.resolved_imports:
                if imported_file in self.nodes:
                    self.nodes[imported_file].importers.append(path)

    def _resolve_import(self, imp: str, from_file: str, language: str) -> List[str]:
        """Resolve an import string to file path(s).

        Uses multiple strategies in order:
        1. Relative path resolution (./foo, ../bar)
        2. Module-prefixed path (for Go/Python internal packages)
        3. Exact match
        4. Suffix match
        """
        # Normalize the import
        normalized = self._normalize_import(imp, language)
        from_dir = str(Path(from_file).parent)

        # Strategy 1: Relative imports
        if imp.startswith("."):
            return self._resolve_relative_import(imp, from_dir)

        # Strategy 2: Module-prefixed (internal package)
        if self.module_name and imp.startswith(self.module_name):
            rest = imp[len(self.module_name) :].lstrip("/.")
            candidates = self._try_exact_match(rest)
            if candidates:
                return candidates

        # Strategy 3: Exact match
        candidates = self._try_exact_match(normalized)
        if candidates:
            return candidates

        # Strategy 4: Suffix match
        candidates = self._try_suffix_match(normalized)
        if candidates:
            return candidates

        return []

    def _normalize_import(self, imp: str, language: str) -> str:
        """Convert import syntax to a path-like format."""
        imp = imp.strip("\"'`")

        # Python dots to slashes: app.core.config -> app/core/config
        if language == "python" and "." in imp and "/" not in imp:
            if not imp.startswith("."):
                imp = imp.replace(".", "/")

        # Rust :: to slashes
        if language == "rust":
            if imp.startswith("crate::"):
                imp = imp[7:].replace("::", "/")
            elif "::" in imp:
                imp = imp.replace("::", "/")

        return imp

    def _resolve_relative_import(self, imp: str, from_dir: str) -> List[str]:
        """Resolve ./foo or ../bar style imports."""
        # Count parent levels
        levels = 0
        rest = imp
        while rest.startswith(".."):
            levels += 1
            rest = rest[2:].lstrip("/")
        rest = rest.lstrip("./")

        # Navigate up
        target_dir = Path(from_dir)
        for _ in range(levels):
            target_dir = target_dir.parent

        # Build candidate path
        if str(target_dir) == ".":
            candidate = rest
        else:
            candidate = str(target_dir / rest)

        return self._try_exact_match(candidate)

    def _try_exact_match(self, path: str) -> List[str]:
        """Try to match path exactly (with common extensions)."""
        extensions = [
            "",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".go",
            ".rs",
            "/index.js",
            "/index.ts",
            "/index.tsx",
            "/__init__.py",
            "/mod.rs",
        ]

        for ext in extensions:
            candidate = path + ext
            if candidate in self.file_index["exact"]:
                return self.file_index["exact"][candidate]
            if candidate in self.file_index["no_ext"]:
                return self.file_index["no_ext"][candidate]

        return []

    def _try_suffix_match(self, normalized: str) -> List[str]:
        """Find files where path ends with normalized import."""
        extensions = ["", ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs"]

        for ext in extensions:
            candidate = normalized + ext
            if candidate in self.file_index["suffix"]:
                files = self.file_index["suffix"][candidate]
                if len(files) == 1:
                    return files

        return []

    def _build_networkx_graph(self) -> None:
        """Build the NetworkX DiGraph from resolved imports."""
        self.graph.clear()

        # Add all nodes
        for path in self.nodes:
            self.graph.add_node(path)

        # Add edges (importer -> imported)
        # Direction: A imports B means edge from A to B
        # PageRank will give higher scores to nodes with many incoming edges
        for path, node in self.nodes.items():
            for imported_file in node.resolved_imports:
                if imported_file in self.nodes:
                    self.graph.add_edge(path, imported_file)

        # Update degree stats
        for path, node in self.nodes.items():
            node.in_degree = self.graph.in_degree(path)
            node.out_degree = self.graph.out_degree(path)

    def _compute_pagerank(self) -> None:
        """Compute PageRank scores for all nodes."""
        if len(self.graph) == 0:
            return

        try:
            scores = nx.pagerank(
                self.graph,
                alpha=self.damping,
                max_iter=self.DEFAULT_MAX_ITER,
                tol=self.DEFAULT_TOL,
            )

            for path, score in scores.items():
                if path in self.nodes:
                    self.nodes[path].pagerank = score

        except nx.NetworkXError:
            # Graph has issues (e.g., no edges), assign uniform scores
            uniform = 1.0 / max(len(self.nodes), 1)
            for node in self.nodes.values():
                node.pagerank = uniform

    def get_critical_paths(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get the top N architecturally important files.

        Returns files ranked by PageRank score, which represents their
        "Architectural Importance" - how central they are to the codebase
        structure, considering transitive dependencies.

        Args:
            top_n: Number of top files to return.

        Returns:
            List of (file_path, pagerank_score) tuples, sorted by score descending.

        Example:
            >>> critical = dg.get_critical_paths(top_n=5)
            >>> for path, score in critical:
            ...     print(f"{path}: {score:.4f}")
            src/core/config.py: 0.0842
            src/utils/helpers.py: 0.0654
            src/db/connection.py: 0.0521
        """
        if not self._built:
            raise RuntimeError("Graph not built. Call build() first.")

        ranked = sorted(
            [(path, node.pagerank) for path, node in self.nodes.items()],
            key=lambda x: x[1],
            reverse=True,
        )

        return ranked[:top_n]

    def is_hub(self, path: str, threshold: int = 3) -> bool:
        """Check if a file is a hub (imported by many files).

        Args:
            path: Relative file path.
            threshold: Minimum number of importers to be considered a hub.

        Returns:
            True if the file has >= threshold importers.
        """
        if path not in self.nodes:
            return False
        return self.nodes[path].in_degree >= threshold

    def get_hub_files(self, threshold: int = 3) -> List[str]:
        """Get all files that are imported by >= threshold other files.

        Args:
            threshold: Minimum importers to qualify as hub.

        Returns:
            List of file paths that are hubs.
        """
        return [path for path, node in self.nodes.items() if node.in_degree >= threshold]

    def get_connected_files(self, path: str) -> List[str]:
        """Get all files connected to the given file (imports + importers).

        Args:
            path: Relative file path.

        Returns:
            List of connected file paths.
        """
        if path not in self.nodes:
            return []

        node = self.nodes[path]
        connected = set(node.resolved_imports) | set(node.importers)
        connected.discard(path)
        return list(connected)

    def get_dependency_chain(self, path: str, depth: int = 3) -> Dict[str, Any]:
        """Get dependency chain (what this file imports, recursively).

        Args:
            path: Starting file path.
            depth: Maximum depth to traverse.

        Returns:
            Nested dict representing the dependency tree.
        """

        def _build_chain(current: str, remaining_depth: int, seen: Set[str]) -> Dict:
            if remaining_depth <= 0 or current in seen or current not in self.nodes:
                return {}

            seen.add(current)
            node = self.nodes[current]

            return {
                "imports": {
                    dep: _build_chain(dep, remaining_depth - 1, seen.copy())
                    for dep in node.resolved_imports
                    if dep in self.nodes
                }
            }

        return {path: _build_chain(path, depth, set())}

    def get_importers_chain(self, path: str, depth: int = 3) -> Dict[str, Any]:
        """Get reverse dependency chain (what imports this file, recursively).

        Args:
            path: Starting file path.
            depth: Maximum depth to traverse.

        Returns:
            Nested dict representing who imports this file.
        """

        def _build_chain(current: str, remaining_depth: int, seen: Set[str]) -> Dict:
            if remaining_depth <= 0 or current in seen or current not in self.nodes:
                return {}

            seen.add(current)
            node = self.nodes[current]

            return {
                "imported_by": {
                    imp: _build_chain(imp, remaining_depth - 1, seen.copy())
                    for imp in node.importers
                    if imp in self.nodes
                }
            }

        return {path: _build_chain(path, depth, set())}

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the dependency graph.

        Returns:
            Dict with graph statistics.
        """
        if not self._built:
            return {"error": "Graph not built"}

        hub_files = self.get_hub_files()

        return {
            "total_files": len(self.nodes),
            "total_edges": self.graph.number_of_edges(),
            "hub_files": len(hub_files),
            "avg_imports_per_file": (
                sum(n.out_degree for n in self.nodes.values()) / max(len(self.nodes), 1)
            ),
            "avg_importers_per_file": (
                sum(n.in_degree for n in self.nodes.values()) / max(len(self.nodes), 1)
            ),
            "languages": dict(self._count_by_language()),
            "isolated_files": len(
                [n for n in self.nodes.values() if n.in_degree == 0 and n.out_degree == 0]
            ),
        }

    def _count_by_language(self) -> Dict[str, int]:
        """Count files by language."""
        counts: Dict[str, int] = {}
        for node in self.nodes.values():
            lang = node.language or "unknown"
            counts[lang] = counts.get(lang, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        """Export the graph as a serializable dictionary.

        Returns:
            Dict that can be serialized to JSON.
        """
        return {
            "root": str(self.root),
            "module": self.module_name,
            "stats": self.get_stats(),
            "critical_paths": self.get_critical_paths(top_n=20),
            "nodes": {
                path: {
                    "language": node.language,
                    "pagerank": node.pagerank,
                    "in_degree": node.in_degree,
                    "out_degree": node.out_degree,
                    "imports": node.resolved_imports,
                    "importers": node.importers,
                }
                for path, node in self.nodes.items()
            },
        }


def analyze_repository(root: str, top_n: int = 10) -> Dict[str, Any]:
    """Convenience function to analyze a repository.

    Args:
        root: Path to repository root.
        top_n: Number of critical paths to return.

    Returns:
        Analysis results including critical paths and statistics.

    Example:
        >>> results = analyze_repository('/my/project')
        >>> print(results['critical_paths'])
    """
    graph = DependencyGraph(root)
    graph.build()

    return {
        "critical_paths": graph.get_critical_paths(top_n=top_n),
        "hub_files": graph.get_hub_files(),
        "stats": graph.get_stats(),
    }
