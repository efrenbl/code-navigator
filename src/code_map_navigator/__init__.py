"""Claude Code Navigator - Token-efficient code navigation for large codebases.

This package provides tools for creating structural maps of codebases and
navigating them efficiently, reducing token usage by up to 97% when working
with AI coding assistants.

Components:
    - CodeMapper: Generates JSON index of codebase structure
    - CodeSearcher: Searches the pre-built index for symbols
    - LineReader: Reads specific lines from files efficiently

Quick Start:
    1. Generate a code map:
        >>> from code_map_navigator import CodeMapper
        >>> mapper = CodeMapper('/path/to/project')
        >>> code_map = mapper.scan()

    2. Search for symbols:
        >>> from code_map_navigator import CodeSearcher
        >>> searcher = CodeSearcher('.codemap.json')
        >>> results = searcher.search_symbol('process_payment')

    3. Read specific lines:
        >>> from code_map_navigator import LineReader
        >>> reader = LineReader()
        >>> content = reader.read_lines('src/api.py', 45, 60)

Example:
    >>> # Full workflow
    >>> from code_map_navigator import CodeMapper, CodeSearcher, LineReader
    >>>
    >>> # Step 1: Map the codebase (one-time)
    >>> mapper = CodeMapper('/my/project')
    >>> mapper.scan()
    >>>
    >>> # Step 2: Search for a symbol
    >>> searcher = CodeSearcher('/my/project/.codemap.json')
    >>> results = searcher.search_symbol('authenticate', symbol_type='function')
    >>> print(results[0].file, results[0].lines)
    'src/auth.py' [45, 89]
    >>>
    >>> # Step 3: Read only those lines
    >>> reader = LineReader('/my/project')
    >>> content = reader.read_symbol('src/auth.py', 45, 89)
"""

__version__ = "1.2.0"
__author__ = "Efren"
__license__ = "MIT"

from .code_mapper import CodeMapper, GenericAnalyzer, PythonAnalyzer, Symbol
from .code_search import CodeSearcher, SearchResult
from .line_reader import LineReader

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__license__",
    # Main classes
    "CodeMapper",
    "CodeSearcher",
    "LineReader",
    # Supporting classes
    "PythonAnalyzer",
    "GenericAnalyzer",
    "Symbol",
    "SearchResult",
]
