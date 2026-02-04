"""Code Navigator - Token-efficient code navigation for large codebases.

This package provides tools for creating structural maps of codebases and
navigating them efficiently, reducing token usage by up to 97% when working
with AI coding assistants.

Components:
    - CodeNavigator: Generates JSON index of codebase structure
    - CodeSearcher: Searches the pre-built index for symbols
    - LineReader: Reads specific lines from files efficiently

Quick Start:
    1. Generate a code map:
        >>> from codenav import CodeNavigator
        >>> mapper = CodeNavigator('/path/to/project')
        >>> code_map = mapper.scan()

    2. Search for symbols:
        >>> from codenav import CodeSearcher
        >>> searcher = CodeSearcher('.codenav.json')
        >>> results = searcher.search_symbol('process_payment')

    3. Read specific lines:
        >>> from codenav import LineReader
        >>> reader = LineReader()
        >>> content = reader.read_lines('src/api.py', 45, 60)

Example:
    >>> # Full workflow
    >>> from codenav import CodeNavigator, CodeSearcher, LineReader
    >>>
    >>> # Step 1: Map the codebase (one-time)
    >>> mapper = CodeNavigator('/my/project')
    >>> mapper.scan()
    >>>
    >>> # Step 2: Search for a symbol
    >>> searcher = CodeSearcher('/my/project/.codenav.json')
    >>> results = searcher.search_symbol('authenticate', symbol_type='function')
    >>> print(results[0].file, results[0].lines)
    'src/auth.py' [45, 89]
    >>>
    >>> # Step 3: Read only those lines
    >>> reader = LineReader('/my/project')
    >>> content = reader.read_symbol('src/auth.py', 45, 89)
"""

import hashlib

from .code_navigator import CodeNavigator, GenericAnalyzer, GitIntegration, PythonAnalyzer, Symbol
from .code_search import CodeSearcher, SearchResult
from .completions import generate_bash_completion, generate_zsh_completion
from .exporters import GraphVizExporter, HTMLExporter, MarkdownExporter, get_exporter
from .js_ts_analyzer import (
    TREE_SITTER_AVAILABLE,
    JavaScriptAnalyzer,
    TypeScriptAnalyzer,
)
from .line_reader import LineReader
from .watcher import CodenavWatcher

# Optional dependency: networkx for DependencyGraph
try:
    from .dependency_graph import DependencyGraph, FileNode, analyze_repository

    HAS_NETWORKX = True
except ImportError:
    DependencyGraph = None  # type: ignore
    FileNode = None  # type: ignore
    analyze_repository = None  # type: ignore
    HAS_NETWORKX = False

# Import resolver (always available - no external dependencies)
from .import_resolver import (
    AliasConfig,
    ImportResolver,
    ResolveResult,
    ResolveStrategy,
    resolve_import_path,
)

# Token-efficient rendering (always available - no external dependencies)
from .token_efficient_renderer import (
    FileMicroMeta,
    HubLevel,
    TokenEfficientRenderer,
    render_skeleton_tree,
)

# Optional: ast-grep high-performance analyzer
try:
    from .ast_grep_analyzer import (
        AstGrepAnalyzer,
        AstGrepSymbol,
        analyze_with_ast_grep,
        is_ast_grep_available,
    )

    HAS_AST_GREP = is_ast_grep_available()
except ImportError:
    AstGrepAnalyzer = None  # type: ignore
    AstGrepSymbol = None  # type: ignore
    analyze_with_ast_grep = None  # type: ignore

    def is_ast_grep_available():
        return False  # type: ignore

    HAS_AST_GREP = False

__version__ = "2.0.0"
__author__ = "Efren"
__license__ = "MIT"


def compute_content_hash(content: str) -> str:
    """Compute a short hash of content for change detection.

    This is the canonical hash function used across all modules for
    consistent file change detection.

    Args:
        content: The text content to hash.

    Returns:
        A 12-character MD5 hash string.

    Example:
        >>> compute_content_hash("def foo(): pass")
        'a1b2c3d4e5f6'
    """
    return hashlib.md5(content.encode()).hexdigest()[:12]


__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__license__",
    # Main classes
    "CodeNavigator",
    "CodeSearcher",
    "LineReader",
    "CodenavWatcher",
    # Dependency Graph (requires networkx)
    "DependencyGraph",
    "FileNode",
    "analyze_repository",
    # Import Resolution
    "ImportResolver",
    "ResolveResult",
    "ResolveStrategy",
    "AliasConfig",
    "resolve_import_path",
    # Token-Efficient Rendering
    "TokenEfficientRenderer",
    "FileMicroMeta",
    "HubLevel",
    "render_skeleton_tree",
    # AST-Grep Analyzer (optional, requires ast-grep-py)
    "AstGrepAnalyzer",
    "AstGrepSymbol",
    "analyze_with_ast_grep",
    "is_ast_grep_available",
    "HAS_AST_GREP",
    # Analyzers
    "PythonAnalyzer",
    "GenericAnalyzer",
    "JavaScriptAnalyzer",
    "TypeScriptAnalyzer",
    # Exporters
    "MarkdownExporter",
    "HTMLExporter",
    "GraphVizExporter",
    "get_exporter",
    # Supporting classes
    "GitIntegration",
    "Symbol",
    "SearchResult",
    # Completions
    "generate_bash_completion",
    "generate_zsh_completion",
    # Feature flags
    "TREE_SITTER_AVAILABLE",
    "HAS_NETWORKX",
    # Utilities
    "compute_content_hash",
]
