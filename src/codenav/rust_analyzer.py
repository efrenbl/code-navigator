"""Rust analyzer — thin shim over the spec-driven extractor.

Deprecated import path kept for backward compatibility: the extraction logic
now lives in :mod:`codenav.languages.rust` (declarative spec) and
:class:`codenav.languages.extractor.TreeSitterExtractor`.

Falls back to regex-based GenericAnalyzer when no Rust grammar is installed.

Example:
    >>> from codenav.rust_analyzer import RustAnalyzer
    >>> analyzer = RustAnalyzer('lib.rs', 'pub fn greet() {}')
    >>> symbols = analyzer.analyze()

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install codenav[ast]
"""

from .languages import registry
from .languages.extractor import TreeSitterExtractor
from .languages.rust import SPEC as _RUST_SPEC

TREE_SITTER_AVAILABLE = registry.is_available("rust")


class RustAnalyzer(TreeSitterExtractor):
    """Analyzes Rust files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str):
        super().__init__(file_path, source, _RUST_SPEC)
