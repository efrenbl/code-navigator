"""JavaScript and TypeScript analyzers — thin shims over the spec-driven extractor.

Deprecated import path kept for backward compatibility: the extraction logic
now lives in :mod:`codenav.languages.javascript` /
:mod:`codenav.languages.typescript` (declarative specs) and
:class:`codenav.languages.extractor.TreeSitterExtractor`.

Falls back to regex-based GenericAnalyzer when the grammars are not installed.

Example:
    >>> from codenav.js_ts_analyzer import JavaScriptAnalyzer
    >>> analyzer = JavaScriptAnalyzer('calc.js', 'function add(a, b) { return a + b; }')
    >>> symbols = analyzer.analyze()

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install codenav[ast]
"""

from dataclasses import replace

from .languages import registry
from .languages.extractor import TreeSitterExtractor
from .languages.javascript import SPEC as _JS_SPEC
from .languages.typescript import SPEC as _TS_SPEC

TREE_SITTER_AVAILABLE = registry.is_available("javascript") and registry.is_available("typescript")

# The is_tsx flag (not the file path) picks the dialect, as it always did.
_TS_PLAIN_SPEC = replace(_TS_SPEC, grammar="typescript", grammar_for_path=None)
_TSX_SPEC = replace(_TS_SPEC, grammar="tsx", grammar_for_path=None)


class JavaScriptAnalyzer(TreeSitterExtractor):
    """Analyzes JavaScript/JSX files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str, is_jsx: bool = False):
        # JSX parses with the same "javascript" grammar; the flag is informational.
        super().__init__(file_path, source, _JS_SPEC)
        self.is_jsx = is_jsx


class TypeScriptAnalyzer(JavaScriptAnalyzer):
    """Analyzes TypeScript/TSX files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str, is_tsx: bool = False):
        TreeSitterExtractor.__init__(
            self, file_path, source, _TSX_SPEC if is_tsx else _TS_PLAIN_SPEC
        )
        self.is_jsx = is_tsx
        self.is_tsx = is_tsx
