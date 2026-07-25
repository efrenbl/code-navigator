#!/usr/bin/env python3
"""Code Mapper - Generates a structural map/graph of a codebase for token-efficient navigation.

This module creates a lightweight index of functions, classes, methods, and their
relationships within a codebase. The generated index can be used for quick symbol
lookup without reading entire files.

Example:
    Command line usage:
        $ codenav scan /path/to/project -o .codenav.json

    Python API usage:
        >>> mapper = CodeNavigator('/path/to/project')
        >>> code_map = mapper.scan()
        >>> print(code_map['stats'])
        {'files_processed': 142, 'symbols_found': 1847, 'errors': 0}

Attributes:
    LANGUAGE_EXTENSIONS: Dict mapping language names to file extensions.
    DEFAULT_IGNORE_PATTERNS: List of patterns to ignore when scanning.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from ._version import __version__
from .colors import get_colors
from .gitignore import GitignoreMatcher


class _Analyzer(Protocol):
    """Structural type for language analyzers exposing analyze()."""

    def analyze(self) -> list["Symbol"]: ...


# Supported languages and their extensions
# Bumped whenever index membership or semantics change in a way that makes a
# previously-generated map unsafe to reuse incrementally. 2.2.9 bumps to "2":
# the gitignore fix changes which files belong in the index, so a "1.0" map
# built by the buggy substring matcher is discarded and rebuilt.
INDEX_FORMAT_VERSION = "2"

LANGUAGE_EXTENSIONS = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs"],
    "typescript": [".ts", ".tsx"],
    "java": [".java"],
    "kotlin": [".kt", ".kts"],
    "swift": [".swift"],
    "csharp": [".cs"],
    "go": [".go"],
    "rust": [".rs"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx"],
    "ruby": [".rb"],
    "php": [".php"],
    "dart": [".dart"],
}

# Languages analyzed by the spec-driven tree-sitter extractor
# (codenav.languages). Python keeps its stdlib-AST analyzer.
_SPEC_LANGUAGES = frozenset(
    {
        "javascript",
        "typescript",
        "ruby",
        "go",
        "rust",
        "dart",
        "java",
        "kotlin",
        "swift",
        "csharp",
        "c",
        "cpp",
        "php",
    }
)

# Spec languages whose fallback prefers ast-grep ([fast]) before regex
# (the languages ast-grep already supported before they got tree-sitter specs).
_AST_GREP_TIER: frozenset[str] = frozenset({"java", "c", "cpp", "php"})

DEFAULT_IGNORE_PATTERNS = [
    # Build artifacts and dependencies
    "node_modules",
    "__pycache__",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    "coverage",
    ".nyc_output",
    "*.min.js",
    "*.bundle.js",
    ".tox",
    "eggs",
    "*.egg-info",
    ".pytest_cache",
    "vendor",
    "target",
    "bin",
    "obj",
    # Flutter/Dart build artifacts and generated files
    ".dart_tool",
    ".flutter-plugins",
    ".flutter-plugins-dependencies",
    "*.g.dart",
    "*.freezed.dart",
    "*.gr.dart",
    # Version control
    ".git",
    ".svn",
    ".hg",
    # IDE settings
    ".idea",
    ".vscode",
    # Environment files - ALL variants (SECURITY: prevents exposure of secrets)
    ".env",
    ".env.*",
    ".env.local",
    ".env.*.local",
    ".env.production*",
    ".env.development*",
    ".envrc",
    "*.env",
    # Credentials and secrets (SECURITY)
    "secrets*",
    "*secret*",
    "*secrets*",
    "*credential*",
    "*credentials*",
    ".aws",
    ".gcp",
    ".ssh",
    ".gnupg",
    # Keys and certificates (SECURITY)
    "*.pem",
    "*.key",
    "*.p8",
    "*.p12",
    "*.pfx",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "*.crt",
    "*.cer",
    # Config files with potential secrets (SECURITY)
    ".npmrc",
    ".pypirc",
    ".netrc",
    "config/database.yml",
    "config/secrets.yml",
    # API keys and tokens
    "*apikey*",
    "*api_key*",
    "*token*",
]


@dataclass
class Symbol:
    """Represents a code symbol (function, class, method, etc.).

    Attributes:
        name: The symbol's name (e.g., 'process_payment').
        type: The symbol type ('function', 'class', 'method', 'variable', 'import').
        file_path: Relative path to the file containing the symbol.
        line_start: Starting line number (1-indexed).
        line_end: Ending line number (1-indexed, inclusive).
        signature: Function/class signature (e.g., 'def foo(x: int) -> str').
        docstring: First few lines of docstring, if present.
        parent: For methods, the containing class name.
        dependencies: List of symbols this symbol calls/uses.
        decorators: List of decorator names applied to this symbol.
        source: Engine that produced the symbol — "ast" (Python AST or
            tree-sitter), "ast-grep", or "regex". None in maps generated
            before v2.3.0.
        visibility: "private" or "protected" when the language exposes it
            (Go lowercase names, Ruby modifiers, Dart underscore prefix).
            None means public or unknown (pre-v2.3.0 maps).
        modifiers: Extra qualifiers such as "static", "async", "abstract",
            "factory", "getter", "setter". None when there are none.
        mixins: Modules mixed into a class/module symbol (Ruby
            include/extend/prepend). None for non-container symbols.
        return_type: Normalized return type name ("*Foo" → "Foo",
            "(Foo, error)" → "Foo", "pkg.Foo" → "Foo"). None when unknown.

    Example:
        >>> symbol = Symbol(
        ...     name='process_payment',
        ...     type='function',
        ...     file_path='src/billing.py',
        ...     line_start=45,
        ...     line_end=89,
        ...     signature='def process_payment(user_id: int, amount: Decimal)'
        ... )
    """

    name: str
    type: str
    file_path: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    parent: str | None = None
    dependencies: list[str] | None = None
    decorators: list[str] | None = None
    truncated: bool = False  # True if symbol exceeded max line limit during analysis
    source: str | None = None  # "ast" | "ast-grep" | "regex" (None: pre-v2.3.0 map)
    visibility: str | None = None  # "private" | "protected" (None: public/unknown)
    modifiers: list[str] | None = None  # e.g. ["static", "async"], ["factory"]
    mixins: list[str] | None = None  # Ruby include/extend/prepend module names
    return_type: str | None = None  # normalized return type name

    def __post_init__(self):
        """Initialize mutable default values."""
        if self.dependencies is None:
            self.dependencies = []
        if self.decorators is None:
            self.decorators = []


# Base classes that mark a ``class`` as an enumeration.
_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


class PythonAnalyzer(ast.NodeVisitor):
    """Analyzes Python files using AST for accurate symbol extraction.

    This analyzer provides the most accurate symbol detection for Python files,
    using Python's built-in AST module to parse the code structure.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        lines: List of source lines.
        symbols: Extracted symbols.
        current_class: Name of class currently being visited (for method detection).
        imports: List of imported modules/names.

    Example:
        >>> source = '''
        ... def greet(name: str) -> str:
        ...     \"\"\"Say hello.\"\"\"
        ...     return f"Hello, {name}"
        ... '''
        >>> analyzer = PythonAnalyzer('example.py', source)
        >>> symbols = analyzer.analyze()
        >>> print(symbols[0].name)
        'greet'
    """

    def __init__(self, file_path: str, source: str):
        """Initialize the Python analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
        """
        self.file_path = file_path
        self.source = source
        self.lines = source.split("\n")
        self.symbols: list[Symbol] = []
        self.current_class: str | None = None
        self.current_function: str | None = None
        self.imports: list[str] = []

    def get_line_end(self, node) -> int:
        """Get the end line of an AST node.

        Args:
            node: An AST node.

        Returns:
            The ending line number of the node.
        """
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno
        if hasattr(node, "body") and node.body:
            last_node = node.body[-1]
            return self.get_line_end(last_node)
        return node.lineno

    def get_signature(self, node) -> str:
        """Extract function/method signature from an AST node.

        Args:
            node: A FunctionDef or AsyncFunctionDef AST node.

        Returns:
            String representation of the function signature.

        Example:
            >>> # For 'async def foo(x: int) -> str:'
            >>> signature = analyzer.get_signature(node)
            >>> print(signature)
            'async def foo(x: int) -> str'
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    try:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    except (TypeError, AttributeError, RecursionError, ValueError):
                        # ast.unparse can fail on malformed/complex AST nodes
                        pass
                args.append(arg_str)

            returns = ""
            if node.returns:
                try:
                    returns = f" -> {ast.unparse(node.returns)}"
                except (TypeError, AttributeError, RecursionError, ValueError):
                    # ast.unparse can fail on malformed/complex AST nodes
                    pass

            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return f"{prefix}def {node.name}({', '.join(args)}){returns}"
        return ""

    def get_decorators(self, node) -> list[str]:
        """Extract decorator names from an AST node.

        Args:
            node: An AST node with decorator_list attribute.

        Returns:
            List of decorator name strings.
        """
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except (TypeError, AttributeError, RecursionError, ValueError):
                # Fallback: try to get simple decorator name
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
        return decorators

    def get_docstring(self, node) -> str | None:
        """Extract docstring from an AST node, truncated for efficiency.

        Args:
            node: An AST node that may have a docstring.

        Returns:
            First 3 lines of the docstring, or None if no docstring.
        """
        doc = ast.get_docstring(node)
        if doc:
            lines = doc.split("\n")
            if len(lines) > 3:
                return "\n".join(lines[:3]) + "..."
            return doc
        return None

    def visit_Import(self, node):
        """Visit an import statement."""
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Visit a from...import statement."""
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Visit a class definition."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except (TypeError, AttributeError, RecursionError, ValueError):
                # ast.unparse can fail on complex/malformed base class expressions
                pass

        signature = f"class {node.name}"
        if bases:
            signature += f"({', '.join(bases)})"

        # Classes deriving from an Enum flavour are modelled as enums so map
        # consumers can render them with the right kind.
        symbol_type = "class"
        for base in bases:
            last = base.split(".")[-1].split("[")[0].strip()
            if last in _ENUM_BASES:
                symbol_type = "enum"
                break

        symbol = Symbol(
            name=node.name,
            type=symbol_type,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=self.get_line_end(node),
            signature=signature,
            docstring=self.get_docstring(node),
            decorators=self.get_decorators(node),
        )
        self.symbols.append(symbol)

        # A class body resets the enclosing-function scope: its direct methods
        # take the class as parent, not some outer function.
        old_class = self.current_class
        old_function = self.current_function
        self.current_class = node.name
        self.current_function = None
        self.generic_visit(node)
        self.current_class = old_class
        self.current_function = old_function

    def visit_FunctionDef(self, node):
        """Visit a function definition."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        """Visit an async function definition."""
        self._visit_function(node)

    def _visit_function(self, node):
        """Process a function or async function definition.

        Args:
            node: A FunctionDef or AsyncFunctionDef AST node.
        """
        symbol_type = "method" if self.current_class else "function"

        # Walk the function body without descending into nested function/class
        # definitions — their calls belong to the nested symbol, not this one.
        calls = []
        stack = list(ast.iter_child_nodes(node))
        while stack:
            child = stack.pop()
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)
            stack.extend(ast.iter_child_nodes(child))

        # A method (direct child of a class) is parented on the class; a nested
        # function is parented on its containing function. This keeps
        # qualified names unique when two functions define same-named helpers.
        parent = self.current_class or self.current_function

        symbol = Symbol(
            name=node.name,
            type=symbol_type,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=self.get_line_end(node),
            signature=self.get_signature(node),
            docstring=self.get_docstring(node),
            parent=parent,
            # Sorted so the index is deterministic across runs (matches the
            # tree-sitter analyzers, which sort callees too).
            dependencies=sorted(set(calls)),
            decorators=self.get_decorators(node),
        )
        self.symbols.append(symbol)

        # Inside this function body, nested defs are children of it (not of an
        # outer class); clear current_class so they don't look like methods.
        old_class = self.current_class
        old_function = self.current_function
        self.current_class = None
        self.current_function = node.name
        self.generic_visit(node)
        self.current_class = old_class
        self.current_function = old_function

    def _add_constant(self, name: str, node) -> None:
        """Record a module-level UPPER_CASE assignment as a ``constant`` symbol."""
        if not (name.isupper() and any(c.isalpha() for c in name)):
            return
        line = self.lines[node.lineno - 1].strip() if node.lineno - 1 < len(self.lines) else name
        self.symbols.append(
            Symbol(
                name=name,
                type="constant",
                file_path=self.file_path,
                line_start=node.lineno,
                line_end=self.get_line_end(node),
                signature=line[:100],
            )
        )

    def visit_Assign(self, node):
        """Record module-level UPPER_CASE constant assignments."""
        if self.current_class is None and self.current_function is None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._add_constant(target.id, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        """Record module-level annotated UPPER_CASE constant assignments."""
        if (
            self.current_class is None
            and self.current_function is None
            and isinstance(node.target, ast.Name)
        ):
            self._add_constant(node.target.id, node)
        self.generic_visit(node)

    def analyze(self) -> list[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.

        Raises:
            SyntaxError: If the file has invalid Python syntax (caught and logged).
        """
        try:
            tree = ast.parse(self.source)
            self.visit(tree)
        except SyntaxError as e:
            print(f"Syntax error in {self.file_path}: {e}", file=sys.stderr)
        for symbol in self.symbols:
            symbol.source = "ast"
        return self.symbols


