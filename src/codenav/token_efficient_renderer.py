#!/usr/bin/env python3
"""Token-Efficient Renderer - Compact codebase visualization for LLMs.

This module generates ASCII tree representations of codebases with inline
"micro-metadata" that packs maximum information into minimum tokens.

Key Innovation: Instead of verbose JSON, each file line contains:
    ├── api_client.py [C:Auth M:login,logout] (Hub:3←)

This conveys: file name, main class, key methods, and hub status
in ~50 characters vs ~500+ characters of equivalent JSON.

Token Savings: Typically 60-80% reduction compared to JSON output.

Example:
    >>> renderer = TokenEfficientRenderer(code_map)
    >>> print(renderer.render_skeleton_tree())

    my-project/
    ├── src/
    │   ├── api/
    │   │   ├── client.py [C:APIClient M:get,post,delete] (Hub:5←)
    │   │   └── routes.py [F:handle_request,validate] (3←)
    │   └── core/
    │       ├── config.py [C:Config M:load,save] (Hub:8←)
    │       └── utils.py [F:helper,format_date]
    └── tests/
        └── test_api.py [F:test_client,test_routes]

    ═══ Summary ═══
    28 files · 142 symbols · 12 hubs
    Top Hubs: config.py(8←), client.py(5←), utils.py(4←)
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Default limits for token-efficient rendering (configurable)
DEFAULT_MAX_CLASSES = 2
DEFAULT_MAX_METHODS_PER_CLASS = 3
DEFAULT_MAX_FUNCTIONS = 3


class HubLevel(Enum):
    """Hub importance levels based on import count."""

    NONE = 0  # 0-1 importers
    LOW = 1  # 2 importers
    MEDIUM = 2  # 3-4 importers
    HIGH = 3  # 5+ importers
    CRITICAL = 4  # 8+ importers


@dataclass
class FileMicroMeta:
    """Compact metadata for a single file.

    Attributes:
        path: Relative file path.
        classes: List of class names.
        functions: List of function names.
        methods: Dict of class -> method names.
        imports_count: Number of files this imports.
        importers_count: Number of files importing this.
        lines: Total lines of code.
        has_tests: Whether file appears to be a test file.
    """

    path: str
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    methods: Dict[str, List[str]] = field(default_factory=dict)
    imports_count: int = 0
    importers_count: int = 0
    lines: int = 0
    has_tests: bool = False

    @property
    def hub_level(self) -> HubLevel:
        """Determine hub level from importer count."""
        if self.importers_count >= 8:
            return HubLevel.CRITICAL
        elif self.importers_count >= 5:
            return HubLevel.HIGH
        elif self.importers_count >= 3:
            return HubLevel.MEDIUM
        elif self.importers_count >= 2:
            return HubLevel.LOW
        return HubLevel.NONE

    def format_micro(
        self,
        max_width: int = 60,
        max_classes: int = DEFAULT_MAX_CLASSES,
        max_methods: int = DEFAULT_MAX_METHODS_PER_CLASS,
        max_functions: int = DEFAULT_MAX_FUNCTIONS,
    ) -> str:
        """Format as compact micro-metadata string.

        Format: [C:ClassName M:method1,method2] or [F:func1,func2]

        Args:
            max_width: Maximum width for the metadata portion.
            max_classes: Maximum number of classes to show.
            max_methods: Maximum methods per class to show.
            max_functions: Maximum standalone functions to show.

        Returns:
            Compact metadata string.
        """
        parts = []

        # Classes with their methods
        if self.classes:
            for cls in self.classes[:max_classes]:
                methods = self.methods.get(cls, [])[:max_methods]
                if methods:
                    parts.append(f"C:{cls} M:{','.join(methods)}")
                else:
                    parts.append(f"C:{cls}")

        # Standalone functions (not methods)
        standalone_funcs = [f for f in self.functions if not f.startswith("_")][:max_functions]
        if standalone_funcs and not self.classes:
            parts.append(f"F:{','.join(standalone_funcs)}")
        elif standalone_funcs and len(parts) < 2:
            # Add some functions if we have room
            parts.append(f"F:{','.join(standalone_funcs[:2])}")

        # Hub indicator
        hub_str = ""
        if self.importers_count >= 2:
            hub_str = f" ({self.importers_count}←)"

        if not parts:
            return hub_str.strip()

        meta = f"[{' '.join(parts)}]"

        # Truncate if too long
        if len(meta) + len(hub_str) > max_width:
            available = max_width - len(hub_str) - 5  # "[...]"
            if available > 10:
                meta = f"[{meta[1:available]}...]"
            else:
                meta = "[...]"

        return f"{meta}{hub_str}"


@dataclass
class TreeNode:
    """Node in the file tree structure."""

    name: str
    is_file: bool = False
    meta: Optional[FileMicroMeta] = None
    children: Dict[str, "TreeNode"] = field(default_factory=dict)

    def get_stats(self) -> Tuple[int, int, int]:
        """Get recursive stats: (file_count, symbol_count, hub_count)."""
        if self.is_file:
            symbols = len(self.meta.classes) + len(self.meta.functions) if self.meta else 0
            is_hub = 1 if self.meta and self.meta.importers_count >= 3 else 0
            return (1, symbols, is_hub)

        files, symbols, hubs = 0, 0, 0
        for child in self.children.values():
            f, s, h = child.get_stats()
            files += f
            symbols += s
            hubs += h
        return (files, symbols, hubs)


class TokenEfficientRenderer:
    """Renders codebase structure with minimal token usage.

    This class takes a code map (from CodeNavigator) and renders it as a
    compact ASCII tree with inline micro-metadata. The goal is to give
    LLMs maximum context with minimum tokens.

    Attributes:
        code_map: The loaded code map dictionary.
        files: Dict of file path -> FileMicroMeta.
        tree: Root TreeNode of the file structure.
        hub_threshold: Minimum importers to be considered a hub.

    Example:
        >>> # From code map file
        >>> renderer = TokenEfficientRenderer.from_file('.codenav.json')
        >>> print(renderer.render_skeleton_tree())

        >>> # From code map dict
        >>> renderer = TokenEfficientRenderer(code_map_dict)
        >>> output = renderer.render_skeleton_tree(max_depth=3)

        >>> # Compare token usage
        >>> stats = renderer.get_token_stats()
        >>> print(f"Saved {stats['savings_percent']:.1f}% tokens")
    """

    # Tree drawing characters
    PIPE = "│"
    ELBOW = "└──"
    TEE = "├──"
    BLANK = "    "
    PIPE_PREFIX = "│   "

    def __init__(
        self,
        code_map: Dict[str, Any],
        hub_threshold: int = 3,
        dependency_graph: Any = None,  # Optional DependencyGraph
        max_classes: int = DEFAULT_MAX_CLASSES,
        max_methods: int = DEFAULT_MAX_METHODS_PER_CLASS,
        max_functions: int = DEFAULT_MAX_FUNCTIONS,
        root_path: str = None,
    ):
        """Initialize the renderer.

        Args:
            code_map: Code map dictionary from CodeNavigator.
            hub_threshold: Min importers to be a hub (default: 3).
            dependency_graph: Optional DependencyGraph for hub detection.
            max_classes: Max classes to show per file (default: 2).
            max_methods: Max methods per class to show (default: 3).
            max_functions: Max standalone functions to show (default: 3).
            root_path: Root path for the codebase (optional).
        """
        self.code_map = code_map
        self.hub_threshold = hub_threshold
        self.dependency_graph = dependency_graph
        self.max_classes = max_classes
        self.max_methods = max_methods
        self.max_functions = max_functions
        self.root_path = root_path
        self.files: Dict[str, FileMicroMeta] = {}
        self.tree: Optional[TreeNode] = None

        self._parse_code_map()
        self._build_tree()

        if dependency_graph:
            self._apply_dependency_data()

    @classmethod
    def from_file(cls, path: str, **kwargs) -> "TokenEfficientRenderer":
        """Create renderer from a code map JSON file.

        Args:
            path: Path to .codenav.json file.
            **kwargs: Additional arguments for __init__.

        Returns:
            Initialized TokenEfficientRenderer.
        """
        with open(path, encoding="utf-8") as f:
            code_map = json.load(f)
        return cls(code_map, **kwargs)

    def _parse_code_map(self) -> None:
        """Parse code map into FileMicroMeta objects."""
        files_data = self.code_map.get("files", {})

        for file_path, file_info in files_data.items():
            symbols = file_info.get("symbols", [])

            classes = []
            functions = []
            methods = defaultdict(list)

            for sym in symbols:
                sym_type = sym.get("type", "")
                sym_name = sym.get("name", "")
                parent = sym.get("parent")

                if sym_type == "class":
                    classes.append(sym_name)
                elif sym_type == "function":
                    functions.append(sym_name)
                elif sym_type == "method" and parent:
                    methods[parent].append(sym_name)

            # Calculate approximate lines
            lines = 0
            for sym in symbols:
                sym_lines = sym.get("lines", [0, 0])
                if isinstance(sym_lines, list) and len(sym_lines) >= 2:
                    lines = max(lines, sym_lines[1])

            # Detect test files
            has_tests = (
                "test" in file_path.lower()
                or file_path.startswith("tests/")
                or any(f.startswith("test_") for f in functions)
            )

            self.files[file_path] = FileMicroMeta(
                path=file_path,
                classes=classes,
                functions=functions,
                methods=dict(methods),
                lines=lines,
                has_tests=has_tests,
            )

    def _apply_dependency_data(self) -> None:
        """Apply dependency graph data to file metadata."""
        if not self.dependency_graph:
            return

        for path, meta in self.files.items():
            if path in self.dependency_graph.nodes:
                node = self.dependency_graph.nodes[path]
                meta.imports_count = node.out_degree
                meta.importers_count = node.in_degree

    def _build_tree(self) -> None:
        """Build tree structure from file paths."""
        self.tree = TreeNode(name="", is_file=False)

        for file_path, meta in self.files.items():
            parts = Path(file_path).parts
            current = self.tree

            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # File node
                    current.children[part] = TreeNode(
                        name=part,
                        is_file=True,
                        meta=meta,
                    )
                else:
                    # Directory node
                    if part not in current.children:
                        current.children[part] = TreeNode(name=part)
                    current = current.children[part]

    def render_skeleton_tree(
        self,
        max_depth: int = 0,
        show_meta: bool = True,
        show_summary: bool = True,
        collapse_threshold: int = 10,
        project_name: str = None,
    ) -> str:
        """Render the codebase as a compact ASCII tree.

        Args:
            max_depth: Maximum directory depth (0 = unlimited).
            show_meta: Include micro-metadata on each file.
            show_summary: Include summary section at end.
            collapse_threshold: Collapse dirs with more files than this.
            project_name: Override project name in output.

        Returns:
            Formatted ASCII tree string.

        Example output:
            my-project/
            ├── src/
            │   ├── api/
            │   │   ├── client.py [C:APIClient M:get,post] (5←)
            │   │   └── routes.py [F:handle,validate] (3←)
            │   └── core/
            │       └── config.py [C:Config M:load] (Hub:8←)
            └── tests/
                └── test_api.py [F:test_client]

            ═══ Summary ═══
            28 files · 142 symbols · 12 hubs
        """
        lines = []

        # Header
        name = project_name or self.code_map.get("root", "project").split("/")[-1]
        lines.append(f"{name}/")

        # Render tree
        self._render_node(
            self.tree,
            lines,
            prefix="",
            is_last=True,
            depth=0,
            max_depth=max_depth,
            show_meta=show_meta,
            collapse_threshold=collapse_threshold,
        )

        # Summary
        if show_summary:
            lines.append("")
            lines.append("═══ Summary ═══")
            stats = self._get_summary_stats()
            lines.append(
                f"{stats['files']} files · {stats['symbols']} symbols · {stats['hubs']} hubs"
            )

            if stats["top_hubs"]:
                hub_strs = [f"{h[0]}({h[1]}←)" for h in stats["top_hubs"][:5]]
                lines.append(f"Top Hubs: {', '.join(hub_strs)}")

        return "\n".join(lines)

    def _render_node(
        self,
        node: TreeNode,
        lines: List[str],
        prefix: str,
        is_last: bool,
        depth: int,
        max_depth: int,
        show_meta: bool,
        collapse_threshold: int,
    ) -> None:
        """Recursively render a tree node."""
        # Check depth limit
        if max_depth > 0 and depth > max_depth:
            return

        # Separate directories and files
        dirs = []
        files = []
        for name, child in sorted(node.children.items()):
            if child.is_file:
                files.append((name, child))
            else:
                dirs.append((name, child))

        all_items = dirs + files

        for i, (name, child) in enumerate(all_items):
            is_last_item = i == len(all_items) - 1
            connector = self.ELBOW if is_last_item else self.TEE
            new_prefix = prefix + (self.BLANK if is_last_item else self.PIPE_PREFIX)

            if child.is_file:
                # File with micro-metadata
                line = f"{prefix}{connector} {name}"
                if show_meta and child.meta:
                    meta_str = child.meta.format_micro(
                        max_classes=self.max_classes,
                        max_methods=self.max_methods,
                        max_functions=self.max_functions,
                    )
                    if meta_str:
                        line += f" {meta_str}"
                lines.append(line)
            else:
                # Directory
                file_count, symbol_count, hub_count = child.get_stats()

                # Check for single-child directory flattening
                flat_path = name
                current = child
                while len(current.children) == 1:
                    only_child_name = list(current.children.keys())[0]
                    only_child = current.children[only_child_name]
                    if only_child.is_file:
                        break
                    flat_path = f"{flat_path}/{only_child_name}"
                    current = only_child

                # Collapse large directories
                if file_count > collapse_threshold and max_depth > 0 and depth >= max_depth - 1:
                    dir_stats = f"({file_count} files, {symbol_count} symbols)"
                    lines.append(f"{prefix}{connector} {flat_path}/ {dir_stats}")
                    continue

                # Directory with stats hint
                dir_line = f"{prefix}{connector} {flat_path}/"
                if file_count > 5:
                    dir_line += f" ({file_count} files)"
                lines.append(dir_line)

                # Recurse
                self._render_node(
                    current,
                    lines,
                    new_prefix,
                    is_last_item,
                    depth + 1,
                    max_depth,
                    show_meta,
                    collapse_threshold,
                )

    def _get_summary_stats(self) -> Dict[str, Any]:
        """Calculate summary statistics."""
        total_files = len(self.files)
        total_symbols = sum(len(m.classes) + len(m.functions) for m in self.files.values())

        # Find hubs
        hubs = [
            (Path(m.path).name, m.importers_count)
            for m in self.files.values()
            if m.importers_count >= self.hub_threshold
        ]
        hubs.sort(key=lambda x: x[1], reverse=True)

        return {
            "files": total_files,
            "symbols": total_symbols,
            "hubs": len(hubs),
            "top_hubs": hubs[:10],
        }

    def render_dependency_flow(
        self,
        top_n: int = 15,
        show_chains: bool = True,
    ) -> str:
        """Render dependency flow visualization.

        Similar to REPO_B's depgraph.go but more compact.

        Args:
            top_n: Number of top dependencies to show.
            show_chains: Show dependency chains (A → B → C).

        Returns:
            Formatted dependency flow string.
        """
        if not self.dependency_graph:
            return "⚠ No dependency graph available. Initialize with dependency_graph parameter."

        lines = []
        lines.append("═══ Dependency Flow ═══")
        lines.append("")

        # Group files by directory
        by_dir = defaultdict(list)
        for path, meta in self.files.items():
            dir_name = str(Path(path).parent)
            if dir_name == ".":
                dir_name = "root"
            by_dir[dir_name].append((path, meta))

        # Show each directory's dependencies
        for dir_name in sorted(by_dir.keys()):
            dir_files = by_dir[dir_name]
            has_deps = any(m.imports_count > 0 for _, m in dir_files)
            if not has_deps:
                continue

            lines.append(f"┌─ {dir_name}/")

            for path, meta in sorted(dir_files, key=lambda x: x[1].importers_count, reverse=True):
                if meta.imports_count == 0 and meta.importers_count == 0:
                    continue

                name = Path(path).stem

                # Show import relationships
                if self.dependency_graph and path in self.dependency_graph.nodes:
                    node = self.dependency_graph.nodes[path]
                    imports = node.resolved_imports[:3]  # Max 3

                    if imports:
                        import_names = [Path(i).stem for i in imports]
                        arrow = "───▶"
                        if meta.importers_count >= 3:
                            arrow = "═══▶"  # Hub gets bold arrow

                        if len(imports) == 1:
                            lines.append(f"│  {name} {arrow} {import_names[0]}")
                        else:
                            lines.append(f"│  {name} {arrow} {', '.join(import_names)}")
                            if len(node.resolved_imports) > 3:
                                lines.append(f"│       +{len(node.resolved_imports) - 3} more")

            lines.append("└─")
            lines.append("")

        # Hub summary
        hubs = self._get_summary_stats()["top_hubs"]
        if hubs:
            lines.append("─" * 40)
            hub_strs = [f"{h[0]}({h[1]}←)" for h in hubs[:6]]
            lines.append(f"HUBS: {', '.join(hub_strs)}")

        return "\n".join(lines)

    def render_compact_index(
        self,
        include_signatures: bool = False,
        group_by: str = "file",  # "file", "type", "directory"
    ) -> str:
        """Render ultra-compact symbol index.

        Even more compact than the tree - just lists key symbols.

        Args:
            include_signatures: Include function signatures.
            group_by: How to group symbols.

        Returns:
            Compact symbol index string.
        """
        lines = []

        if group_by == "type":
            # Group by symbol type
            classes = []
            functions = []

            for path, meta in self.files.items():
                short_path = Path(path).stem
                for cls in meta.classes[:self.max_classes]:
                    methods = meta.methods.get(cls, [])[:self.max_methods]
                    if methods:
                        classes.append(f"{short_path}.{cls}({','.join(methods)})")
                    else:
                        classes.append(f"{short_path}.{cls}")

                for func in meta.functions[:self.max_functions]:
                    if not func.startswith("_"):
                        functions.append(f"{short_path}.{func}")

            if classes:
                lines.append(f"Classes: {', '.join(classes[:20])}")
                if len(classes) > 20:
                    lines.append(f"  +{len(classes) - 20} more classes")

            if functions:
                lines.append(f"Functions: {', '.join(functions[:30])}")
                if len(functions) > 30:
                    lines.append(f"  +{len(functions) - 30} more functions")

        else:  # group_by == "file" or "directory"
            for path in sorted(self.files.keys()):
                meta = self.files[path]
                if not meta.classes and not meta.functions:
                    continue

                short = Path(path).stem
                symbols = []

                for cls in meta.classes[:self.max_classes]:
                    methods = meta.methods.get(cls, [])[:self.max_methods]
                    if methods:
                        symbols.append(f"C:{cls}({','.join(methods)})")
                    else:
                        symbols.append(f"C:{cls}")

                for func in meta.functions[:self.max_functions]:
                    if not func.startswith("_"):
                        symbols.append(f"F:{func}")

                if symbols:
                    lines.append(f"{short}: {' '.join(symbols)}")

        return "\n".join(lines)

    def get_token_stats(self) -> Dict[str, Any]:
        """Compare token usage between JSON and tree output.

        Returns:
            Dict with token comparison statistics.
        """
        import json

        # Original JSON size
        json_output = json.dumps(self.code_map, indent=2)
        json_chars = len(json_output)

        # Compact JSON
        compact_json = json.dumps(self.code_map, separators=(",", ":"))
        compact_chars = len(compact_json)

        # Tree output
        tree_output = self.render_skeleton_tree()
        tree_chars = len(tree_output)

        # Compact index
        index_output = self.render_compact_index()
        index_chars = len(index_output)

        # Approximate token counts (rough: 4 chars ≈ 1 token)
        json_tokens = json_chars // 4
        compact_tokens = compact_chars // 4
        tree_tokens = tree_chars // 4
        index_tokens = index_chars // 4

        return {
            "json_chars": json_chars,
            "json_tokens_approx": json_tokens,
            "compact_json_chars": compact_chars,
            "compact_json_tokens_approx": compact_tokens,
            "tree_chars": tree_chars,
            "tree_tokens_approx": tree_tokens,
            "index_chars": index_chars,
            "index_tokens_approx": index_tokens,
            "savings_vs_json": json_chars - tree_chars,
            "savings_percent": (
                ((json_chars - tree_chars) / json_chars) * 100 if json_chars > 0 else 0
            ),
            "savings_vs_compact": compact_chars - tree_chars,
            "compact_savings_percent": (
                ((compact_chars - tree_chars) / compact_chars) * 100 if compact_chars > 0 else 0
            ),
        }


def render_skeleton_tree(
    file_nodes: Union[Dict[str, Any], str],
    max_depth: int = 0,
    show_meta: bool = True,
    project_name: str = None,
) -> str:
    """Convenience function to render a skeleton tree.

    Args:
        file_nodes: Either a code map dict or path to .codenav.json.
        max_depth: Maximum directory depth (0 = unlimited).
        show_meta: Include micro-metadata.
        project_name: Override project name.

    Returns:
        Formatted ASCII tree string.

    Example:
        >>> tree = render_skeleton_tree('.codenav.json')
        >>> print(tree)
    """
    if isinstance(file_nodes, str):
        renderer = TokenEfficientRenderer.from_file(file_nodes)
    else:
        renderer = TokenEfficientRenderer(file_nodes)

    return renderer.render_skeleton_tree(
        max_depth=max_depth,
        show_meta=show_meta,
        project_name=project_name,
    )
