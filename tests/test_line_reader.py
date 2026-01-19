"""Tests for the line_reader module."""

import tempfile
from pathlib import Path

import pytest

from code_map_navigator.line_reader import LineReader, format_output


@pytest.fixture
def sample_file():
    """Create a sample file for testing."""
    content = "\n".join([f"Line {i}" for i in range(1, 101)])  # 100 lines
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()
        yield f.name


@pytest.fixture
def reader():
    """Create a LineReader instance."""
    return LineReader()


class TestLineReader:
    """Tests for the LineReader class."""

    def test_read_single_line(self, reader, sample_file):
        """Test reading a single line."""
        result = reader.read_lines(sample_file, 50)

        assert "error" not in result
        assert result["requested"] == [50, 50]
        assert len(result["lines"]) == 1
        assert result["lines"][0]["num"] == 50
        assert result["lines"][0]["content"] == "Line 50"
        assert result["lines"][0]["in_range"] is True

    def test_read_line_range(self, reader, sample_file):
        """Test reading a range of lines."""
        result = reader.read_lines(sample_file, 10, 20)

        assert "error" not in result
        assert result["requested"] == [10, 20]
        assert len(result["lines"]) == 11  # Lines 10-20 inclusive

        for line in result["lines"]:
            assert 10 <= line["num"] <= 20
            assert line["in_range"] is True

    def test_read_with_context(self, reader, sample_file):
        """Test reading with context lines."""
        result = reader.read_lines(sample_file, 50, 50, context=3)

        assert result["requested"] == [50, 50]
        assert result["actual"] == [47, 53]
        assert len(result["lines"]) == 7

        # Check in_range markers
        for line in result["lines"]:
            if line["num"] == 50:
                assert line["in_range"] is True
            else:
                assert line["in_range"] is False

    def test_read_at_file_start(self, reader, sample_file):
        """Test reading at the beginning of file."""
        result = reader.read_lines(sample_file, 1, 5, context=3)

        assert result["actual"][0] == 1  # Can't go before line 1
        assert len(result["lines"]) >= 5

    def test_read_at_file_end(self, reader, sample_file):
        """Test reading at the end of file."""
        result = reader.read_lines(sample_file, 98, 100, context=3)

        assert result["actual"][1] == 100  # Can't go past line 100
        assert len(result["lines"]) >= 3

    def test_read_file_not_found(self, reader):
        """Test reading a non-existent file."""
        result = reader.read_lines("/nonexistent/file.py", 1, 10)

        assert "error" in result
        assert "not found" in result["error"].lower()

    def test_read_multiple_ranges(self, reader, sample_file):
        """Test reading multiple ranges."""
        ranges = [(10, 15), (30, 35), (80, 85)]
        result = reader.read_ranges(sample_file, ranges)

        assert "error" not in result
        assert len(result["sections"]) == 3  # Non-overlapping ranges

        # Verify each section
        for section in result["sections"]:
            assert "range" in section
            assert "lines" in section

    def test_read_ranges_merge_close(self, reader, sample_file):
        """Test that close ranges are merged."""
        ranges = [(10, 12), (15, 18)]  # Gap of 2, should merge with default collapse_gap=5
        result = reader.read_ranges(sample_file, ranges, collapse_gap=5)

        assert "error" not in result
        assert len(result["sections"]) == 1  # Merged into one

    def test_read_ranges_no_merge_far(self, reader, sample_file):
        """Test that far ranges are not merged."""
        ranges = [(10, 12), (30, 35)]  # Gap of 17, should not merge
        result = reader.read_ranges(sample_file, ranges, collapse_gap=5)

        assert "error" not in result
        assert len(result["sections"]) == 2  # Not merged


class TestReadSymbol:
    """Tests for read_symbol method."""

    @pytest.fixture
    def large_file(self):
        """Create a larger file for truncation testing."""
        content = "\n".join([f"Line {i}: some content here" for i in range(1, 301)])
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            f.flush()
            yield f.name

    def test_read_small_symbol(self, reader, sample_file):
        """Test reading a small symbol (no truncation)."""
        result = reader.read_symbol(sample_file, 10, 30, max_lines=100)

        assert "error" not in result
        assert result["truncated"] is False
        assert result["range"] == [10, 30]

    def test_read_large_symbol_truncated(self, reader, large_file):
        """Test reading a large symbol (with truncation)."""
        result = reader.read_symbol(large_file, 10, 200, max_lines=50)

        assert "error" not in result
        assert result["truncated"] is True
        assert "skipped_lines" in result

        # Check for ellipsis marker
        ellipsis_line = [l for l in result["lines"] if l["num"] is None]
        assert len(ellipsis_line) == 1
        assert "omitted" in ellipsis_line[0]["content"]

    def test_read_symbol_with_context(self, reader, sample_file):
        """Test reading symbol with context."""
        result = reader.read_symbol(sample_file, 50, 60, include_context=True)

        assert "error" not in result
        # Should have context lines (in_range=False)
        context_lines = [l for l in result["lines"] if not l["in_range"]]
        assert len(context_lines) > 0


