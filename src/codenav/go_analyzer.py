"""Go analyzer using tree-sitter for AST-based symbol extraction.

Falls back to regex-based GenericAnalyzer when tree-sitter is not installed.

Example:
    >>> from codenav.go_analyzer import GoAnalyzer
    >>> source = '''
    ... func greet(name string) string {
    ...     return "Hello, " + name
    ... }
    ... '''
    >>> analyzer = GoAnalyzer('example.go', source)
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
    import tree_sitter_go as ts_go
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .code_navigator import GenericAnalyzer, Symbol


class GoAnalyzer:
    """Analyzes Go files using tree-sitter for accurate symbol extraction.

    When tree-sitter is not available, automatically falls back to regex-based
    GenericAnalyzer.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        symbols: Extracted symbols.

    Example:
        >>> source = '''
        ... type User struct {
        ...     Name string
        ... }
        ...
        ... func (u *User) Greet() string {
        ...     return "Hello, " + u.Name
        ... }
        ... '''
        >>> analyzer = GoAnalyzer('user.go', source)
        >>> symbols = analyzer.analyze()
        >>> print([s.name for s in symbols])
        ['User', 'Greet']
    """

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.lines = source.split("\n")
        self.symbols: list[Symbol] = []

    def analyze(self) -> list[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.
        """
        if not TREE_SITTER_AVAILABLE:
            fallback = GenericAnalyzer(self.file_path, self.source, "go")
            return fallback.analyze()

        try:
            parser = Parser(Language(ts_go.language()))
            tree = parser.parse(bytes(self.source, "utf-8"))
            self._visit_node(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            fallback = GenericAnalyzer(self.file_path, self.source, "go")
            return fallback.analyze()

        return self.symbols

    def _visit_node(self, node: "Node") -> None:
        """Recursively visit AST nodes and extract symbols."""
        node_type = node.type

        if node_type == "function_declaration":
            self._extract_function(node)
        elif node_type == "method_declaration":
            self._extract_method(node)
        elif node_type == "type_declaration":
            for child in node.children:
                if child.type == "type_spec":
                    self._extract_type_spec(child)
        elif node_type == "const_declaration":
            self._extract_const(node)

        for child in node.children:
            self._visit_node(child)

    def _get_node_text(self, node: "Node") -> str:
        return self.source[node.start_byte : node.end_byte]

    def _get_child_by_type(self, node: "Node", type_name: str) -> "Node | None":
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _extract_function(self, node: "Node") -> None:
        """Extract a function declaration."""
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Get type parameters (generics)
        type_params = ""
        tp_node = self._get_child_by_type(node, "type_parameter_list")
        if tp_node:
            type_params = self._get_node_text(tp_node)

        # Get parameters
        params = ""
        for child in node.children:
            if child.type == "parameter_list":
                params = self._get_node_text(child)
                break

        # Get return type
        result = ""
        for child in node.children:
            if child.type in (
                "type_identifier",
                "slice_type",
                "pointer_type",
                "qualified_type",
                "map_type",
                "parameter_list",
            ):
                # Skip the first parameter_list (that's the params)
                if child.type == "parameter_list" and child == node.children[2]:
                    continue
                if child.start_byte > (node.children[2].end_byte if len(node.children) > 2 else 0):
                    result = " " + self._get_node_text(child)
                    break

        signature = f"func {name}{type_params}{params}{result}"

        self.symbols.append(
            Symbol(
                name=name,
                type="function",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_method(self, node: "Node") -> None:
        """Extract a method declaration with receiver."""
        # Get method name (field_identifier)
        name_node = self._get_child_by_type(node, "field_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Get receiver type (parent)
        parent = None
        param_lists = [c for c in node.children if c.type == "parameter_list"]
        if param_lists:
            receiver_list = param_lists[0]
            for child in receiver_list.children:
                if child.type == "parameter_declaration":
                    for rc in child.children:
                        if rc.type == "pointer_type":
                            # *User -> User
                            for pt_child in rc.children:
                                if pt_child.type == "type_identifier":
                                    parent = self._get_node_text(pt_child)
                        elif rc.type == "type_identifier":
                            parent = self._get_node_text(rc)

        # Get parameters (second parameter_list)
        params = ""
        if len(param_lists) > 1:
            params = self._get_node_text(param_lists[1])

        receiver_str = f"({self._get_node_text(param_lists[0])})" if param_lists else ""
        signature = f"func {receiver_str} {name}{params}"

        self.symbols.append(
            Symbol(
                name=name,
                type="method",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
                parent=parent,
            )
        )

    def _extract_type_spec(self, node: "Node") -> None:
        """Extract a type specification (struct, interface, or alias)."""
        name_node = self._get_child_by_type(node, "type_identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Determine type kind
        struct_node = self._get_child_by_type(node, "struct_type")
        iface_node = self._get_child_by_type(node, "interface_type")

        if struct_node:
            symbol_type = "struct"
            signature = f"type {name} struct"
        elif iface_node:
            symbol_type = "interface"
            signature = f"type {name} interface"
        else:
            symbol_type = "type"
            # Get the aliased type
            for child in node.children:
                if child.type == "type_identifier" and child != name_node:
                    signature = f"type {name} {self._get_node_text(child)}"
                    break
            else:
                signature = f"type {name}"

        self.symbols.append(
            Symbol(
                name=name,
                type=symbol_type,
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_const(self, node: "Node") -> None:
        """Extract const declarations."""
        for child in node.children:
            if child.type == "const_spec":
                for spec_child in child.children:
                    if spec_child.type == "identifier":
                        name = self._get_node_text(spec_child)
                        self.symbols.append(
                            Symbol(
                                name=name,
                                type="const",
                                file_path=self.file_path,
                                line_start=child.start_point[0] + 1,
                                line_end=child.end_point[0] + 1,
                                signature=self._get_node_text(child).strip()[:100],
                            )
                        )
                        break