class GenericAnalyzer:
    """Regex-based analyzer for non-Python languages.

    Provides symbol detection for JavaScript, TypeScript, Java, Go, Rust, and C/C++
    using regular expression patterns. Less accurate than AST analysis but works
    across multiple languages.

    Attributes:
        PATTERNS: Dict of regex patterns for each supported language.
        file_path: Path to the file being analyzed.
        source: Source code content.
        language: The programming language of the file.

    Example:
        >>> source = 'function greet(name) { return "Hello, " + name; }'
        >>> analyzer = GenericAnalyzer('example.js', source, 'javascript')
        >>> symbols = analyzer.analyze()
    """

    PATTERNS = {
        "javascript": {
            "function": r"(?:async\s+)?function\s+(\w+)\s*\([^)]*\)",
            "arrow": r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>",
            "class": r"class\s+(\w+)(?:\s+extends\s+\w+)?",
            "method": r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*{",
        },
        "typescript": {
            "function": r"(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)",
            "interface": r"interface\s+(\w+)",
            "type": r"type\s+(\w+)\s*=",
            "class": r"class\s+(\w+)(?:\s+extends\s+\w+)?(?:\s+implements\s+\w+)?",
        },
        "java": {
            "class": r"(?:public|private|protected)?\s*class\s+(\w+)",
            "interface": r"interface\s+(\w+)",
            "method": r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*\([^)]*\)",
        },
        "go": {
            "function": r"func\s+(\w+)\s*(?:\[[^\]]*\])?\s*\(",
            "method": r"func\s+\([^)]+\)\s+(\w+)\s*(?:\[[^\]]*\])?\s*\(",
            "struct": r"type\s+(\w+)\s+struct",
            "interface": r"type\s+(\w+)\s+interface",
            "type_alias": r"type\s+(\w+)\s+(?!struct\b|interface\b)\w+",
        },
        "ruby": {
            "function": r"^[ \t]*def\s+(?!self\.)(\w+[!?=]?)",
            "class": r"^[ \t]*class\s+([A-Z]\w*)",
            "module": r"^[ \t]*module\s+([A-Z]\w*)",
        },
        "rust": {
            "function": r"(?:pub\s+)?(?:async\s+)?fn\s+(\w+)",
            "struct": r"(?:pub\s+)?struct\s+(\w+)",
            "impl": r"impl(?:<[^>]*>)?\s+(\w+)",
            "trait": r"(?:pub\s+)?trait\s+(\w+)",
            "enum": r"(?:pub\s+)?enum\s+(\w+)",
        },
        "dart": {
            "class": r"(?:abstract\s+)?class\s+(\w+)",
            "mixin": r"^[ \t]*mixin\s+(\w+)",
            "enum": r"enum\s+(\w+)\s*\{",
            "extension": r"extension\s+(\w+)\s+on\s+\w+",
            "function": r"^[ \t]*(?!(?:if|for|while|switch|catch|return|do|else|throw|new|await|assert|yield)\b)(?:Future(?:<[^>]+>)?|void|String|int|double|bool|num|dynamic|Widget|List(?:<[^>]+>)?|Map(?:<[^>]+>)?|Set(?:<[^>]+>)?|Iterable(?:<[^>]+>)?|Stream(?:<[^>]+>)?|[A-Z]\w*\??)\s+(\w+)\s*\([^)]*\)\s*(?:async\s*\*?\s*)?\{",
        },
        "kotlin": {
            "function": r"(?:suspend\s+)?fun\s+(?:<[^>]*>\s+)?(?:[\w.<>?]+\.)?(\w+)\s*\(",
            "class": r"(?:abstract\s+|open\s+|data\s+|sealed\s+|inner\s+|annotation\s+)*class\s+(\w+)",
            "interface": r"(?:fun\s+)?interface\s+(\w+)",
            "object": r"(?:^|\s)object\s+(\w+)",
            "type": r"typealias\s+(\w+)",
        },
        "swift": {
            "function": r"func\s+(\w+)\s*(?:<[^>]*>)?\s*\(",
            "class": r"(?:final\s+|open\s+)?class\s+(\w+)",
            "struct": r"struct\s+(\w+)",
            "protocol": r"protocol\s+(\w+)",
            "enum": r"(?:indirect\s+)?enum\s+(\w+)",
            "extension": r"extension\s+([\w.]+)",
        },
        "csharp": {
            "class": r"(?:public\s+|private\s+|protected\s+|internal\s+|static\s+|sealed\s+|abstract\s+|partial\s+)*class\s+(\w+)",
            "interface": r"interface\s+(\w+)",
            "struct": r"(?:readonly\s+)?(?:record\s+)?struct\s+(\w+)",
            "enum": r"enum\s+(\w+)",
            "method": r"(?:public|private|protected|internal|static|virtual|override|async|sealed)\s+[\w<>\[\],?\s]+?\b(\w+)\s*\([^)]*\)\s*(?:\{|=>)",
        },
        "c": {
            "function": r"^[A-Za-z_][\w\s\*]*?\b(\w+)\s*\([^;)]*\)\s*\{",
            "struct": r"(?:typedef\s+)?struct\s+(\w+)\s*\{",
            "enum": r"(?:typedef\s+)?enum\s+(\w+)\s*\{",
            "union": r"(?:typedef\s+)?union\s+(\w+)\s*\{",
        },
        "cpp": {
            "function": r"^[A-Za-z_][\w:\s\*&<>,~]*?\b([\w~]+)\s*\([^;)]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{",
            "class": r"class\s+(\w+)",
            "struct": r"struct\s+(\w+)\s*[\{:]",
            "namespace": r"namespace\s+(\w+)",
            "enum": r"enum\s+(?:class\s+)?(\w+)",
        },
        "php": {
            "function": r"function\s+(\w+)\s*\(",
            "class": r"(?:abstract\s+|final\s+)?class\s+(\w+)",
            "interface": r"interface\s+(\w+)",
            "trait": r"trait\s+(\w+)",
            "enum": r"enum\s+(\w+)",
        },
    }

    # Maximum lines to scan for a symbol's end before giving up
    MAX_SYMBOL_LINES = 500

    # Languages that use 'end' keyword instead of braces for block termination
    KEYWORD_END_LANGUAGES = {"ruby"}

    # Keywords that open a new block in end-based languages
    _END_OPENERS = (
        "def ",
        "class ",
        "module ",
        "do",
        "if ",
        "unless ",
        "while ",
        "until ",
        "for ",
        "begin",
        "case ",
    )

    def __init__(
        self,
        file_path: str,
        source: str,
        language: str,
        max_symbol_lines: int | None = None,
    ):
        """Initialize the generic analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
            language: Programming language identifier.
            max_symbol_lines: Override the per-symbol scan cap. Defaults to
                ``MAX_SYMBOL_LINES`` (500) when None.
        """
        self.file_path = file_path
        self.source = source
        self.language = language
        self.lines = source.split("\n")
        self.max_symbol_lines = (
            max_symbol_lines if max_symbol_lines is not None else self.MAX_SYMBOL_LINES
        )

    def analyze(self) -> list[Symbol]:
        """Analyze the file using regex patterns.

        Returns:
            List of Symbol objects found in the file.
        """
        import re

        symbols = []
        patterns = self.PATTERNS.get(self.language, {})

        for symbol_type, pattern in patterns.items():
            for match in re.finditer(pattern, self.source, re.MULTILINE):
                name = match.group(1)
                line_num = self.source[: match.start()].count("\n") + 1

                line_end = line_num
                was_truncated = False

                if self.language in self.KEYWORD_END_LANGUAGES:
                    # Keyword-based end detection (Ruby: def/class/module ... end)
                    depth = 1
                    for i, line in enumerate(self.lines[line_num:], start=line_num + 1):
                        stripped = line.strip()
                        if not stripped.startswith("#"):
                            for kw in self._END_OPENERS:
                                if stripped.startswith(kw) or stripped == kw.strip():
                                    depth += 1
                                    break
                            if (
                                stripped == "end"
                                or stripped.startswith("end ")
                                or stripped.startswith("end;")
                            ):
                                depth -= 1
                                if depth <= 0:
                                    line_end = i
                                    break
                        if i > line_num + self.max_symbol_lines:
                            line_end = i
                            was_truncated = True
                            break
                else:
                    # Brace-based end detection (Go, JS, Java, Rust, C/C++)
                    brace_count = 0
                    started = False
                    for i, line in enumerate(self.lines[line_num - 1 :], start=line_num):
                        brace_count += line.count("{") - line.count("}")
                        if "{" in line:
                            started = True
                        if started and brace_count <= 0:
                            line_end = i
                            break
                        if i > line_num + self.max_symbol_lines:
                            line_end = i
                            was_truncated = True
                            break

                symbols.append(
                    Symbol(
                        name=name,
                        type=symbol_type,
                        file_path=self.file_path,
                        line_start=line_num,
                        line_end=line_end,
                        signature=match.group(0).strip()[:100],
                        truncated=was_truncated,
                        source="regex",
                    )
                )

        return symbols


