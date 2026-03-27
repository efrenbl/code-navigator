"""Tests to verify core library imports work independently of optional dependencies.

These tests ensure that `codenav` can be used as a pure Python library
(e.g. from kmlp-mcp) without requiring the MCP SDK or other optional deps.
"""

import importlib


class TestCoreImports:
    """Verify that core classes are importable from the top-level package."""

    def test_code_navigator_import(self):
        from codenav import CodeNavigator

        assert CodeNavigator is not None

    def test_code_searcher_import(self):
        from codenav import CodeSearcher

        assert CodeSearcher is not None

    def test_line_reader_import(self):
        from codenav import LineReader

        assert LineReader is not None

    def test_token_efficient_renderer_import(self):
        from codenav import TokenEfficientRenderer

        assert TokenEfficientRenderer is not None

    def test_import_resolver_import(self):
        from codenav import ImportResolver

        assert ImportResolver is not None

    def test_symbol_dataclass_import(self):
        from codenav import Symbol

        assert Symbol is not None

    def test_search_result_dataclass_import(self):
        from codenav import SearchResult

        assert SearchResult is not None

    def test_compute_content_hash_import(self):
        from codenav import compute_content_hash

        result = compute_content_hash("test")
        assert isinstance(result, str)
        assert len(result) == 12

    def test_feature_flags_available(self):
        from codenav import HAS_NETWORKX, TREE_SITTER_AVAILABLE

        assert isinstance(HAS_NETWORKX, bool)
        assert isinstance(TREE_SITTER_AVAILABLE, bool)


class TestMCPOptional:
    """Verify that MCP module handles missing dependencies gracefully."""

    def test_mcp_available_flag_exists(self):
        from codenav.mcp import MCP_AVAILABLE

        assert isinstance(MCP_AVAILABLE, bool)

    def test_mcp_module_importable(self):
        """MCP submodule should always be importable, even without mcp SDK."""
        mod = importlib.import_module("codenav.mcp")
        assert hasattr(mod, "MCP_AVAILABLE")


class TestDirectModuleImports:
    """Verify core modules can be imported directly without MCP."""

    def test_code_navigator_module(self):
        mod = importlib.import_module("codenav.code_navigator")
        assert hasattr(mod, "CodeNavigator")

    def test_code_search_module(self):
        mod = importlib.import_module("codenav.code_search")
        assert hasattr(mod, "CodeSearcher")

    def test_line_reader_module(self):
        mod = importlib.import_module("codenav.line_reader")
        assert hasattr(mod, "LineReader")

    def test_token_efficient_renderer_module(self):
        mod = importlib.import_module("codenav.token_efficient_renderer")
        assert hasattr(mod, "TokenEfficientRenderer")

    def test_import_resolver_module(self):
        mod = importlib.import_module("codenav.import_resolver")
        assert hasattr(mod, "ImportResolver")

    def test_exporters_module(self):
        mod = importlib.import_module("codenav.exporters")
        assert hasattr(mod, "MarkdownExporter")

    def test_watcher_module(self):
        mod = importlib.import_module("codenav.watcher")
        assert hasattr(mod, "CodenavWatcher")
