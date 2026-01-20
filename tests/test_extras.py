"""Tests for extra features: completions, watcher, and exporters."""

import json
import tempfile
from pathlib import Path

import pytest

from code_map_navigator.completions import (
    generate_bash_completion,
    generate_zsh_completion,
    get_symbols_from_map,
)
from code_map_navigator.exporters import (
    GraphVizExporter,
    HTMLExporter,
    MarkdownExporter,
    get_exporter,
)
from code_map_navigator.watcher import CodeMapWatcher


@pytest.fixture
def sample_codemap(tmp_path):
    """Create a sample code map file for testing."""
    codemap = {
        "version": "1.0",
        "root": str(tmp_path),
        "generated_at": "2024-01-15T10:00:00",
        "stats": {
            "files_processed": 2,
            "symbols_found": 5,
            "errors": 0,
        },
        "files": {
            "src/main.py": {
                "hash": "abc123",
                "symbols": [
                    {
                        "name": "main",
                        "type": "function",
                        "lines": [10, 20],
                        "signature": "def main() -> None",
                        "deps": ["setup", "run"],
                    },
                    {
                        "name": "setup",
                        "type": "function",
                        "lines": [25, 35],
                        "signature": "def setup(config: dict) -> None",
                    },
                ],
            },
            "src/utils.py": {
                "hash": "def456",
                "symbols": [
                    {
                        "name": "Helper",
                        "type": "class",
                        "lines": [5, 50],
                        "signature": "class Helper",
                    },
                    {
                        "name": "process",
                        "type": "method",
                        "lines": [10, 30],
                        "signature": "def process(self, data)",
                        "parent": "Helper",
                    },
                    {
                        "name": "validate",
                        "type": "function",
                        "lines": [55, 70],
                        "signature": "def validate(data: dict) -> bool",
                    },
                ],
            },
        },
        "index": {
            "main": [{"file": "src/main.py", "type": "function", "lines": [10, 20]}],
            "setup": [{"file": "src/main.py", "type": "function", "lines": [25, 35]}],
            "helper": [{"file": "src/utils.py", "type": "class", "lines": [5, 50]}],
        },
    }

    map_path = tmp_path / ".codemap.json"
    map_path.write_text(json.dumps(codemap))
    return str(map_path)


class TestCompletions:
    """Tests for shell completion generation."""

    def test_generate_bash_completion(self):
        """Test bash completion script generation."""
        script = generate_bash_completion()

        assert "#!/bin/bash" not in script  # Not a standalone script
        assert "_codemap_completions" in script
        assert "complete -F _codemap_completions codemap" in script
        assert "map" in script
        assert "search" in script
        assert "export" in script
        assert "watch" in script

    def test_generate_zsh_completion(self):
        """Test zsh completion script generation."""
        script = generate_zsh_completion()

        assert "#compdef codemap" in script
        assert "_codemap()" in script
        assert "map:" in script
        assert "search:" in script
        assert "export:" in script
        assert "watch:" in script

    def test_get_symbols_from_map(self, sample_codemap):
        """Test extracting symbols from a code map."""
        symbols = get_symbols_from_map(sample_codemap)

        assert isinstance(symbols, list)
        assert "main" in symbols
        assert "setup" in symbols
        assert "Helper" in symbols

    def test_get_symbols_from_nonexistent_map(self):
        """Test extracting symbols from a nonexistent file."""
        symbols = get_symbols_from_map("/nonexistent/path.json")
        assert symbols == []

    def test_get_symbols_limit(self, sample_codemap):
        """Test symbol extraction with limit."""
        symbols = get_symbols_from_map(sample_codemap, limit=2)
        assert len(symbols) <= 2


class TestMarkdownExporter:
    """Tests for Markdown export."""

    def test_markdown_export(self, sample_codemap):
        """Test basic Markdown export."""
        exporter = MarkdownExporter(sample_codemap)
        markdown = exporter.export()

        assert "# Code Map:" in markdown
        assert "## Statistics" in markdown
        assert "**Files:** 2" in markdown
        assert "**Symbols:** 5" in markdown
        assert "## Files" in markdown
        assert "`src/main.py`" in markdown
        assert "`main`" in markdown

    def test_markdown_has_symbol_index(self, sample_codemap):
        """Test that Markdown export includes symbol index."""
        exporter = MarkdownExporter(sample_codemap)
        markdown = exporter.export()

        assert "## Symbol Index" in markdown

    def test_markdown_export_to_file(self, sample_codemap, tmp_path):
        """Test exporting Markdown to a file."""
        output_path = tmp_path / "output.md"
        exporter = MarkdownExporter(sample_codemap)
        exporter.export_to_file(str(output_path))

        assert output_path.exists()
        content = output_path.read_text()
        assert "# Code Map:" in content


class TestHTMLExporter:
    """Tests for HTML export."""

    def test_html_export(self, sample_codemap):
        """Test basic HTML export."""
        exporter = HTMLExporter(sample_codemap)
        html = exporter.export()

        assert "<!DOCTYPE html>" in html
        assert "<title>Code Map:" in html
        assert "src/main.py" in html
        assert "main" in html

    def test_html_has_styles(self, sample_codemap):
        """Test that HTML export includes styles."""
        exporter = HTMLExporter(sample_codemap)
        html = exporter.export()

        assert "<style>" in html
        assert "</style>" in html

    def test_html_has_javascript(self, sample_codemap):
        """Test that HTML export includes JavaScript."""
        exporter = HTMLExporter(sample_codemap)
        html = exporter.export()

        assert "<script>" in html
        assert "</script>" in html


