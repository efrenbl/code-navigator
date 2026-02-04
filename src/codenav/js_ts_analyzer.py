"""JavaScript and TypeScript analyzers using tree-sitter for AST-based symbol extraction.

This module provides accurate symbol detection for JavaScript and TypeScript files
using tree-sitter for parsing. Falls back to regex-based GenericAnalyzer when
tree-sitter is not installed.

Example:
    >>> from codenav.js_ts_analyzer import JavaScriptAnalyzer
    >>> source = '''
    ... function greet(name) {
    ...     return `Hello, ${name}!`;
    ... }
    ... '''
    >>> analyzer = JavaScriptAnalyzer('example.js', source)
    >>> symbols = analyzer.analyze()
    >>> print(symbols[0].name)
    'greet'

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install codenav[ast]
"""

import sys
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from tree_sitter import Node

# Try to import tree-sitter
try:
    import tree_sitter_javascript as ts_javascript
    import tree_sitter_typescript as ts_typescript
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .code_navigator import GenericAnalyzer, Symbol


class JavaScriptAnalyzer:
    """Analyzes JavaScript/JSX files using tree-sitter for accurate symbol extraction.

    When tree-sitter is not available, automatically falls back to regex-based
    GenericAnalyzer.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        is_jsx: Whether to parse as JSX.
        symbols: Extracted symbols.

    Example:
        >>> source = '''
        ... const add = (a, b) => a + b;
        ...
        ... class Calculator {
        ...     multiply(x, y) {
        ...         return x * y;
        ...     }
        ... }
        ... '''
        >>> analyzer = JavaScriptAnalyzer('calc.js', source)
        >>> symbols = analyzer.analyze()
        >>> print([s.name for s in symbols])
        ['add', 'Calculator', 'multiply']
    """

    def __init__(self, file_path: str, source: str, is_jsx: bool = False):
        """Initialize the JavaScript analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
            is_jsx: Whether to parse as JSX (default: False).
        """
        self.file_path = file_path
        self.source = source
        self.is_jsx = is_jsx
        self.lines = source.split("\n")
        self.symbols: List[Symbol] = []
        self._current_class: Optional[str] = None

    def analyze(self) -> List[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.
        """
        if not TREE_SITTER_AVAILABLE:
            # Fallback to regex-based analyzer
            fallback = GenericAnalyzer(self.file_path, self.source, "javascript")
            return fallback.analyze()

        try:
            parser = Parser(Language(ts_javascript.language()))
            tree = parser.parse(bytes(self.source, "utf-8"))
            self._visit_node(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            # Fallback to regex on error
            fallback = GenericAnalyzer(self.file_path, self.source, "javascript")
            return fallback.analyze()

        return self.symbols

    def _visit_node(self, node: "Node") -> None:
        """Recursively visit AST nodes and extract symbols.

        Args:
            node: A tree-sitter AST node.
        """
        node_type = node.type

        if node_type == "function_declaration":
            self._extract_function(node)
        elif node_type == "class_declaration":
            self._extract_class(node)
        elif node_type == "method_definition":
            self._extract_method(node)
        elif node_type == "variable_declaration":
            self._extract_variable_declaration(node)
        elif node_type == "lexical_declaration":
            self._extract_variable_declaration(node)
        elif node_type == "export_statement":
            # Process the exported item
            for child in node.children:
                self._visit_node(child)
            return  # Don't visit children again

        # Recursively visit children
        for child in node.children:
            self._visit_node(child)

    def _get_node_text(self, node: "Node") -> str:
        """Get the text content of a node.

        Args:
            node: A tree-sitter AST node.

        Returns:
            The text content of the node.
        """
        return self.source[node.start_byte : node.end_byte]

    def _get_identifier_name(self, node: "Node") -> Optional[str]:
        """Get the identifier name from a node.

        Args:
            node: A tree-sitter AST node.

        Returns:
            The identifier name, or None if not found.
        """
        for child in node.children:
            if child.type == "identifier":
                return self._get_node_text(child)
        return None

    def _extract_function(self, node: "Node") -> None:
        """Extract a function declaration.

        Args:
            node: A function_declaration node.
        """
        name = self._get_identifier_name(node)
        if not name:
            return

        # Check if async
        is_async = any(child.type == "async" for child in node.children)

        # Get parameters
        params = ""
        for child in node.children:
            if child.type == "formal_parameters":
                params = self._get_node_text(child)
                break

        prefix = "async " if is_async else ""
        signature = f"{prefix}function {name}{params}"

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

    def _extract_class(self, node: "Node") -> None:
        """Extract a class declaration and its methods.

        Args:
            node: A class_declaration node.
        """
        name = self._get_identifier_name(node)
        if not name:
            return

        # Get heritage (extends)
        heritage = ""
        for child in node.children:
            if child.type == "class_heritage":
                heritage_text = self._get_node_text(child)
                heritage = f" {heritage_text}"
                break

        signature = f"class {name}{heritage}"

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

        # Visit class body for methods
        old_class = self._current_class
        self._current_class = name
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    self._visit_node(member)
        self._current_class = old_class

    def _extract_method(self, node: "Node") -> None:
        """Extract a method definition.

        Args:
            node: A method_definition node.
        """
        # Get method name
        name = None
        for child in node.children:
            if child.type == "property_identifier":
                name = self._get_node_text(child)
                break

        if not name:
            return

        # Check for async/static
        is_async = any(child.type == "async" for child in node.children)
        is_static = any(child.type == "static" for child in node.children)

        # Get parameters
        params = ""
        for child in node.children:
            if child.type == "formal_parameters":
                params = self._get_node_text(child)
                break

        prefix = ""
        if is_static:
            prefix += "static "
        if is_async:
            prefix += "async "

        signature = f"{prefix}{name}{params}"

        self.symbols.append(
            Symbol(
                name=name,
                type="method",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
                parent=self._current_class,
            )
        )

    def _extract_variable_declaration(self, node: "Node") -> None:
        """Extract arrow functions and function expressions from variable declarations.

        Args:
            node: A variable_declaration or lexical_declaration node.
        """
        for child in node.children:
            if child.type == "variable_declarator":
                self._extract_variable_declarator(child)

    def _extract_variable_declarator(self, node: "Node") -> None:
        """Extract a variable declarator that may contain an arrow function.

        Args:
            node: A variable_declarator node.
        """
        name = None
        value = None

        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child)
            elif child.type in ("arrow_function", "function_expression"):
                value = child

        if not name or not value:
            return

        # Check if it's an arrow function or function expression
        is_async = any(c.type == "async" for c in value.children)

        # Get parameters
        params = ""
        for child in value.children:
            if child.type == "formal_parameters":
                params = self._get_node_text(child)
                break
            elif child.type == "identifier":
                # Single param arrow function: x => x + 1
                params = f"({self._get_node_text(child)})"
                break

        prefix = "async " if is_async else ""
        signature = f"const {name} = {prefix}{params} =>"

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


class TypeScriptAnalyzer(JavaScriptAnalyzer):
    """Analyzes TypeScript/TSX files using tree-sitter for accurate symbol extraction.

    Extends JavaScriptAnalyzer with TypeScript-specific constructs like interfaces,
    type aliases, and enums.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        is_tsx: Whether to parse as TSX.
        symbols: Extracted symbols.

    Example:
        >>> source = '''
        ... interface User {
        ...     name: string;
        ...     age: number;
        ... }
        ...
        ... type Status = 'active' | 'inactive';
        ...
        ... enum Color {
        ...     Red,
        ...     Green,
        ...     Blue
        ... }
        ... '''
        >>> analyzer = TypeScriptAnalyzer('types.ts', source)
        >>> symbols = analyzer.analyze()
        >>> print([s.name for s in symbols])
        ['User', 'Status', 'Color']
    """

    def __init__(self, file_path: str, source: str, is_tsx: bool = False):
        """Initialize the TypeScript analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
            is_tsx: Whether to parse as TSX (default: False).
        """
        super().__init__(file_path, source, is_jsx=is_tsx)
        self.is_tsx = is_tsx

    def analyze(self) -> List[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.
        """
        if not TREE_SITTER_AVAILABLE:
            # Fallback to regex-based analyzer
            fallback = GenericAnalyzer(self.file_path, self.source, "typescript")
            return fallback.analyze()

        try:
            # Use TSX parser for .tsx files, otherwise use regular TypeScript
            if self.is_tsx:
                language = Language(ts_typescript.language_tsx())
            else:
                language = Language(ts_typescript.language_typescript())

            parser = Parser(language)
            tree = parser.parse(bytes(self.source, "utf-8"))
            self._visit_node(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            # Fallback to regex on error
            fallback = GenericAnalyzer(self.file_path, self.source, "typescript")
            return fallback.analyze()

        return self.symbols

    def _visit_node(self, node: "Node") -> None:
        """Recursively visit AST nodes and extract symbols.

        Extends parent class to handle TypeScript-specific nodes.

        Args:
            node: A tree-sitter AST node.
        """
        node_type = node.type

        # TypeScript-specific node types
        if node_type == "interface_declaration":
            self._extract_interface(node)
        elif node_type == "type_alias_declaration":
            self._extract_type_alias(node)
        elif node_type == "enum_declaration":
            self._extract_enum(node)
        elif node_type == "ambient_declaration":
            # Process declare statements
            for child in node.children:
                self._visit_node(child)
            return
        else:
            # Let parent class handle common JS constructs
            super()._visit_node(node)
            return

        # Recursively visit children for TS-specific nodes
        for child in node.children:
            self._visit_node(child)

    def _extract_interface(self, node: "Node") -> None:
        """Extract an interface declaration.

        Args:
            node: An interface_declaration node.
        """
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child)
                break

        if not name:
            return

        # Get extends clause if any
        extends = ""
        for child in node.children:
            if child.type == "extends_type_clause":
                extends_text = self._get_node_text(child)
                extends = f" {extends_text}"
                break

        # Get type parameters if any
        type_params = ""
        for child in node.children:
            if child.type == "type_parameters":
                type_params = self._get_node_text(child)
                break

        signature = f"interface {name}{type_params}{extends}"

        self.symbols.append(
            Symbol(
                name=name,
                type="interface",
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100],
            )
        )

    def _extract_type_alias(self, node: "Node") -> None:
        """Extract a type alias declaration.

        Args:
            node: A type_alias_declaration node.
        """
        name = None
        for child in node.children:
            if child.type == "type_identifier":
                name = self._get_node_text(child)
                break

        if not name:
            return

        # Get type parameters if any
        type_params = ""
        for child in node.children:
            if child.type == "type_parameters":
                type_params = self._get_node_text(child)
                break

        # Get the type value (simplified, first 50 chars)
        type_value = ""
        for i, child in enumerate(node.children):
            if child.type == "=":
                # Next child should be the type
                remaining = node.children[i + 1 :]
                if remaining:
                    type_value = self._get_node_text(remaining[0])[:50]
                break

        signature = f"type {name}{type_params} = {type_value}"

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

    def _extract_enum(self, node: "Node") -> None:
        """Extract an enum declaration.

        Args:
            node: An enum_declaration node.
        """
        name = None
        for child in node.children:
            if child.type == "identifier":
                name = self._get_node_text(child)
                break

        if not name:
            return

        # Check for const enum
        is_const = any(child.type == "const" for child in node.children)

        prefix = "const " if is_const else ""
        signature = f"{prefix}enum {name}"

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
