"""Dart/Flutter analyzer — thin shim over the spec-driven extractor.

Deprecated import path kept for backward compatibility: the extraction logic
now lives in :mod:`codenav.languages.dart` (declarative spec) and
:class:`codenav.languages.extractor.TreeSitterExtractor`.

Falls back to regex-based GenericAnalyzer when no Dart grammar is installed.
Flutter needs no separate grammar: Flutter widgets are ordinary Dart classes.

Example:
    >>> from codenav.dart_analyzer import DartAnalyzer
    >>> analyzer = DartAnalyzer('main.dart', 'class MyWidget {}')
    >>> symbols = analyzer.analyze()

Installation:
    To enable AST support, install with the 'ast' or 'dart' extra:
        pip install codenav[dart]
"""

from .languages import registry
from .languages.dart import SPEC as _DART_SPEC
from .languages.extractor import TreeSitterExtractor

TREE_SITTER_AVAILABLE = registry.is_available("dart")

# Loaded Language object, kept under its historical name for direct-parse users.
_DART_LANGUAGE = registry.get_language("dart")


class DartAnalyzer(TreeSitterExtractor):
    """Analyzes Dart/Flutter files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str):
        super().__init__(file_path, source, _DART_SPEC)
