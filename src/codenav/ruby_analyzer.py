"""Ruby analyzer using tree-sitter for AST-based symbol extraction.

Falls back to regex-based GenericAnalyzer when tree-sitter is not installed.

Example:
    >>> from codenav.ruby_analyzer import RubyAnalyzer
    >>> source = '''
    ... def greet(name)
    ...   "Hello, #{name}!"
    ... end
    ... '''
    >>> analyzer = RubyAnalyzer('example.rb', source)
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
    import tree_sitter_ruby as ts_ruby
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .code_navigator import GenericAnalyzer, Symbol


class RubyAnalyzer:
    """Analyzes Ruby files using tree-sitter for accurate symbol extraction.

    When tree-sitter is not available, automatically falls back to regex-based
    GenericAnalyzer.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        symbols: Extracted symbols.

    Example:
        >>> source = '''
        ... class User
        ...   def initialize(name)
        ...     @name = name
        ...   end
        ...
        ...   def greet
        ...     "Hello, #{@name}!"
        ...   end
        ... end
        ... '''
        >>> analyzer = RubyAnalyzer('user.rb', source)
        >>> symbols = analyzer.analyze()
        >>> print([s.name for s in symbols])
        ['User', 'initialize', 'greet']
    """

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.lines = source.split("\n")
        self.symbols: list[Symbol] = []
        self._current_class: str | None = None
        self._current_module: str | None = None

    def analyze(self) -> list[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.
        """
        if not TREE_SITTER_AVAILABLE:
            fallback = GenericAnalyzer(self.file_path, self.source, "ruby")
            return fallback.analyze()

        try:
            parser = Parser(Language(ts_ruby.language()))
            tree = parser.parse(bytes(self.source, "utf-8"))
            self._visit_node(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            fallback = GenericAnalyzer(self.file_path, self.source, "ruby")
            return fallback.analyze()

        return self.symbols

    def _visit_node(self, node: "Node") -> None:
        """Recursively visit AST nodes and extract symbols."""
        node_type = node.type

        if node_type == "method":
            self._extract_method(node)
            return  # Don't visit children (nested defs handled separately)
        elif node_type == "singleton_method":
            self._extract_singleton_method(node)
            return
        elif node_type == "class":
            self._extract_class(node)
            return  # Class body visited inside _extract_class
        elif node_type == "module":
            self._extract_module(node)
            return

        for child in node.children:
            self._visit_node(child)

    def _get_node_text(self, node: "Node") -> str:
        return self.source[node.start_byte : node.end_byte]

    def _get_child_by_type(self, node: "Node", type_name: str) -> "Node | None":
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _extract_method(self, node: "Node") -> None:
        """Extract a method definition."""
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Get parameters
        params = ""
        params_node = self._get_child_by_type(node, "method_parameters")
        if params_node:
            params = self._get_node_text(params_node)

        # Determine type based on context
        parent = self._current_class or self._current_module
        symbol_type = "method" if parent else "function"

        signature = f"def {name}{params}"

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

    def _extract_singleton_method(self, node: "Node") -> None:
        """Extract a singleton (class-level) method like def self.method_name."""
        # Get the method name
        name_node = self._get_child_by_type(node, "identifier")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Get parameters
        params = ""
        params_node = self._get_child_by_type(node, "method_parameters")
        if params_node:
            params = self._get_node_text(params_node)

        parent = self._current_class or self._current_module
        signature = f"def self.{name}{params}"

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

    def _extract_class(self, node: "Node") -> None:
        """Extract a class declaration and visit its body."""
        # Get class name (constant node)
        name_node = self._get_child_by_type(node, "constant")
        if not name_node:
            # Try scope_resolution for nested classes like A::B
            name_node = self._get_child_by_type(node, "scope_resolution")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        # Get superclass
        superclass = ""
        sup_node = self._get_child_by_type(node, "superclass")
        if sup_node:
            for child in sup_node.children:
                if child.type in ("constant", "scope_resolution"):
                    superclass = f" < {self._get_node_text(child)}"
                    break

        signature = f"class {name}{superclass}"

        self.symbols.append(
            Symbol(
                name=name,
                type="class",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

        # Visit body with class context
        old_class = self._current_class
        self._current_class = name
        body = self._get_child_by_type(node, "body_statement")
        if body:
            for child in body.children:
                self._visit_node(child)
        self._current_class = old_class

    def _extract_module(self, node: "Node") -> None:
        """Extract a module declaration and visit its body."""
        name_node = self._get_child_by_type(node, "constant")
        if not name_node:
            return

        name = self._get_node_text(name_node)

        signature = f"module {name}"

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

        # Visit body with module context
        old_module = self._current_module
        self._current_module = name
        body = self._get_child_by_type(node, "body_statement")
        if body:
            for child in body.children:
                self._visit_node(child)
        self._current_module = old_module
