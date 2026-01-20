"""Tests for the unified CLI module."""

import argparse
import json
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from code_map_navigator.cli import main
from code_map_navigator.code_mapper import add_map_arguments, run_map
from code_map_navigator.code_search import add_search_arguments, run_search
from code_map_navigator.line_reader import add_read_arguments, run_read


class TestCLIHelp:
    """Tests for CLI help and version output."""

    def test_main_help(self):
        """Test that main help displays available commands."""
        with patch.object(sys, "argv", ["codemap", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_version(self):
        """Test that version is displayed correctly."""
        with patch.object(sys, "argv", ["codemap", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_map_help(self):
        """Test map subcommand help."""
        with patch.object(sys, "argv", ["codemap", "map", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_search_help(self):
        """Test search subcommand help."""
        with patch.object(sys, "argv", ["codemap", "search", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_read_help(self):
        """Test read subcommand help."""
        with patch.object(sys, "argv", ["codemap", "read", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_stats_help(self):
        """Test stats subcommand help."""
        with patch.object(sys, "argv", ["codemap", "stats", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_no_command_shows_help(self, capsys):
        """Test that running without a command shows help."""
        with patch.object(sys, "argv", ["codemap"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestAddArgumentsFunctions:
    """Tests for the add_*_arguments helper functions."""

    def test_add_map_arguments(self):
        """Test that map arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_map_arguments(parser)

        # Parse with required argument
        args = parser.parse_args(["/some/path"])
        assert args.path == "/some/path"
        assert args.output == ".codemap.json"
        assert args.ignore is None
        assert args.compact is False
        assert args.no_color is False

    def test_add_map_arguments_with_options(self):
        """Test map arguments with all options."""
        parser = argparse.ArgumentParser()
        add_map_arguments(parser)

        args = parser.parse_args([
            "/some/path",
            "-o", "custom.json",
            "-i", "*.test.py", "*.spec.py",
            "--compact",
            "--no-color"
        ])
        assert args.path == "/some/path"
        assert args.output == "custom.json"
        assert args.ignore == ["*.test.py", "*.spec.py"]
        assert args.compact is True
        assert args.no_color is True

    def test_add_search_arguments(self):
        """Test that search arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)

        # Parse with query
        args = parser.parse_args(["MyClass"])
        assert args.query == "MyClass"
        assert args.map == ".codemap.json"
        assert args.type is None
        assert args.limit == 10
        assert args.no_fuzzy is False

    def test_add_search_arguments_with_options(self):
        """Test search arguments with all options."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)

        args = parser.parse_args([
            "process",
            "-m", "custom.json",
            "-t", "function",
            "-f", "src/",
            "-l", "20",
            "--no-fuzzy",
            "--compact",
            "-o", "table"
        ])
        assert args.query == "process"
        assert args.map == "custom.json"
        assert args.type == "function"
        assert args.file == "src/"
        assert args.limit == 20
        assert args.no_fuzzy is True
        assert args.compact is True
        assert args.output == "table"

    def test_add_search_arguments_stats_mode(self):
        """Test search arguments for stats mode."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)

        args = parser.parse_args(["--stats"])
        assert args.stats is True
        assert args.query is None

    def test_add_read_arguments(self):
        """Test that read arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)

        args = parser.parse_args(["src/api.py", "10-20"])
        assert args.file == "src/api.py"
        assert args.lines == "10-20"
        assert args.context == 0
        assert args.symbol is False

    def test_add_read_arguments_with_options(self):
        """Test read arguments with all options."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)

        args = parser.parse_args([
            "src/api.py",
            "10-20",
            "-r", "/project",
            "-c", "5",
            "--symbol",
            "--max-lines", "50",
            "-o", "code",
            "--compact"
        ])
        assert args.file == "src/api.py"
        assert args.lines == "10-20"
        assert args.root == "/project"
        assert args.context == 5
        assert args.symbol is True
        assert args.max_lines == 50
        assert args.output == "code"
        assert args.compact is True

    def test_add_read_arguments_search_mode(self):
        """Test read arguments for search mode."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)

        args = parser.parse_args(["src/api.py", "-s", "def process"])
        assert args.file == "src/api.py"
        assert args.search == "def process"


class TestMapCommand:
    """Tests for the map subcommand."""

    def test_run_map_creates_codemap(self):
        """Test that run_map creates a code map file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            (Path(tmpdir) / "test.py").write_text("def hello(): pass")

            parser = argparse.ArgumentParser()
            add_map_arguments(parser)
            args = parser.parse_args([tmpdir, "-o", "test.codemap.json"])

            # Capture output
            captured_output = StringIO()
            with patch("sys.stdout", captured_output), patch("sys.stderr", StringIO()):
                run_map(args)

            # Check that the map file was created
            output_path = Path(tmpdir) / "test.codemap.json"
            assert output_path.exists()

            # Verify contents
            with open(output_path) as f:
                data = json.load(f)
            assert "version" in data
            assert "files" in data
            assert "index" in data

    def test_run_map_compact_output(self):
        """Test that compact flag produces minified JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("def hello(): pass")

            parser = argparse.ArgumentParser()
            add_map_arguments(parser)
            args = parser.parse_args([tmpdir, "-o", "test.json", "--compact"])

            with patch("sys.stdout", StringIO()), patch("sys.stderr", StringIO()):
                run_map(args)

            output_path = Path(tmpdir) / "test.json"
            content = output_path.read_text()
            # Compact JSON should not have newlines or indentation
            assert "\n" not in content.strip() or content.count("\n") == 1


class TestSearchCommand:
    """Tests for the search subcommand."""

    @pytest.fixture
    def codemap_file(self, tmp_path):
        """Create a temporary code map file."""
        codemap = {
            "version": "1.0",
            "root": str(tmp_path),
            "generated_at": "2024-01-01T00:00:00",
            "stats": {"files_processed": 1, "symbols_found": 3, "errors": 0},
            "files": {
                "test.py": {
                    "hash": "abc123",
                    "symbols": [
                        {"name": "hello", "type": "function", "lines": [1, 5], "signature": "def hello()"},
                        {"name": "MyClass", "type": "class", "lines": [10, 30], "signature": "class MyClass"},
                        {"name": "get_value", "type": "method", "lines": [15, 20], "parent": "MyClass"},
                    ]
                }
            },
            "index": {
                "hello": [{"file": "test.py", "type": "function", "lines": [1, 5]}],
                "myclass": [{"file": "test.py", "type": "class", "lines": [10, 30]}],
                "get_value": [{"file": "test.py", "type": "method", "lines": [15, 20], "parent": "MyClass"}],
            }
        }

        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(codemap, f)

        return map_path

    def test_run_search_finds_symbol(self, codemap_file, capsys):
        """Test that search finds symbols correctly."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)
        args = parser.parse_args(["hello", "-m", str(codemap_file)])

        run_search(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) >= 1
        assert any(r["name"] == "hello" for r in output)

    def test_run_search_with_type_filter(self, codemap_file, capsys):
        """Test that type filter works correctly."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)
        args = parser.parse_args(["-t", "class", "-m", str(codemap_file)])

        run_search(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert len(output) >= 1
        assert all(r["type"] == "class" for r in output)

    def test_run_search_stats(self, codemap_file, capsys):
        """Test that stats command works correctly."""
        parser = argparse.ArgumentParser()
        add_search_arguments(parser)
        args = parser.parse_args(["--stats", "-m", str(codemap_file)])

        run_search(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "total_symbols" in output
        assert output["total_symbols"] == 3


class TestReadCommand:
    """Tests for the read subcommand."""

    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a temporary test file."""
        content = "\n".join([f"Line {i}" for i in range(1, 101)])
        file_path = tmp_path / "test.txt"
        file_path.write_text(content)
        return file_path

    def test_run_read_single_line(self, test_file, capsys):
        """Test reading a single line."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)
        args = parser.parse_args([str(test_file), "10"])

        run_read(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["requested"] == [10, 10]
        assert len(output["lines"]) == 1
        assert output["lines"][0]["content"] == "Line 10"

    def test_run_read_range(self, test_file, capsys):
        """Test reading a range of lines."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)
        args = parser.parse_args([str(test_file), "10-15"])

        run_read(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["requested"] == [10, 15]
        assert len(output["lines"]) == 6

    def test_run_read_with_context(self, test_file, capsys):
        """Test reading with context lines."""
        parser = argparse.ArgumentParser()
        add_read_arguments(parser)
        args = parser.parse_args([str(test_file), "50", "-c", "2"])

        run_read(args)

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["actual"] == [48, 52]
        assert len(output["lines"]) == 5


class TestStatsCommand:
    """Tests for the stats subcommand (shortcut for search --stats)."""

    def test_stats_via_unified_cli(self, tmp_path, capsys):
        """Test stats command through unified CLI."""
        # Create a code map
        codemap = {
            "version": "1.0",
            "root": str(tmp_path),
            "generated_at": "2024-01-01T00:00:00",
            "stats": {"files_processed": 5, "symbols_found": 50, "errors": 0},
            "files": {},
            "index": {}
        }

        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(codemap, f)

        with patch.object(sys, "argv", ["codemap", "stats", "-m", str(map_path)]):
            main()

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["files"] == 5
        assert output["total_symbols"] == 50


class TestBackwardCompatibility:
    """Tests to ensure legacy commands still work."""

    def test_code_mapper_main_import(self):
        """Test that code_mapper.main is still importable."""
        from code_map_navigator.code_mapper import main
        assert callable(main)

    def test_code_search_main_import(self):
        """Test that code_search.main is still importable."""
        from code_map_navigator.code_search import main
        assert callable(main)

    def test_line_reader_main_import(self):
        """Test that line_reader.main is still importable."""
        from code_map_navigator.line_reader import main
        assert callable(main)
