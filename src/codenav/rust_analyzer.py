"""Rust analyzer using tree-sitter for AST-based symbol extraction.

Falls back to regex-based GenericAnalyzer when tree-sitter is not installed.

Example:
    >>> from codenav.rust_analyzer import RustAnalyzer
    >>> source = '''
    ... pub fn greet(name: &str) -> String {
    ...     format!("Hello, {}!", name)
    ... }
    ... '''
    >>> analyzer = RustAnalyzer('example.rs', source)
    >>> symbols = analyzer.analyze()
    >>> print(symbols[0].name)
    'greet'

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install code-navigator[ast]
"""

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

try:
    import tree_sitter_rust as ts_rust
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .code_navigator import GenericAnalyzer, Symbol


class RustAnalyzer:
    """Analyzes Rust files using tree-sitter for accurate symbol extraction.

    When tree-sitter is not available, automatically falls back to regex-based
    GenericAnalyzer.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        symbols: Extracted symbols.

    Example:
        >>> source = '''
        ... pub struct User {
        ...     name: String,
        ... }
        ...
        ... impl User {
        ...     pub fn new(name: String) -> Self {
        ...         User { name }
        ...     }
        ... }
        ... '''
        >>> analyzer = RustAnalyzer('user.rs', source)
        >>> symbols = analyzer.analyze()
        >>> print([s.name for s in symbols])
        ['User', 'User', 'new']
    """

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.lines = source.split("\n")
        self.symbols: list[Symbol] = []
        self._current_impl: str | None = None
        self._current_trait_impl: str | None = None

    def analyze(self) -> list[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.
        """
        if not TREE_SITTER_AVAILABLE:
            fallback = GenericAnalyzer(self.file_path, self.source, "rust")
            return fallback.analyze()

        try:
            parser = Parser(Language(ts_rust.language()))
            tree = parser.parse(bytes(self.source, "utf-8"))
            self._visit_node(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            fallback = GenericAnalyzer(self.file_path, self.source, "rust")
            return fallback.analyze()

        return self.symbols

    def _visit_node(self, node: "Node") -> None:
        """Recursively visit AST nodes and extract symbols."""
        node_type = node.type

        if node_type == "function_item":
            self._extract_function(node)
        elif node_type == "struct_item":
            self._extract_struct(node)
        elif node_type == "enum_item":
            self._extract_enum(node)
        elif node_type == "trait_item":
            self._extract_trait(node)
        elif node_type == "impl_item":
            self._extract_impl(node)
            return  # Body visited inside _extract_impl
        elif node_type == "type_item":
            self._extract_type_alias(node)
        elif node_type == "const_item":
            self._extract_const(node)
        elif node_type == "mod_item":
            self._extract_mod(node)
            return  # Body visited inside _extract_mod

        for child in node.children:
            self._visit_node(child)

    def _get_node_text(self, node: "Node") -> str:
        return self.source[node.start_byte : node.end_byte]

    def _get_child_by_type(self, node: "Node", type_name: str) -> "Node | None":
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _has_visibility(self, node: "Node") -> bool:
        return self._get_child_by_type(node, "visibility_modifier") is not None

    def _is_async(self, node: "Node") -> bool:
        mods = self._get_child_by_type(node, "function_modifiers")
        if mods:
            for child in mods.children:
                if child.type == "async":
                    return True
        return False

    def _get_type_params(self, node: "Node") -> str:
        tp = self._get_child_by_type(node, "type_parameters")
        if tp:
            return self._get_node_text(tp)
        return ""

    def _extract_function(self, node: "Node") -> None:
        """Extract a function/method item."""
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Visibility
        pub = "pub " if self._has_visibility(node) else ""
        async_prefix = "async " if self._is_async(node) else ""
        type_params = self._get_type_params(node)

        # Parameters
        params = ""
        params_node = self._get_child_by_type(node, "parameters")
        if params_node:
            params = self._get_node_text(params_node)

        # Return type
        ret = ""
        for i, child in enumerate(node.children):
            if child.type == "->":
                remaining = [c for c in node.children[i + 1 :] if c.type != "block"]
                if remaining:
                    ret = " -> " + self._get_node_text(remaining[0])
                break

        # Determine type
        parent = self._current_impl
        symbol_type = "method" if parent else "function"

        signature = f"{pub}{async_prefix}fn {name}{type_params}{params}{ret}"

        self.symbols.append(
            Symbol(
                name=name,
                type=symbol_type,
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
                parent=parent,
            )
        )

    def _extract_struct(self, node: "Node") -> None:
        """Extract a struct definition."""
        name_node = self._get_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        pub = "pub " if self._has_visibility(node) else ""
        type_params = self._get_type_params(node)
        signature = f"{pub}struct {name}{type_params}"

        self.symbols.append(
            Symbol(
                name=name,
                type="struct",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_enum(self, node: "Node") -> None:
        """Extract an enum definition."""
        name_node = self._get_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        pub = "pub " if self._has_visibility(node) else ""
        signature = f"{pub}enum {name}"

        self.symbols.append(
            Symbol(
                name=name,
                type="enum",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_trait(self, node: "Node") -> None:
        """Extract a trait definition."""
        name_node = self._get_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        pub = "pub " if self._has_visibility(node) else ""
        type_params = self._get_type_params(node)
        signature = f"{pub}trait {name}{type_params}"

        self.symbols.append(
            Symbol(
                name=name,
                type="trait",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_impl(self, node: "Node") -> None:
        """Extract an impl block and visit its methods."""
        # Get the type being implemented
        # For "impl Type", get Type
        # For "impl Trait for Type", get Type (the target)
        impl_type = None
        trait_name = None

        type_ids = [c for c in node.children if c.type == "type_identifier"]
        scoped_ids = [c for c in node.children if c.type == "scoped_type_identifier"]
        has_for = any(c.type == "for" for c in node.children)

        if has_for:
            # impl Trait for Type
            if len(type_ids) >= 1:
                impl_type = self._get_node_text(type_ids[-1])
            if scoped_ids:
                trait_name = self._get_node_text(scoped_ids[0])
            elif len(type_ids) >= 2:
                trait_name = self._get_node_text(type_ids[0])
        else:
            # impl Type
            if type_ids:
                impl_type = self._get_node_text(type_ids[0])

        if impl_type:
            type_params = self._get_type_params(node)
            if trait_name:
                sig = f"impl {trait_name} for {impl_type}{type_params}"
            else:
                sig = f"impl {impl_type}{type_params}"

            self.symbols.append(
                Symbol(
                    name=impl_type,
                    type="impl",
                    file_path=self.file_path,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    signature=sig[:100],
                )
            )

        # Visit body with impl context
        old_impl = self._current_impl
        self._current_impl = impl_type
        decl_list = self._get_child_by_type(node, "declaration_list")
        if decl_list:
            for child in decl_list.children:
                self._visit_node(child)
        self._current_impl = old_impl

    def _extract_type_alias(self, node: "Node") -> None:
        """Extract a type alias."""
        name_node = self._get_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        pub = "pub " if self._has_visibility(node) else ""
        type_params = self._get_type_params(node)
        signature = f"{pub}type {name}{type_params}"

        self.symbols.append(
            Symbol(
                name=name,
                type="type",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_const(self, node: "Node") -> None:
        """Extract a const item."""
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        pub = "pub " if self._has_visibility(node) else ""
        signature = f"{pub}const {name}"

        self.symbols.append(
            Symbol(
                name=name,
                type="const",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_mod(self, node: "Node") -> None:
        """Extract a module declaration and visit its body."""
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)
        signature = f"mod {name}"

        self.symbols.append(
            Symbol(
                name=name,
                type="module",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

        # Visit body
        decl_list = self._get_child_by_type(node, "declaration_list")
        if decl_list:
            for child in decl_list.children:
                self._visit_node(child)