class TestSearchInFile:
    """Tests for search_in_file method."""

    @pytest.fixture
    def searchable_file(self):
        """Create a file with searchable content."""
        content = """
def process_payment(amount):
    validate(amount)
    return charge(amount)

def validate(value):
    return value > 0

def process_refund(amount):
    validate(amount)
    return refund(amount)
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(content)
            f.flush()
            yield f.name

    def test_search_literal(self, reader, searchable_file):
        """Test searching for a literal string."""
        result = reader.search_in_file(searchable_file, "process")

        assert "error" not in result
        assert result["matches"] >= 2  # process_payment and process_refund

    def test_search_regex(self, reader, searchable_file):
        """Test searching with regex pattern."""
        result = reader.search_in_file(searchable_file, r"def \w+_payment")

        assert "error" not in result
        assert result["matches"] >= 1

    def test_search_no_matches(self, reader, searchable_file):
        """Test searching for non-existent pattern."""
        result = reader.search_in_file(searchable_file, "nonexistent_pattern")

        assert "error" not in result
        assert result["matches"] == 0
        assert result["sections"] == []

    def test_search_max_matches(self, reader, searchable_file):
        """Test max_matches limit."""
        result = reader.search_in_file(searchable_file, "validate", max_matches=1)

        assert result["matches"] == 1

    def test_search_with_context(self, reader, searchable_file):
        """Test search with context lines."""
        result = reader.search_in_file(searchable_file, "process_payment", context=2)

        assert "error" not in result
        assert result["matches"] >= 1
        # Should have multiple lines per section due to context
        assert len(result["sections"][0]["lines"]) > 1


class TestFormatOutput:
    """Tests for the format_output function."""

    def test_format_json(self):
        """Test JSON format output."""
        result = {"file": "test.py", "lines": [{"num": 1, "content": "hello"}]}
        output = format_output(result, "json")

        assert "test.py" in output
        assert "hello" in output

    def test_format_code(self):
        """Test code format output."""
        result = {
            "file": "test.py",
            "lines": [
                {"num": 1, "content": "line 1", "in_range": True},
                {"num": 2, "content": "line 2", "in_range": False},
            ],
        }
        output = format_output(result, "code")

        assert "# test.py" in output
        assert ">   1 |" in output  # In range (4-char padding for line number)
        assert "    2 |" in output  # Not in range

    def test_format_error(self):
        """Test formatting error result."""
        result = {"error": "File not found"}
        output = format_output(result, "code")

        assert "Error:" in output
        assert "File not found" in output

    def test_format_sections(self):
        """Test formatting result with sections."""
        result = {
            "file": "test.py",
            "sections": [
                {
                    "lines": [{"num": 1, "content": "line 1", "in_range": True}]
                },
                {
                    "lines": [{"num": 10, "content": "line 10", "in_range": True}]
                },
            ],
        }
        output = format_output(result, "code")

        assert "..." in output  # Section separator


class TestLineReaderWithRoot:
    """Tests for LineReader with root path."""

    def test_resolve_relative_path(self):
        """Test resolving relative paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file
            (Path(tmpdir) / "src").mkdir()
            test_file = Path(tmpdir) / "src" / "test.py"
            test_file.write_text("Line 1\nLine 2\nLine 3")

            reader = LineReader(tmpdir)
            result = reader.read_lines("src/test.py", 1, 3)

            assert "error" not in result
            assert len(result["lines"]) == 3

    def test_resolve_absolute_path(self):
        """Test that absolute paths work regardless of root."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("Line 1\nLine 2\nLine 3")
            f.flush()

            reader = LineReader("/some/other/root")
            result = reader.read_lines(f.name, 1, 3)  # Absolute path

            assert "error" not in result
            assert len(result["lines"]) == 3