def _astgrep_to_symbol(ag_symbol: Any) -> Symbol:
    """Adapt an ``AstGrepSymbol`` to the canonical ``Symbol`` dataclass.

    The ast-grep analyzer carries the same core fields plus ``parent`` (which
    the regex fallback cannot produce), so wiring it in upgrades the
    regex-tier languages to real AST symbols.
    """
    return Symbol(
        name=ag_symbol.name,
        type=ag_symbol.type,
        file_path=ag_symbol.file_path,
        line_start=ag_symbol.line_start,
        line_end=ag_symbol.line_end,
        signature=ag_symbol.signature,
        parent=ag_symbol.parent,
        source="ast-grep",
    )


def coverage_summary_line(stats: dict[str, Any]) -> str:
    """Build a one-line, human-readable coverage summary from scan stats.

    Example: ``mapped 636 · unmapped 12 (.kt:8 .sh:4) · skipped 1204 · coverage 98.2%``
    """
    parts = [f"mapped {stats.get('files_processed', 0)}"]
    unmapped = stats.get("files_unmapped", 0)
    exts = stats.get("unmapped_extensions") or {}
    if unmapped:
        top = sorted(exts.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        ext_str = " ".join(f"{ext}:{n}" for ext, n in top)
        parts.append(f"unmapped {unmapped} ({ext_str})" if ext_str else f"unmapped {unmapped}")
    if stats.get("files_skipped"):
        causes = [
            (k[len("skipped_") :], v)
            for k, v in sorted(stats.items())
            if k.startswith("skipped_") and v
        ]
        cause_str = " ".join(f"{name}:{n}" for name, n in causes)
        parts.append(
            f"skipped {stats['files_skipped']} ({cause_str})"
            if cause_str
            else f"skipped {stats['files_skipped']}"
        )
    if "coverage_pct" in stats:
        parts.append(f"coverage {stats['coverage_pct']}%")
    if stats.get("symbols_truncated"):
        parts.append(f"truncated {stats['symbols_truncated']}")
    if stats.get("coverage_gaps"):
        parts.append(f"GAPS {','.join(stats['coverage_gaps'])}")
    return " · ".join(parts)


class GitIntegration:
    """Git integration utilities for the code mapper.

    Provides methods to get git-tracked files, parse .gitignore,
    and find changes since a specific commit.

    Attributes:
        root_path: Path to the git repository root.
        available: Whether git is available and this is a git repo.

    Example:
        >>> git = GitIntegration('/path/to/repo')
        >>> if git.available:
        ...     tracked_files = git.get_tracked_files()
        ...     print(f"Found {len(tracked_files)} tracked files")
    """

    def __init__(self, root_path: Path):
        """Initialize git integration.

        Args:
            root_path: Path to the repository root.
        """
        self.root_path = root_path
        self.available = self._check_git_available()

    def _check_git_available(self) -> bool:
        """Check if git is available and this is a git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def get_tracked_files(self) -> set[str]:
        """Get all files tracked by git.

        Returns:
            Set of relative file paths tracked by git.
        """
        if not self.available:
            return set()

        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return set()

    def get_gitignore_patterns(self) -> list[str]:
        """Parse .gitignore and return patterns.

        Returns:
            List of gitignore patterns.
        """
        patterns = []
        gitignore_path = self.root_path / ".gitignore"

        if gitignore_path.exists():
            try:
                content = gitignore_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith("#"):
                        patterns.append(line)
            except Exception:
                pass

        return patterns

    @staticmethod
    def _read_pattern_file(path: Path) -> list[str]:
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

    def get_info_exclude_patterns(self) -> list[str]:
        """Raw lines of ``.git/info/exclude`` (repo-local, uncommitted ignores)."""
        return self._read_pattern_file(self.root_path / ".git" / "info" / "exclude")

    def get_core_excludes_patterns(self) -> list[str]:
        """Raw lines of the user's ``core.excludesFile`` (global gitignore)."""
        if not self.available:
            return []
        try:
            result = subprocess.run(
                ["git", "config", "--get", "core.excludesFile"],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []
        path_str = result.stdout.strip() if result.returncode == 0 else ""
        if not path_str:
            default = Path.home() / ".config" / "git" / "ignore"
            if not default.exists():
                return []
            path_str = str(default)
        return self._read_pattern_file(Path(path_str).expanduser())

    def get_files_changed_since(self, commit: str) -> set[str]:
        """Get files that changed since a specific commit.

        Args:
            commit: Git commit hash (7-40 hex characters).

        Returns:
            Set of relative file paths that have changed.

        Raises:
            ValueError: If commit is not a valid hex hash.
        """
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.~^/@{}\-]*", commit):
            raise ValueError(f"Invalid git reference: {commit}")

        if not self.available:
            return set()

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", commit, "HEAD"],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return set()

    def get_uncommitted_changes(self) -> set[str]:
        """Get files with uncommitted changes.

        Returns:
            Set of relative file paths with uncommitted changes.
        """
        if not self.available:
            return set()

        try:
            # Get both staged and unstaged changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.root_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                files = set()
                for line in result.stdout.strip().split("\n"):
                    if line and len(line) > 3:
                        # Format: "XY filename" where XY is status
                        files.add(line[3:].strip())
                return files
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return set()


class CodeNavigator:
    """Main class for mapping a codebase to create a searchable index.

    Scans a directory tree, analyzes source files, and generates a JSON index
    containing all symbols, their locations, signatures, and dependencies.

    Attributes:
        root_path: Absolute path to the codebase root.
        ignore_patterns: List of patterns to skip during scanning.
        symbols: List of all discovered symbols.
        file_hashes: Dict mapping file paths to content hashes.
        stats: Dict with processing statistics.

    Example:
        >>> mapper = CodeNavigator('/path/to/project')
        >>> code_map = mapper.scan()
        >>> print(f"Found {code_map['stats']['symbols_found']} symbols")
        Found 1847 symbols

        >>> # Save to file
        >>> import json
        >>> with open('.codenav.json', 'w') as f:
        ...     json.dump(code_map, f)
    """

    def __init__(
        self,
        root_path: str,
        ignore_patterns: list[str] = None,
        git_only: bool = False,
        use_gitignore: bool = False,
        max_symbol_lines: int = 500,
    ):
        """Initialize the code mapper.

        Args:
            root_path: Path to the root directory to scan.
            ignore_patterns: Additional patterns to ignore. Merged with defaults.
            git_only: If True, only scan files tracked by git.
            use_gitignore: If True, also ignore patterns from .gitignore.
            max_symbol_lines: Per-symbol scan cap for the regex fallback
                (``GenericAnalyzer``). Raise it to avoid truncating very large
                functions. Default 500.
        """
        self.root_path = Path(root_path).resolve()
        self.ignore_patterns = list(ignore_patterns or DEFAULT_IGNORE_PATTERNS)
        self.git_only = git_only
        self.use_gitignore = use_gitignore
        self.max_symbol_lines = max_symbol_lines
        self.symbols: list[Symbol] = []
        self.file_hashes: dict[str, str] = {}
        # Raw import specifiers per file (rel_path -> [spec, ...]); resolved to
        # internal file paths in generate_map for the per-file "imports" key.
        self.file_imports: dict[str, list[str]] = {}
        self._lang_code_lines: dict[str, int] = {}
        self.stats: dict[str, Any] = {
            "files_processed": 0,
            "symbols_found": 0,
            "errors": 0,
            "files_skipped": 0,
            "files_unmapped": 0,
            "unmapped_extensions": {},
        }
        self._existing_map: dict[str, Any] | None = None

        # Initialize git integration
        self._git = GitIntegration(self.root_path)
        self._git_tracked_files: set[str] | None = None

        # Add gitignore patterns if requested. A ``.gitignore`` is a plain file
        # and the matcher is self-contained, so we honor it even outside a git
        # repo (tarball exports, worktrees). These are kept on ``ignore_patterns``
        # (a documented attribute) and also feed the semantic matcher below.
        if self.use_gitignore:
            gitignore_patterns = self._git.get_gitignore_patterns()
            self.ignore_patterns.extend(gitignore_patterns)

        # Cache git tracked files if git_only mode
        if self.git_only and self._git.available:
            self._git_tracked_files = self._git.get_tracked_files()

        # Real gitignore-semantics matcher (replaces the old substring test).
        # Codenav defaults + user patterns + root .gitignore live at root scope;
        # nested .gitignore files are folded in per directory during the walk.
        self._ignore_matcher = GitignoreMatcher()
        self._ignore_matcher.add_patterns(self.ignore_patterns, "")
        self._nested_gitignore_dirs: set[str] = set()
        # .git/info/exclude and core.excludesFile genuinely need a git repo.
        if self.use_gitignore and self._git.available:
            self._ignore_matcher.add_patterns(self._git.get_info_exclude_patterns(), "")
            self._ignore_matcher.add_patterns(self._git.get_core_excludes_patterns(), "")

    def _load_nested_gitignore(self, dir_abs: Path) -> None:
        """Fold a directory's ``.gitignore`` into the matcher, scoped to that dir.

        No-op unless ``use_gitignore`` is set. Called top-down during the walk so
        deeper files, appended later, override shallower ones (last-match-wins).
        """
        if not self.use_gitignore:
            return
        try:
            rel = dir_abs.relative_to(self.root_path).as_posix()
        except ValueError:
            return
        if rel in ("", ".") or rel in self._nested_gitignore_dirs:
            return  # root handled in __init__; each dir folded once
        gitignore = dir_abs / ".gitignore"
        if gitignore.is_file():
            self._nested_gitignore_dirs.add(rel)
            self._ignore_matcher.add_patterns(GitIntegration._read_pattern_file(gitignore), rel)

    def should_ignore(self, path: Path, is_dir: bool | None = None) -> bool:
        """Check if a path should be ignored, using real gitignore semantics.

        Matches on path components (never as a substring, the historical bug),
        with anchoring, ``dir/``, ``**`` and negation handled by
        :class:`~codenav.gitignore.GitignoreMatcher`.

        Args:
            path: Path to check (absolute, under the scan root).
            is_dir: Whether the path is a directory. Inferred from disk when
                omitted; the walk passes it explicitly to avoid a stat.

        Returns:
            True if the path matches the ignore rules.
        """
        try:
            rel = path.relative_to(self.root_path).as_posix()
        except ValueError:
            return False
        if rel in ("", "."):
            return False
        if is_dir is None:
            is_dir = path.is_dir()
        return self._ignore_matcher.is_ignored(rel, is_dir)

    def _is_git_tracked(self, file_path: Path) -> bool:
        """Check if a file is tracked by git.

        Args:
            file_path: Absolute path to the file.

        Returns:
            True if the file is git-tracked (or git_only mode is disabled).
        """
        if not self.git_only or self._git_tracked_files is None:
            return True

        try:
            rel_path = str(file_path.relative_to(self.root_path))
            return rel_path in self._git_tracked_files
        except ValueError:
            return False

    def get_language(self, file_path: Path) -> str | None:
        """Determine the programming language from file extension.

        Args:
            file_path: Path to the file.

        Returns:
            Language identifier string, or None if not recognized.
        """
        ext = file_path.suffix.lower()
        for lang, extensions in LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return lang
        return None

    def hash_file(self, content: str) -> str:
        """Generate a hash for file content.

        Args:
            content: File content string.

        Returns:
            12-character MD5 hash of the content.
        """
        from . import compute_content_hash

        return compute_content_hash(content)

    def analyze_file(self, file_path: Path) -> list[Symbol]:
        """Analyze a single file and extract its symbols.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of Symbol objects found in the file.
        """
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            rel_path = str(file_path.relative_to(self.root_path))
            self.file_hashes[rel_path] = self.hash_file(content)

            language = self.get_language(file_path)
            analyzer: _Analyzer
            if language is not None:
                # Cheap per-language code-volume tally, so the coverage invariant
                # can tell a genuinely broken analyzer (real code, zero symbols)
                # from a legitimately symbol-less file (an empty __init__.py).
                self._lang_code_lines[language] = self._lang_code_lines.get(language, 0) + sum(
                    1 for ln in content.splitlines() if ln.strip()
                )
            if language == "python":
                analyzer = PythonAnalyzer(rel_path, content)
            elif language in _SPEC_LANGUAGES:
                from .languages import get_spec
                from .languages.extractor import TreeSitterExtractor

                # For the ast-grep tier the extractor's fallback chain is
                # tree-sitter → ast-grep ([fast]) → regex; otherwise the
                # extractor degrades straight to the regex GenericAnalyzer.
                fallback = None
                if language in _AST_GREP_TIER:
                    fallback = partial(self._analyze_fallback, rel_path, content, language)
                spec = get_spec(language)
                assert spec is not None
                analyzer = TreeSitterExtractor(rel_path, content, spec, fallback=fallback)
            elif language:
                # Languages with no tree-sitter spec: use ast-grep when
                # available (real AST → parent linkage, better signatures),
                # else the regex fallback.
                return self._analyze_fallback(rel_path, content, language)
            else:
                return []

            symbols = analyzer.analyze()
            # Capture raw import specifiers so generate_map can resolve them to
            # internal file paths for the per-file "imports" key.
            self.file_imports[rel_path] = list(getattr(analyzer, "imports", []) or [])
            return symbols

        except Exception as e:
            self.stats["errors"] += 1
            print(f"Error analyzing {file_path}: {e}", file=sys.stderr)
            return []

    def _analyze_fallback(self, rel_path: str, content: str, language: str) -> list[Symbol]:
        """Analyze a regex-tier language, preferring ast-grep when installed.

        Uses ``AstGrepAnalyzer`` (opt-in via the ``[fast]`` extra) for an
        AST-level parse with parent linkage; falls back to the regex
        ``GenericAnalyzer`` when ast-grep is absent, the language is
        unsupported by it, or it yields nothing.
        """
        try:
            from .ast_grep_analyzer import AstGrepAnalyzer, is_ast_grep_available

            if is_ast_grep_available():
                ag = AstGrepAnalyzer(rel_path, content, language)
                if ag.available:
                    converted = [_astgrep_to_symbol(s) for s in ag.analyze()]
                    if converted:
                        return converted
        except Exception:
            # Any ast-grep hiccup must not break the scan — degrade to regex.
            pass

        return GenericAnalyzer(
            rel_path, content, language, max_symbol_lines=self.max_symbol_lines
        ).analyze()

    def _count_unmapped(self, file_path: Path) -> None:
        """Record a file whose extension has no analyzer (coverage metric)."""
        self.stats["files_unmapped"] += 1
        ext = file_path.suffix.lower() or "<none>"
        exts = self.stats["unmapped_extensions"]
        exts[ext] = exts.get(ext, 0) + 1

    def _record_skip(self, file_path: Path, cause: str = "gitignore") -> None:
        """Record a file skipped by an ignore rule, keyed by distinguishable cause.

        Separating causes is what lets ``errors: 0`` stop coexisting with a fifth
        of the code silently missing: a reader can tell "ignored on purpose" from
        "the parser choked" from "no analyzer for this extension".
        """
        self.stats["files_skipped"] += 1
        key = f"skipped_{cause}"
        self.stats[key] = self.stats.get(key, 0) + 1

    def _finalize_coverage(self, mapped_total: int) -> None:
        """Compute derived coverage metrics after a scan completes.

        ``coverage_pct`` is mapped files over (mapped + unmapped-by-extension);
        ignored/skipped files are excluded from the denominator.

        Also builds the per-language breakdown and the coverage invariant: a
        supported language present on disk that produced **zero** symbols across
        every one of its files means its analyzer silently broke. That is an
        error, not a statistic — an index that reports ``errors: 0`` while a
        fifth of the code is missing is worse than no index, because the agent
        concludes "not in the code" when the truth is "not in the index".
        """
        self.stats["symbols_found"] = len(self.symbols)
        self.stats["symbols_truncated"] = sum(1 for s in self.symbols if s.truncated)
        denom = mapped_total + self.stats["files_unmapped"]
        self.stats["coverage_pct"] = round(100 * mapped_total / denom, 1) if denom else 100.0

        # Per-language: files analyzed (from file_hashes) vs files that yielded
        # at least one symbol.
        per_language: dict[str, dict[str, int]] = {}
        for rel_path in self.file_hashes:
            lang = self.get_language(Path(rel_path))
            if lang is None:
                continue
            entry = per_language.setdefault(
                lang, {"files": 0, "files_with_symbols": 0, "symbols": 0}
            )
            entry["files"] += 1
        files_with_symbols: dict[str, set[str]] = {}
        for symbol in self.symbols:
            lang = self.get_language(Path(symbol.file_path))
            if lang is None:
                continue
            entry = per_language.setdefault(
                lang, {"files": 0, "files_with_symbols": 0, "symbols": 0}
            )
            entry["symbols"] += 1
            files_with_symbols.setdefault(lang, set()).add(symbol.file_path)
        for lang, files in files_with_symbols.items():
            per_language[lang]["files_with_symbols"] = len(files)

        self.stats["per_language"] = per_language
        # A gap = a language with real code volume (not just an empty file) whose
        # analyzer extracted nothing anywhere.
        broken = sorted(
            lang
            for lang, e in per_language.items()
            if e["files"] >= self.MIN_FILES_FOR_GAP
            and e["files_with_symbols"] == 0
            and self._lang_code_lines.get(lang, 0) >= self.MIN_CODE_LINES_FOR_GAP
        )
        self.stats["coverage_gaps"] = broken
        if broken:
            self.stats["errors"] += len(broken)
            print(
                "ERROR: coverage invariant violated — these languages have source "
                f"files but zero extracted symbols: {', '.join(broken)}",
                file=sys.stderr,
            )

    # Maximum time allowed for a scan operation (seconds)
    SCAN_TIMEOUT = 30

    # A language is only flagged as a broken-analyzer gap when it has several
    # files AND real code volume yet zero symbols anywhere — thresholds chosen so
    # a stray empty __init__.py or a comment-only file never triggers the hard
    # exit, but a genuinely dead analyzer (dozens of files, nothing extracted)
    # always does.
    MIN_FILES_FOR_GAP = 3
    MIN_CODE_LINES_FOR_GAP = 30

    def scan(self) -> dict[str, Any]:
        """Scan the entire codebase and generate a code map.

        Returns:
            Dict containing the complete code map with files, index, and stats.
            Includes 'scan_timeout': True if the operation was cut short.

        Example:
            >>> mapper = CodeNavigator('/my/project')
            >>> result = mapper.scan()
            >>> print(result.keys())
            dict_keys(['version', 'root', 'generated_at', 'stats', 'files', 'index'])
        """
        mode = "git-tracked files" if self.git_only else "codebase"
        print(f"Scanning {mode} at: {self.root_path}", file=sys.stderr)

        if self.git_only:
            if not self._git.available:
                print("Warning: git not available, scanning all files", file=sys.stderr)
            elif self._git_tracked_files:
                print(f"  Git tracked files: {len(self._git_tracked_files)}", file=sys.stderr)

        scan_start = time.monotonic()
        timed_out = False

        for root, dirs, files in os.walk(self.root_path):
            if time.monotonic() - scan_start > self.SCAN_TIMEOUT:
                timed_out = True
                print("Warning: scan timed out, returning partial results", file=sys.stderr)
                break
            self._load_nested_gitignore(Path(root))
            dirs[:] = [d for d in dirs if not self.should_ignore(Path(root) / d, is_dir=True)]

            for file in files:
                file_path = Path(root) / file
                if self.should_ignore(file_path, is_dir=False):
                    self._record_skip(file_path)
                    continue

                # Skip if not git-tracked (when git_only mode is enabled)
                if not self._is_git_tracked(file_path):
                    self.stats["files_skipped"] += 1
                    self.stats["skipped_not_tracked"] = self.stats.get("skipped_not_tracked", 0) + 1
                    continue

                language = self.get_language(file_path)
                if language:
                    symbols = self.analyze_file(file_path)
                    self.symbols.extend(symbols)
                    self.stats["files_processed"] += 1
                else:
                    self._count_unmapped(file_path)

        self._finalize_coverage(self.stats["files_processed"])
        if timed_out:
            self.stats["scan_timeout"] = True
        return self.generate_map()

    def get_current_file_hash(self, file_path: Path) -> str | None:
        """Get the hash of a file's current content without full analysis.

        Args:
            file_path: Path to the file.

        Returns:
            Hash string, or None if file cannot be read.
        """
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return self.hash_file(content)
        except Exception:
            return None

    def scan_incremental(self, existing_map_path: str) -> dict[str, Any]:
        """Incrementally update an existing code map.

        Only re-analyzes files that have changed since the last scan.
        This is much faster than a full scan for large codebases.

        Args:
            existing_map_path: Path to the existing .codenav.json file.

        Returns:
            Dict containing the updated code map.

        Example:
            >>> mapper = CodeNavigator('/my/project')
            >>> result = mapper.scan_incremental('.codenav.json')
            >>> print(result['stats'])
            {'files_processed': 5, 'files_unchanged': 137, 'files_added': 2, ...}
        """
        # Load existing map - only extract 'files' to minimize memory usage
        # The full map can be large; we only need the files dict for comparison
        try:
            with open(existing_map_path, encoding="utf-8") as f:
                existing_map = json.load(f)
                # A format-version mismatch means the old index was built by a
                # different codenav whose membership/semantics may differ (e.g.
                # the pre-2.2.9 substring ignore bug). Reusing it would carry the
                # stale rows forward silently — force a full rebuild instead.
                existing_version = existing_map.get("version")
                if existing_version != INDEX_FORMAT_VERSION:
                    print(
                        f"Index format changed ({existing_version} -> "
                        f"{INDEX_FORMAT_VERSION}), performing full scan",
                        file=sys.stderr,
                    )
                    return self.scan()
                # Extract only what we need, let the rest be garbage collected
                existing_files = existing_map.get("files", {})
                del existing_map  # Explicit cleanup of the full map
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Cannot load existing map ({e}), performing full scan", file=sys.stderr)
            return self.scan()
        print(f"Incremental scan at: {self.root_path}", file=sys.stderr)
        print(f"Existing map has {len(existing_files)} files", file=sys.stderr)

        # Initialize incremental stats
        self.stats: dict[str, Any] = {
            "files_processed": 0,
            "files_unchanged": 0,
            "files_added": 0,
            "files_modified": 0,
            "files_deleted": 0,
            "symbols_found": 0,
            "errors": 0,
            "files_skipped": 0,
            "files_unmapped": 0,
            "unmapped_extensions": {},
        }

        # Track which files we've seen in current scan
        current_files: dict[str, str] = {}  # rel_path -> hash

        # First pass: collect all current files and their hashes
        # Note: Files may be deleted/modified during walk (TOCTOU).
        # We handle this by checking existence and catching exceptions.
        for root, dirs, files in os.walk(self.root_path):
            self._load_nested_gitignore(Path(root))
            dirs[:] = [d for d in dirs if not self.should_ignore(Path(root) / d, is_dir=True)]

            for file in files:
                file_path = Path(root) / file
                if self.should_ignore(file_path, is_dir=False):
                    self._record_skip(file_path)
                    continue

                # Skip symlinks to prevent symlink attacks
                try:
                    if file_path.is_symlink():
                        self._record_skip(file_path, "symlink")
                        continue
                except OSError:
                    continue

                language = self.get_language(file_path)
                if language:
                    rel_path = str(file_path.relative_to(self.root_path))
                    try:
                        current_hash = self.get_current_file_hash(file_path)
                        if current_hash:
                            current_files[rel_path] = current_hash
                    except OSError:
                        # File disappeared or became inaccessible during scan
                        pass
                else:
                    self._count_unmapped(file_path)

        # Categorize files
        unchanged_files = []
        modified_files = []
        added_files = []

        for rel_path, current_hash in current_files.items():
            if rel_path in existing_files:
                existing_hash = existing_files[rel_path].get("hash", "")
                if current_hash == existing_hash:
                    unchanged_files.append(rel_path)
                else:
                    modified_files.append(rel_path)
            else:
                added_files.append(rel_path)

        # Files in existing map but not in current scan = deleted
        deleted_files = [f for f in existing_files if f not in current_files]

        print(f"  Unchanged: {len(unchanged_files)}", file=sys.stderr)
        print(f"  Modified: {len(modified_files)}", file=sys.stderr)
        print(f"  Added: {len(added_files)}", file=sys.stderr)
        print(f"  Deleted: {len(deleted_files)}", file=sys.stderr)

        # Preserve unchanged files' symbols
        for rel_path in unchanged_files:
            file_info = existing_files[rel_path]
            self.file_hashes[rel_path] = file_info.get("hash", "")
            # Carry over already-resolved imports; generate_map re-resolves them
            # (resolved file paths round-trip through the resolver's exact match).
            self.file_imports[rel_path] = list(file_info.get("imports", []) or [])

            # Convert stored symbols back to Symbol objects
            for sym_data in file_info.get("symbols", []):
                symbol = Symbol(
                    name=sym_data["name"],
                    type=sym_data["type"],
                    file_path=rel_path,
                    line_start=sym_data["lines"][0],
                    line_end=sym_data["lines"][1],
                    signature=sym_data.get("signature"),
                    docstring=sym_data.get("docstring"),
                    parent=sym_data.get("parent"),
                    dependencies=sym_data.get("deps") or [],
                    decorators=sym_data.get("decorators") or [],
                    truncated=sym_data.get("truncated", False),
                    source=sym_data.get("source"),
                    visibility=sym_data.get("visibility"),
                    modifiers=sym_data.get("modifiers"),
                    mixins=sym_data.get("mixins"),
                    return_type=sym_data.get("return_type"),
                )
                self.symbols.append(symbol)

        self.stats["files_unchanged"] = len(unchanged_files)

        # Analyze modified and added files
        # Note: TOCTOU mitigation - files may have changed or been deleted
        # between the hash check and analysis. We handle this gracefully.
        files_to_analyze = modified_files + added_files
        for rel_path in files_to_analyze:
            file_path = self.root_path / rel_path
            try:
                # Check file still exists and is a regular file (not symlink)
                if not file_path.is_file() or file_path.is_symlink():
                    # File was deleted or replaced with symlink between hash and analyze
                    print(
                        f"  Skipping {rel_path}: file no longer exists or is symlink",
                        file=sys.stderr,
                    )
                    self.stats["errors"] += 1
                    continue

                symbols = self.analyze_file(file_path)
                self.symbols.extend(symbols)
                self.stats["files_processed"] += 1
            except OSError as e:
                # File became inaccessible between hash check and analysis (TOCTOU)
                print(f"  Skipping {rel_path}: {e}", file=sys.stderr)
                self.stats["errors"] += 1
                continue

        self.stats["files_added"] = len(added_files)
        self.stats["files_modified"] = len(modified_files)
        self.stats["files_deleted"] = len(deleted_files)
        # Coverage reflects the whole tree: all current recognized files
        # (unchanged + modified + added) over recognized + unmapped.
        self._finalize_coverage(len(current_files))

        return self.generate_map()

    def _attach_resolved_imports(self, files_map: dict[str, dict[str, Any]]) -> None:
        """Resolve each file's raw import specifiers to internal file paths.

        Adds an ``"imports"`` key (list of repo-relative file paths) to every
        entry in ``files_map``. Specifiers that resolve outside the repo, or not
        at all (external libraries), are omitted. Best-effort: any resolver
        failure leaves imports empty rather than aborting the scan.
        """
        for file_path in files_map:
            files_map[file_path].setdefault("imports", [])

        if not any(self.file_imports.values()):
            return

        try:
            from .import_resolver import ImportResolver

            resolver = ImportResolver(str(self.root_path))
            resolver.load_aliases_from_tsconfig()
            resolver.load_aliases_from_pyproject()
            resolver.build_index()
        except Exception:
            return

        known_files = set(files_map)
        for file_path, raw_imports in self.file_imports.items():
            if file_path not in files_map:
                continue
            resolved: list[str] = []
            seen: set[str] = set()
            for spec in raw_imports:
                target = self._resolve_one(resolver, file_path, spec)
                # Keep only internal files that we actually mapped, and never a
                # self-import.
                if target and target in known_files and target != file_path and target not in seen:
                    seen.add(target)
                    resolved.append(target)
            files_map[file_path]["imports"] = resolved

    @staticmethod
    def _resolve_one(resolver: Any, file_path: str, spec: str) -> str | None:
        """Resolve a single import spec, retrying shorter dotted prefixes.

        Python ``from pkg.mod import name`` is recorded as ``pkg.mod.name``,
        which does not name a file. Retry ``pkg.mod`` then ``pkg`` so the import
        still resolves to the module file.
        """
        candidate = spec
        while candidate:
            try:
                result = resolver.resolve(file_path, candidate)
            except Exception:
                return None
            path = result.path
            if result.found and isinstance(path, str):
                return path
            if "." not in candidate:
                return None
            candidate = candidate.rsplit(".", 1)[0]
        return None

    def generate_map(self) -> dict[str, Any]:
        """Generate the code map structure from collected symbols.

        Returns:
            Dict with version, root, timestamp, stats, files map, and symbol index.
        """
        # Start with all analyzed files (including those with no symbols)
        files_map = {}
        for file_path, file_hash in self.file_hashes.items():
            files_map[file_path] = {
                "hash": file_hash,
                "symbols": [],
            }

        # Add symbols to their respective files
        for symbol in self.symbols:
            if symbol.file_path not in files_map:
                files_map[symbol.file_path] = {
                    "hash": self.file_hashes.get(symbol.file_path, ""),
                    "symbols": [],
                }
            symbol_dict = {
                "name": symbol.name,
                "type": symbol.type,
                "lines": [symbol.line_start, symbol.line_end],
                "signature": symbol.signature,
                "docstring": symbol.docstring,
                "parent": symbol.parent,
                "deps": symbol.dependencies[:10] if symbol.dependencies else None,
                "decorators": symbol.decorators if symbol.decorators else None,
            }
            # Only include truncated flag when True (keeps output compact)
            if symbol.truncated:
                symbol_dict["truncated"] = True
            # Engine provenance; omitted when unknown (pre-v2.3.0 round-trips)
            if symbol.source:
                symbol_dict["source"] = symbol.source
            # v2.3.0 enrichment keys — emitted only when set (public visibility
            # is normalized to None upstream, keeping the map compact)
            if symbol.visibility:
                symbol_dict["visibility"] = symbol.visibility
            if symbol.modifiers:
                symbol_dict["modifiers"] = symbol.modifiers
            if symbol.mixins:
                symbol_dict["mixins"] = symbol.mixins
            if symbol.return_type:
                symbol_dict["return_type"] = symbol.return_type
            files_map[symbol.file_path]["symbols"].append(symbol_dict)

        # Resolve raw import specifiers to internal repo file paths so map
        # consumers can follow file-to-file import relationships. Unresolved /
        # external imports (third-party libraries) are dropped — only repo
        # files are linked.
        self._attach_resolved_imports(files_map)

        symbol_index = {}
        for symbol in self.symbols:
            key = symbol.name.lower()
            if key not in symbol_index:
                symbol_index[key] = []
            symbol_index[key].append(
                {
                    "file": symbol.file_path,
                    "type": symbol.type,
                    "lines": [symbol.line_start, symbol.line_end],
                    "parent": symbol.parent,
                }
            )

        return {
            "version": INDEX_FORMAT_VERSION,
            "root": str(self.root_path),
            "generated_at": datetime.now().isoformat(),
            "stats": self.stats,
            "files": files_map,
            "index": symbol_index,
        }


def add_map_arguments(parser: argparse.ArgumentParser) -> None:
    """Add map command arguments to a parser.

    Args:
        parser: The argument parser to add arguments to.
    """
    parser.add_argument("path", help="Path to the codebase root directory")
    parser.add_argument(
        "-o", "--output", default=".codenav.json", help="Output file path (default: .codenav.json)"
    )
    parser.add_argument("-i", "--ignore", nargs="*", help="Additional patterns to ignore")
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Only update changed files (requires existing map)",
    )
    parser.add_argument(
        "--git-only",
        action="store_true",
        help="Only scan files tracked by git",
    )
    parser.add_argument(
        "--use-gitignore",
        action="store_true",
        help="Also ignore patterns from .gitignore",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Output compact JSON (default: pretty-printed)"
    )
    parser.add_argument(
        "--max-symbol-lines",
        type=int,
        default=500,
        help="Per-symbol scan cap for regex-based languages (default: 500). "
        "Raise it to avoid truncating very large functions.",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")


def run_map(args: argparse.Namespace) -> None:
    """Execute the map command with parsed arguments.

    Args:
        args: Parsed command-line arguments.
    """
    ignore_patterns = DEFAULT_IGNORE_PATTERNS.copy()
    if args.ignore:
        ignore_patterns.extend(args.ignore)

    git_only = getattr(args, "git_only", False)
    use_gitignore = getattr(args, "use_gitignore", False)

    mapper = CodeNavigator(
        args.path,
        ignore_patterns,
        git_only=git_only,
        use_gitignore=use_gitignore,
        max_symbol_lines=getattr(args, "max_symbol_lines", 500),
    )

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(args.path, output_path)

    # Use incremental scan if requested and existing map exists
    incremental = getattr(args, "incremental", False)
    if incremental and os.path.exists(output_path):
        code_map = mapper.scan_incremental(output_path)
    else:
        if incremental:
            print(f"No existing map at {output_path}, performing full scan", file=sys.stderr)
        code_map = mapper.scan()

    with open(output_path, "w", encoding="utf-8") as f:
        if args.compact:
            json.dump(code_map, f, separators=(",", ":"))
        else:
            json.dump(code_map, f, indent=2)

    c = get_colors(no_color=args.no_color)
    stats = code_map["stats"]

    # Display appropriate message based on scan type
    if "files_unchanged" in stats:
        # Incremental scan
        print(f"\n{c.success('✓')} Code map updated: {c.cyan(output_path)}", file=sys.stderr)
        print(f"  Unchanged: {c.dim(str(stats['files_unchanged']))}", file=sys.stderr)
        print(f"  Modified: {c.yellow(str(stats['files_modified']))}", file=sys.stderr)
        print(f"  Added: {c.green(str(stats['files_added']))}", file=sys.stderr)
        print(f"  Deleted: {c.magenta(str(stats['files_deleted']))}", file=sys.stderr)
        print(f"  Total symbols: {c.green(str(stats['symbols_found']))}", file=sys.stderr)
    else:
        # Full scan
        print(f"\n{c.success('✓')} Code map generated: {c.cyan(output_path)}", file=sys.stderr)
        print(f"  Files processed: {c.green(str(stats['files_processed']))}", file=sys.stderr)
        print(f"  Symbols found: {c.green(str(stats['symbols_found']))}", file=sys.stderr)

    # Coverage summary (mapped / unmapped-by-extension / skipped / coverage%)
    if "coverage_pct" in stats:
        print(f"  Coverage: {c.cyan(coverage_summary_line(stats))}", file=sys.stderr)

    summary = {"output": output_path, "stats": stats}
    if args.compact:
        print(json.dumps(summary, separators=(",", ":")))
    else:
        print(json.dumps(summary, indent=2))

    # A violated coverage invariant is a hard failure: the index is unsafe to
    # trust (a whole language extracted nothing), so exit non-zero rather than
    # letting a broken index look successful.
    if stats.get("coverage_gaps"):
        print(
            f"{c.error('✗')} Coverage invariant violated for: "
            f"{', '.join(stats['coverage_gaps'])}",
            file=sys.stderr,
        )
        sys.exit(2)


def main():
    """Command-line interface for the code mapper.

    Usage:
        codenav scan /path/to/project [-o OUTPUT] [-i IGNORE...] [--compact]

    Example:
        $ codenav scan /my/project -o .codenav.json
    """
    parser = argparse.ArgumentParser(
        description="Generate a code map for token-efficient navigation",
        epilog="Example: codenav scan /my/project -o .codenav.json",
    )
    add_map_arguments(parser)
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()
    run_map(args)


if __name__ == "__main__":
    main()
