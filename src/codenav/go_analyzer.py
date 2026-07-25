"""Go analyzer — thin shim over the spec-driven extractor.

Deprecated import path kept for backward compatibility: the extraction logic
now lives in :mod:`codenav.languages.go` (declarative spec) and
:class:`codenav.languages.extractor.TreeSitterExtractor`.

Falls back to regex-based GenericAnalyzer when no Go grammar is installed.

Example:
    >>> from codenav.go_analyzer import GoAnalyzer
    >>> analyzer = GoAnalyzer('example.go', 'func greet() string { return "hi" }')
    >>> symbols = analyzer.analyze()

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install codenav[ast]
"""

from .languages import registry
from .languages.extractor import TreeSitterExtractor
from .languages.go import SPEC as _GO_SPEC

TREE_SITTER_AVAILABLE = registry.is_available("go")


class GoAnalyzer(TreeSitterExtractor):
    """Analyzes Go files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str):
        super().__init__(file_path, source, _GO_SPEC)
