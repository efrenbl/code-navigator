#!/usr/bin/env python3
"""AST-Grep Analyzer - High-performance multi-language code analysis.

This module provides an optional high-performance analyzer using ast-grep's
native Python bindings. It offers superior accuracy compared to regex-based
analysis and supports 20+ programming languages through tree-sitter.

Requirements:
    pip install ast-grep-py

Example:
    >>> from codenav.ast_grep_analyzer import AstGrepAnalyzer
    >>> analyzer = AstGrepAnalyzer("example.py", source_code, "python")
    >>> symbols = analyzer.analyze()
    >>> imports = analyzer.find_imports()
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Check for ast-grep availability
try:
    from ast_grep_py import SgRoot
    HAS_AST_GREP = True
except ImportError:
    HAS_AST_GREP = False
    SgRoot = None


@dataclass
class AstGrepSymbol:
    """Symbol extracted by ast-grep.

    Attributes:
        name: Symbol name (function, class, variable name).
        type: Symbol type (function, class, method, interface, etc.).
        file_path: Relative file path.
        line_start: Starting line (1-indexed).
        line_end: Ending line (1-indexed).
        signature: Full signature text (truncated).
        parent: Parent class name for methods.
        meta_vars: Captured meta-variables from pattern.
    """
    name: str
    type: str
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    parent: Optional[str] = None
    meta_vars: Dict[str, str] = field(default_factory=dict)


class AstGrepAnalyzer:
    """Multi-language analyzer using ast-grep native Python bindings.

    This analyzer provides accurate AST-based code analysis for multiple
    languages without the overhead of subprocess calls. It uses declarative
    patterns that are easy to maintain and extend.

    Supported Languages:
        python, javascript, typescript, go, rust, java, ruby, swift,
        kotlin, c, cpp, csharp, php, lua, scala, elixir

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        language: Programming language identifier.
        root: SgRoot instance for AST operations.

    Example:
        >>> source = '''
        ... def greet(name: str) -> str:
        ...     return f"Hello, {name}"
        ... '''
        >>> analyzer = AstGrepAnalyzer("greet.py", source, "python")
        >>> symbols = analyzer.analyze()
        >>> print(symbols[0].name)
        'greet'
    """

    # Pattern definitions for each language
    # Format: { "symbol_type": "pattern" } or { "symbol_type": {"kind": "ast_node_kind"} }
    PATTERNS = {
        "python": {
            "function": {"kind": "function_definition"},
            "class": {"kind": "class_definition"},
            "import": "import $MODULE",
            "import_from": "from $MODULE import $$$NAMES",
            "async_function": {"kind": "function_definition", "pattern": "async def $NAME"},
        },
        "javascript": {
            "function": {"kind": "function_declaration"},
            "arrow": "const $NAME = ($$$ARGS) => $$$BODY",
            "arrow_async": "const $NAME = async ($$$ARGS) => $$$BODY",
            "class": {"kind": "class_declaration"},
            "method": {"kind": "method_definition"},
            "import": 'import $$$ITEMS from "$PATH"',
            "import_default": 'import $NAME from "$PATH"',
            "require": 'require("$PATH")',
        },
        "typescript": {
            "function": {"kind": "function_declaration"},
            "arrow": "const $NAME = ($$$ARGS): $RETURN => $$$BODY",
            "class": {"kind": "class_declaration"},
            "interface": {"kind": "interface_declaration"},
            "type_alias": {"kind": "type_alias_declaration"},
            "method": {"kind": "method_definition"},
            "import": 'import $$$ITEMS from "$PATH"',
            "import_type": 'import type $$$ITEMS from "$PATH"',
        },
        "go": {
            "function": "func $NAME($$$ARGS)",
            "method": "func ($RECEIVER) $NAME($$$ARGS)",
            "struct": "type $NAME struct",
            "interface": "type $NAME interface",
            "import": 'import "$PATH"',
        },
        "rust": {
            "function": {"kind": "function_item"},
            "struct": {"kind": "struct_item"},
            "enum": {"kind": "enum_item"},
            "impl": {"kind": "impl_item"},
            "trait": {"kind": "trait_item"},
            "use": "use $PATH",
        },
        "java": {
            "class": {"kind": "class_declaration"},
            "interface": {"kind": "interface_declaration"},
            "method": {"kind": "method_declaration"},
            "import": "import $PATH;",
        },
        "ruby": {
            "method": {"kind": "method"},
            "class": {"kind": "class"},
            "module": {"kind": "module"},
            "require": 'require "$PATH"',
            "require_relative": 'require_relative "$PATH"',
        },
        "swift": {
            "function": "func $NAME($$$ARGS)",
            "class": "class $NAME",
            "struct": "struct $NAME",
            "protocol": "protocol $NAME",
            "import": "import $MODULE",
        },
        "kotlin": {
            "function": "fun $NAME($$$ARGS)",
            "class": "class $NAME",
            "interface": "interface $NAME",
            "import": "import $PATH",
        },
        "c": {
            "function": {"kind": "function_definition"},
            "struct": "struct $NAME",
            "include": '#include "$PATH"',
            "include_system": "#include <$PATH>",
        },
        "cpp": {
            "function": {"kind": "function_definition"},
            "class": {"kind": "class_specifier"},
            "struct": "struct $NAME",
            "namespace": "namespace $NAME",
            "include": '#include "$PATH"',
        },
    }

    # Language aliases
    LANGUAGE_ALIASES = {
        "js": "javascript",
        "ts": "typescript",
        "tsx": "typescript",
        "jsx": "javascript",
        "rs": "rust",
        "rb": "ruby",
        "kt": "kotlin",
        "cs": "csharp",
    }

    def __init__(self, file_path: str, source: str, language: str):
        """Initialize the analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
            language: Programming language identifier.

        Raises:
            ImportError: If ast-grep-py is not installed.
        """
        if not HAS_AST_GREP:
            raise ImportError(
                "ast-grep-py is required for AstGrepAnalyzer. "
                "Install with: pip install ast-grep-py"
            )

        self.file_path = file_path
        self.source = source
        self.language = self.LANGUAGE_ALIASES.get(language.lower(), language.lower())

        # Parse source code
        try:
            self.root = SgRoot(source, self.language)
            self._available = True
        except Exception:
            self._available = False
            self.root = None

    @property
    def available(self) -> bool:
        """Check if analysis is available for this language."""
        return self._available and self.language in self.PATTERNS

    def analyze(self) -> List[AstGrepSymbol]:
        """Extract all symbols from the source code.

        Returns:
            List of AstGrepSymbol objects found in the file.
        """
        if not self.available:
            return []

        symbols = []
        patterns = self.PATTERNS.get(self.language, {})
        root_node = self.root.root()

        for symbol_type, pattern_config in patterns.items():
            # Skip import patterns (handled separately)
            if "import" in symbol_type or symbol_type in ("require", "use", "include"):
                continue

            matches = self._find_matches(root_node, pattern_config)

            for match in matches:
                symbol = self._extract_symbol(match, symbol_type)
                if symbol:
                    symbols.append(symbol)

        return symbols

    def _find_matches(self, node: Any, pattern_config) -> List[Any]:
        """Find matches using pattern or kind."""
        if isinstance(pattern_config, str):
            # Direct pattern
            return list(node.find_all(pattern=pattern_config))
        elif isinstance(pattern_config, dict):
            # Kind-based or combined
            if "kind" in pattern_config and "pattern" in pattern_config:
                # Both kind and pattern
                kind_matches = list(node.find_all(kind=pattern_config["kind"]))
                return [m for m in kind_matches if m.matches(pattern=pattern_config["pattern"])]
            elif "kind" in pattern_config:
                return list(node.find_all(kind=pattern_config["kind"]))
            elif "pattern" in pattern_config:
                return list(node.find_all(pattern=pattern_config["pattern"]))
        return []

    def _extract_symbol(self, match: Any, symbol_type: str) -> Optional[AstGrepSymbol]:
        """Extract symbol information from a match."""
        try:
            # Try to get name from meta-variable
            name_node = match.get_match("NAME")
            if name_node:
                name = name_node.text()
            else:
                # Try field-based extraction
                name_field = match.field("name")
                if name_field:
                    name = name_field.text()
                else:
                    # Fallback: extract first identifier
                    name = self._extract_name_fallback(match, symbol_type)
                    if not name:
                        return None

            # Get range
            rng = match.range()

            # Get signature (truncated)
            full_text = match.text()
            signature = full_text[:150] + "..." if len(full_text) > 150 else full_text
            # Clean up signature (first line only for readability)
            signature = signature.split("\n")[0].strip()

            return AstGrepSymbol(
                name=name,
                type=symbol_type,
                file_path=self.file_path,
                line_start=rng.start.line + 1,  # Convert to 1-indexed
                line_end=rng.end.line + 1,
                signature=signature,
            )

        except Exception:
            return None

    def _extract_name_fallback(self, match: Any, symbol_type: str) -> Optional[str]:
        """Fallback method to extract name from AST node."""
        text = match.text()

        # Language-specific extraction
        if self.language == "python":
            if symbol_type in ("function", "async_function"):
                # def name(...) or async def name(...)
                if "def " in text:
                    start = text.index("def ") + 4
                    end = text.index("(", start)
                    return text[start:end].strip()
            elif symbol_type == "class":
                if "class " in text:
                    start = text.index("class ") + 6
                    end = text.find("(", start)
                    if end == -1:
                        end = text.find(":", start)
                    return text[start:end].strip()

        elif self.language in ("javascript", "typescript"):
            if symbol_type == "function":
                if "function " in text:
                    start = text.index("function ") + 9
                    end = text.index("(", start)
                    return text[start:end].strip()

        return None

    def find_imports(self) -> List[str]:
        """Extract all import statements.

        Returns:
            List of imported module/path strings.
        """
        if not self.available:
            return []

        imports = []
        patterns = self.PATTERNS.get(self.language, {})
        root_node = self.root.root()

        # Collect import-related patterns
        import_patterns = {
            k: v for k, v in patterns.items()
            if "import" in k or k in ("require", "use", "include", "include_system")
        }

        for pattern_type, pattern in import_patterns.items():
            if isinstance(pattern, str):
                matches = root_node.find_all(pattern=pattern)
                for match in matches:
                    # Try common meta-variables
                    for var in ["MODULE", "PATH", "ITEMS"]:
                        node = match.get_match(var)
                        if node:
                            text = node.text().strip('"\'')
                            if text and text not in imports:
                                imports.append(text)
                            break

        return imports

    def find_classes(self) -> List[Tuple[str, List[str]]]:
        """Find classes with their methods.

        Returns:
            List of (class_name, [method_names]) tuples.
        """
        if not self.available:
            return []

        results = []
        root_node = self.root.root()

        # Find class patterns based on language
        class_kind = {
            "python": "class_definition",
            "javascript": "class_declaration",
            "typescript": "class_declaration",
            "java": "class_declaration",
            "ruby": "class",
            "cpp": "class_specifier",
        }.get(self.language)

        if not class_kind:
            return []

        for class_match in root_node.find_all(kind=class_kind):
            # Get class name
            name_field = class_match.field("name")
            class_name = name_field.text() if name_field else "Unknown"

            # Find methods within this class
            methods = []
            method_kind = {
                "python": "function_definition",
                "javascript": "method_definition",
                "typescript": "method_definition",
                "java": "method_declaration",
                "ruby": "method",
            }.get(self.language)

            if method_kind:
                for method in class_match.find_all(kind=method_kind):
                    method_name_field = method.field("name")
                    if method_name_field:
                        methods.append(method_name_field.text())

            results.append((class_name, methods))

        return results


def analyze_with_ast_grep(
    file_path: str,
    source: str,
    language: str,
) -> List[AstGrepSymbol]:
    """Convenience function to analyze a file with ast-grep.

    Args:
        file_path: Relative file path.
        source: Source code content.
        language: Programming language.

    Returns:
        List of extracted symbols.

    Example:
        >>> symbols = analyze_with_ast_grep("app.py", source, "python")
        >>> for sym in symbols:
        ...     print(f"{sym.type}: {sym.name}")
    """
    if not HAS_AST_GREP:
        return []

    analyzer = AstGrepAnalyzer(file_path, source, language)
    return analyzer.analyze()


def is_ast_grep_available() -> bool:
    """Check if ast-grep-py is installed and available."""
    return HAS_AST_GREP
