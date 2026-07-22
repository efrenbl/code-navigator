"""Tests for the centralized ReDoS guard (codenav.regex_safety.safe_compile).

Covers the two paths that previously called re.compile directly:
  - code_search._safe_regex_compile (now an alias of safe_compile)
  - line_reader.LineReader.search_in_file (the grep path)
"""

import re
import tempfile
from pathlib import Path

import pytest

from codenav.code_search import _safe_regex_compile
from codenav.line_reader import LineReader
from codenav.regex_safety import safe_compile

# Nested-quantifier / catastrophic-backtracking constructs that must be rejected.
CATASTROPHIC = [
    "(a+)+",
    "(a*)*",
    "(a+)*",
    "(.*)+",
    r"(\w+)+",
    "(a+b)+",
    r"(\d+){2,}",
]

# Legitimate patterns that must still compile.
SAFE = [
    "process_payment",
    "def .*payment",
    "(foo)+",
    "(a|b)*",
    r"[A-Za-z_]\w*",
    "class|struct",
]


class TestSafeCompile:
    @pytest.mark.parametrize("pattern", CATASTROPHIC)
    def test_rejects_catastrophic(self, pattern):
        with pytest.raises(ValueError, match="nested quantifiers"):
            safe_compile(pattern)

    @pytest.mark.parametrize("pattern", SAFE)
    def test_allows_safe(self, pattern):
        compiled = safe_compile(pattern)
        assert isinstance(compiled, re.Pattern)

    def test_invalid_regex_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            safe_compile("(unclosed")

    def test_default_flag_is_ignorecase(self):
        assert safe_compile("abc").flags & re.IGNORECASE

    def test_code_search_alias_is_shared_guard(self):
        # code_search must reuse the same centralized guard, not a private copy.
        assert _safe_regex_compile is safe_compile


class TestSearchInFileGuard:
    """The grep path must reject catastrophic patterns instead of compiling them."""

    def test_search_in_file_rejects_catastrophic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "sample.py"
            f.write_text("aaaaaaaaaaaaaaaaaaaa!\n")
            reader = LineReader(tmpdir)

            result = reader.search_in_file(str(f), "(a+)+")

            assert "error" in result
            assert "nested quantifiers" in result["error"]
            assert result["matches"] == 0

    def test_search_in_file_allows_safe_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "sample.py"
            f.write_text("def process_payment():\n    pass\n")
            reader = LineReader(tmpdir)

            result = reader.search_in_file(str(f), "process_payment")

            assert "error" not in result
            assert result["matches"] >= 1
