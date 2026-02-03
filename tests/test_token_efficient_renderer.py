#!/usr/bin/env python3
"""Tests for the TokenEfficientRenderer module."""

import json

import pytest

from codenav.token_efficient_renderer import (
    FileMicroMeta,
    HubLevel,
    TokenEfficientRenderer,
    TreeNode,
    render_skeleton_tree,
)


@pytest.fixture
def sample_code_map():
    """Create a sample code map for testing."""
    return {
        "version": "1.0",
        "root": "/project/my-app",
        "files": {
            "src/api/client.py": {
                "hash": "abc123",
                "symbols": [
                    {"name": "APIClient", "type": "class", "lines": [10, 50]},
                    {"name": "get", "type": "method", "parent": "APIClient", "lines": [15, 25]},
                    {"name": "post", "type": "method", "parent": "APIClient", "lines": [27, 40]},
                    {"name": "delete", "type": "method", "parent": "APIClient", "lines": [42, 50]},
                ],
            },
            "src/api/routes.py": {
                "hash": "def456",
                "symbols": [
                    {"name": "handle_request", "type": "function", "lines": [5, 20]},
                    {"name": "validate", "type": "function", "lines": [22, 35]},
                ],
            },
            "src/core/config.py": {
                "hash": "ghi789",
                "symbols": [
                    {"name": "Config", "type": "class", "lines": [8, 60]},
                    {"name": "load", "type": "method", "parent": "Config", "lines": [12, 30]},
                    {"name": "save", "type": "method", "parent": "Config", "lines": [32, 50]},
                    {"name": "validate", "type": "method", "parent": "Config", "lines": [52, 60]},
                ],
            },
            "src/core/utils.py": {
                "hash": "jkl012",
                "symbols": [
                    {"name": "helper", "type": "function", "lines": [3, 10]},
                    {"name": "format_date", "type": "function", "lines": [12, 20]},
                    {"name": "_private_func", "type": "function", "lines": [22, 30]},
                ],
            },
            "tests/test_api.py": {
                "hash": "mno345",
                "symbols": [
                    {"name": "test_client", "type": "function", "lines": [5, 15]},
                    {"name": "test_routes", "type": "function", "lines": [17, 30]},
                ],
            },
        },
        "stats": {
            "files_processed": 5,
            "symbols_found": 12,
        },
    }


@pytest.fixture
def code_map_file(tmp_path, sample_code_map):
    """Write sample code map to a temp file."""
    file_path = tmp_path / ".codenav.json"
    file_path.write_text(json.dumps(sample_code_map, indent=2))
    return str(file_path)


class TestFileMicroMeta:
    """Tests for FileMicroMeta dataclass."""

    def test_hub_level_none(self):
        """Test no hub status."""
        meta = FileMicroMeta(path="test.py", importers_count=1)
        assert meta.hub_level == HubLevel.NONE

    def test_hub_level_low(self):
        """Test low hub status."""
        meta = FileMicroMeta(path="test.py", importers_count=2)
        assert meta.hub_level == HubLevel.LOW

    def test_hub_level_medium(self):
        """Test medium hub status."""
        meta = FileMicroMeta(path="test.py", importers_count=3)
        assert meta.hub_level == HubLevel.MEDIUM

    def test_hub_level_high(self):
        """Test high hub status."""
        meta = FileMicroMeta(path="test.py", importers_count=5)
        assert meta.hub_level == HubLevel.HIGH

    def test_hub_level_critical(self):
        """Test critical hub status."""
        meta = FileMicroMeta(path="test.py", importers_count=10)
        assert meta.hub_level == HubLevel.CRITICAL

    def test_format_micro_with_class(self):
        """Test micro format with class and methods."""
        meta = FileMicroMeta(
            path="client.py",
            classes=["APIClient"],
            methods={"APIClient": ["get", "post", "delete"]},
            importers_count=5,
        )
        result = meta.format_micro()
        assert "C:APIClient" in result
        assert "M:get,post,delete" in result
        assert "(5←)" in result

    def test_format_micro_with_functions(self):
        """Test micro format with standalone functions."""
        meta = FileMicroMeta(
            path="utils.py",
            functions=["helper", "format_date"],
            importers_count=2,
        )
        result = meta.format_micro()
        assert "F:helper,format_date" in result
        assert "(2←)" in result

    def test_format_micro_empty(self):
        """Test micro format with no symbols."""
        meta = FileMicroMeta(path="empty.py")
        result = meta.format_micro()
        assert result == ""

    def test_format_micro_truncation(self):
        """Test micro format truncation for long content."""
        meta = FileMicroMeta(
            path="big.py",
            classes=["VeryLongClassNameThatExceedsNormalWidth"],
            methods={"VeryLongClassNameThatExceedsNormalWidth": ["method1", "method2", "method3"]},
        )
        result = meta.format_micro(max_width=30)
        assert len(result) <= 35  # Some tolerance


class TestTreeNode:
    """Tests for TreeNode dataclass."""

    def test_get_stats_file(self):
        """Test stats for a file node."""
        meta = FileMicroMeta(
            path="test.py",
            classes=["MyClass"],
            functions=["func1", "func2"],
            importers_count=5,
        )
        node = TreeNode(name="test.py", is_file=True, meta=meta)
        files, symbols, hubs = node.get_stats()
        assert files == 1
        assert symbols == 3  # 1 class + 2 functions
        assert hubs == 1  # importers >= 3

    def test_get_stats_directory(self):
        """Test stats for a directory node."""
        file1 = TreeNode(
            name="a.py",
            is_file=True,
            meta=FileMicroMeta(path="a.py", classes=["A"], importers_count=5),
        )
        file2 = TreeNode(
            name="b.py", is_file=True, meta=FileMicroMeta(path="b.py", functions=["b1", "b2"])
        )
        dir_node = TreeNode(name="src", children={"a.py": file1, "b.py": file2})

        files, symbols, hubs = dir_node.get_stats()
        assert files == 2
        assert symbols == 3  # 1 class + 2 functions
        assert hubs == 1  # Only a.py is a hub