class TestGraphVizExporter:
    """Tests for GraphViz export."""

    def test_graphviz_export(self, sample_codemap):
        """Test basic GraphViz export."""
        exporter = GraphVizExporter(sample_codemap)
        dot = exporter.export()

        assert "digraph CodeMap {" in dot
        assert "rankdir=LR;" in dot
        assert "}" in dot

    def test_graphviz_has_nodes(self, sample_codemap):
        """Test that GraphViz export includes nodes."""
        exporter = GraphVizExporter(sample_codemap)
        dot = exporter.export()

        assert "main" in dot
        assert "Helper" in dot

    def test_graphviz_has_clusters(self, sample_codemap):
        """Test that GraphViz export includes file clusters."""
        exporter = GraphVizExporter(sample_codemap)
        dot = exporter.export()

        assert "subgraph cluster_" in dot


class TestGetExporter:
    """Tests for the get_exporter factory function."""

    def test_get_markdown_exporter(self, sample_codemap):
        """Test getting Markdown exporter."""
        exporter = get_exporter("markdown", sample_codemap)
        assert isinstance(exporter, MarkdownExporter)

    def test_get_md_exporter(self, sample_codemap):
        """Test getting Markdown exporter with 'md' alias."""
        exporter = get_exporter("md", sample_codemap)
        assert isinstance(exporter, MarkdownExporter)

    def test_get_html_exporter(self, sample_codemap):
        """Test getting HTML exporter."""
        exporter = get_exporter("html", sample_codemap)
        assert isinstance(exporter, HTMLExporter)

    def test_get_graphviz_exporter(self, sample_codemap):
        """Test getting GraphViz exporter."""
        exporter = get_exporter("graphviz", sample_codemap)
        assert isinstance(exporter, GraphVizExporter)

    def test_get_dot_exporter(self, sample_codemap):
        """Test getting GraphViz exporter with 'dot' alias."""
        exporter = get_exporter("dot", sample_codemap)
        assert isinstance(exporter, GraphVizExporter)

    def test_invalid_format(self, sample_codemap):
        """Test getting exporter with invalid format."""
        with pytest.raises(ValueError):
            get_exporter("invalid", sample_codemap)


class TestCodeMapWatcher:
    """Tests for the CodeMapWatcher."""

    def test_watcher_initialization(self, tmp_path):
        """Test watcher initialization."""
        watcher = CodeMapWatcher(str(tmp_path))

        assert watcher.root_path == tmp_path
        assert watcher.debounce == 1.0
        assert watcher._running is False

    def test_watcher_with_options(self, tmp_path):
        """Test watcher with custom options."""
        watcher = CodeMapWatcher(
            str(tmp_path),
            output_path="custom.json",
            debounce=2.0,
            git_only=True,
            use_gitignore=True,
            compact=True,
        )

        assert "custom.json" in watcher.output_path
        assert watcher.debounce == 2.0
        assert watcher.git_only is True
        assert watcher.use_gitignore is True
        assert watcher.compact is True

    def test_watcher_get_watched_files(self, tmp_path):
        """Test getting watched files."""
        # Create some test files
        (tmp_path / "main.py").write_text("def hello(): pass")
        (tmp_path / "utils.js").write_text("function test() {}")
        (tmp_path / "readme.txt").write_text("Not a code file")

        watcher = CodeMapWatcher(str(tmp_path))
        files = watcher._get_watched_files()

        # Should include .py and .js files
        file_names = [f.name for f in files]
        assert "main.py" in file_names
        assert "utils.js" in file_names
        # Should not include .txt
        assert "readme.txt" not in file_names

    def test_watcher_should_ignore(self, tmp_path):
        """Test ignore patterns."""
        watcher = CodeMapWatcher(str(tmp_path))

        # Should ignore node_modules
        assert watcher._should_ignore(tmp_path / "node_modules" / "test.js") is True

        # Should ignore __pycache__
        assert watcher._should_ignore(tmp_path / "__pycache__" / "test.pyc") is True

        # Should not ignore regular files
        assert watcher._should_ignore(tmp_path / "main.py") is False

    def test_watcher_hash_file(self, tmp_path):
        """Test file hashing."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        watcher = CodeMapWatcher(str(tmp_path))
        hash1 = watcher._hash_file(test_file)

        assert hash1 is not None
        assert len(hash1) == 12

        # Same content should produce same hash
        hash2 = watcher._hash_file(test_file)
        assert hash1 == hash2

        # Different content should produce different hash
        test_file.write_text("def goodbye(): pass")
        hash3 = watcher._hash_file(test_file)
        assert hash1 != hash3

    def test_watcher_check_for_changes(self, tmp_path):
        """Test change detection."""
        test_file = tmp_path / "main.py"
        test_file.write_text("def hello(): pass")

        watcher = CodeMapWatcher(str(tmp_path))

        # Initial check should detect no changes (empty state)
        # but will add files to tracking
        watcher._check_for_changes()

        # Second check with no changes
        assert watcher._check_for_changes() is False

        # Modify file
        test_file.write_text("def goodbye(): pass")
        assert watcher._check_for_changes() is True

    def test_watcher_stop(self, tmp_path):
        """Test watcher stop method."""
        watcher = CodeMapWatcher(str(tmp_path))
        watcher._running = True
        watcher.stop()
        assert watcher._running is False
