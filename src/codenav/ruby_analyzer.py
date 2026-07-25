"""Ruby analyzer — thin shim over the spec-driven extractor.

Deprecated import path kept for backward compatibility: the extraction logic
now lives in :mod:`codenav.languages.ruby` (declarative spec) and
:class:`codenav.languages.extractor.TreeSitterExtractor`.

Falls back to regex-based GenericAnalyzer when no Ruby grammar is installed.

Example:
    >>> from codenav.ruby_analyzer import RubyAnalyzer
    >>> analyzer = RubyAnalyzer('user.rb', 'def greet\\n  "hi"\\nend')
    >>> symbols = analyzer.analyze()

Installation:
    To enable AST support, install with the 'ast' extra:
        pip install codenav[ast]
"""

from .languages import registry
from .languages.extractor import TreeSitterExtractor
from .languages.ruby import SPEC as _RUBY_SPEC

TREE_SITTER_AVAILABLE = registry.is_available("ruby")


class RubyAnalyzer(TreeSitterExtractor):
    """Analyzes Ruby files using tree-sitter for accurate symbol extraction."""

    def __init__(self, file_path: str, source: str):
        super().__init__(file_path, source, _RUBY_SPEC)