class TestTokenEfficientRenderer:
    """Tests for TokenEfficientRenderer class."""

    def test_init_from_dict(self, sample_code_map):
        """Test initialization from dict."""
        renderer = TokenEfficientRenderer(sample_code_map)
        assert len(renderer.files) == 5
        assert renderer.tree is not None

    def test_init_from_file(self, code_map_file):
        """Test initialization from file."""
        renderer = TokenEfficientRenderer.from_file(code_map_file)
        assert len(renderer.files) == 5

    def test_parse_classes(self, sample_code_map):
        """Test that classes are parsed correctly."""
        renderer = TokenEfficientRenderer(sample_code_map)
        client_meta = renderer.files["src/api/client.py"]
        assert "APIClient" in client_meta.classes

    def test_parse_methods(self, sample_code_map):
        """Test that methods are parsed correctly."""
        renderer = TokenEfficientRenderer(sample_code_map)
        client_meta = renderer.files["src/api/client.py"]
        assert "APIClient" in client_meta.methods
        assert "get" in client_meta.methods["APIClient"]

    def test_parse_functions(self, sample_code_map):
        """Test that functions are parsed correctly."""
        renderer = TokenEfficientRenderer(sample_code_map)
        routes_meta = renderer.files["src/api/routes.py"]
        assert "handle_request" in routes_meta.functions

    def test_detect_test_files(self, sample_code_map):
        """Test that test files are detected."""
        renderer = TokenEfficientRenderer(sample_code_map)
        test_meta = renderer.files["tests/test_api.py"]
        assert test_meta.has_tests

    def test_render_skeleton_tree(self, sample_code_map):
        """Test basic tree rendering."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree()

        # Check structure
        assert "my-app/" in output
        assert "src/" in output
        assert "api/" in output
        assert "client.py" in output
        assert "═══ Summary ═══" in output

    def test_render_with_meta(self, sample_code_map):
        """Test tree rendering includes micro-metadata."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree(show_meta=True)

        # Should include class info
        assert "C:APIClient" in output or "C:Config" in output

    def test_render_without_meta(self, sample_code_map):
        """Test tree rendering without meta."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree(show_meta=False)

        # Should not include class markers
        assert "[C:" not in output

    def test_render_without_summary(self, sample_code_map):
        """Test tree rendering without summary."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree(show_summary=False)

        assert "═══ Summary ═══" not in output

    def test_render_with_depth_limit(self, sample_code_map):
        """Test tree rendering with depth limit."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree(max_depth=1)

        # Should show directories but collapse deeper content
        assert "src/" in output

    def test_render_custom_project_name(self, sample_code_map):
        """Test tree rendering with custom project name."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree(project_name="custom-name")

        assert "custom-name/" in output

    def test_render_compact_index(self, sample_code_map):
        """Test compact index rendering."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_compact_index()

        # Should list symbols compactly
        assert "client" in output.lower() or "config" in output.lower()

    def test_render_compact_index_by_type(self, sample_code_map):
        """Test compact index grouped by type."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_compact_index(group_by="type")

        assert "Classes:" in output or "Functions:" in output


class TestTokenStats:
    """Tests for token statistics."""

    def test_get_token_stats(self, sample_code_map):
        """Test token statistics calculation."""
        renderer = TokenEfficientRenderer(sample_code_map)
        stats = renderer.get_token_stats()

        assert "json_chars" in stats
        assert "tree_chars" in stats
        assert "savings_percent" in stats

        # Tree should be more compact than JSON
        assert stats["tree_chars"] < stats["json_chars"]
        assert stats["savings_percent"] > 0

    def test_significant_savings(self, sample_code_map):
        """Test that savings are significant."""
        renderer = TokenEfficientRenderer(sample_code_map)
        stats = renderer.get_token_stats()

        # Should save at least 30%
        assert stats["savings_percent"] >= 30


class TestConvenienceFunction:
    """Tests for the convenience function."""

    def test_render_from_dict(self, sample_code_map):
        """Test convenience function with dict."""
        output = render_skeleton_tree(sample_code_map)
        assert "my-app/" in output

    def test_render_from_file(self, code_map_file):
        """Test convenience function with file path."""
        output = render_skeleton_tree(code_map_file)
        assert "my-app/" in output

    def test_render_with_options(self, sample_code_map):
        """Test convenience function with options."""
        output = render_skeleton_tree(
            sample_code_map, max_depth=2, show_meta=False, project_name="test-project"
        )
        assert "test-project/" in output


class TestOutputQuality:
    """Tests for output quality and formatting."""

    def test_tree_connectors(self, sample_code_map):
        """Test that tree uses proper connectors."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree()

        # Should have tree connectors
        assert "├──" in output or "└──" in output

    def test_directory_slash(self, sample_code_map):
        """Test that directories end with slash."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree()

        # Directories should have trailing slash
        assert "src/" in output

    def test_no_trailing_whitespace(self, sample_code_map):
        """Test no trailing whitespace on lines."""
        renderer = TokenEfficientRenderer(sample_code_map)
        output = renderer.render_skeleton_tree()

        for line in output.split("\n"):
            assert line == line.rstrip(), f"Trailing whitespace on: {repr(line)}"
