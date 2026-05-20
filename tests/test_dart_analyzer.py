"""Tests for DartAnalyzer — covers both tree-sitter and regex fallback paths."""

from pathlib import Path

import pytest

from codenav.code_navigator import CodeNavigator, GenericAnalyzer
from codenav.dart_analyzer import TREE_SITTER_AVAILABLE, DartAnalyzer

FIXTURE = Path(__file__).parent / "fixtures" / "sample_dart.dart"
SAMPLE = FIXTURE.read_text()


def _names(symbols, type_=None):
    if type_:
        return [s.name for s in symbols if s.type == type_]
    return [s.name for s in symbols]


class TestDartAnalyzerFallback:
    """GenericAnalyzer regex fallback — always runs regardless of tree-sitter."""

    def test_detects_classes(self):
        symbols = GenericAnalyzer("sample.dart", SAMPLE, "dart").analyze()
        classes = _names(symbols, "class")
        assert "MyWidget" in classes
        assert "Counter" in classes

    def test_detects_enum(self):
        symbols = GenericAnalyzer("sample.dart", SAMPLE, "dart").analyze()
        assert "Status" in _names(symbols, "enum")

    def test_detects_mixin(self):
        symbols = GenericAnalyzer("sample.dart", SAMPLE, "dart").analyze()
        assert "Loggable" in _names(symbols, "mixin")

    def test_detects_extension(self):
        symbols = GenericAnalyzer("sample.dart", SAMPLE, "dart").analyze()
        assert "StringExtension" in _names(symbols, "extension")

    def test_line_numbers_positive(self):
        for s in GenericAnalyzer("sample.dart", SAMPLE, "dart").analyze():
            assert s.line_start >= 1
            assert s.line_end >= s.line_start

    def test_regex_does_not_match_control_keywords(self):
        """Refined regex must not flag if/for/while/return as functions."""
        src = """
        void test() {
          if (cond) {
            return;
          }
          for (var x in list) {
            print(x);
          }
        }
        """
        symbols = GenericAnalyzer("ctrl.dart", src, "dart").analyze()
        fn_names = _names(symbols, "function")
        assert "test" in fn_names
        assert "if" not in fn_names
        assert "for" not in fn_names


class TestDartAnalyzer:
    """DartAnalyzer — uses tree-sitter when available, regex otherwise."""

    def test_analyze_returns_symbols(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert len(symbols) > 0

    def test_detects_classes(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        classes = _names(symbols, "class")
        assert "MyWidget" in classes
        assert "Counter" in classes

    def test_detects_enum(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert "Status" in _names(symbols, "enum")

    def test_detects_mixin(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert "Loggable" in _names(symbols, "mixin")

    def test_detects_extension(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert "StringExtension" in _names(symbols, "extension")

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter-dart not installed")
    def test_detects_private_class(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert "_CounterState" in _names(symbols, "class")

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter-dart not installed")
    def test_methods_have_parent(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        methods = [s for s in symbols if s.type == "method"]
        assert any(s.parent == "MyWidget" and s.name == "build" for s in methods)
        assert any(s.parent == "_CounterState" and s.name == "_increment" for s in methods)

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter-dart not installed")
    def test_top_level_function(self):
        symbols = DartAnalyzer("sample.dart", SAMPLE).analyze()
        assert "formatCurrency" in _names(symbols, "function")

    def test_empty_file(self):
        assert DartAnalyzer("empty.dart", "").analyze() == []

    def test_invalid_dart_does_not_crash(self):
        bad = "class { broken dart *** @@@ }"
        symbols = DartAnalyzer("bad.dart", bad).analyze()
        assert isinstance(symbols, list)

    def test_line_numbers_positive(self):
        for s in DartAnalyzer("sample.dart", SAMPLE).analyze():
            assert s.line_start >= 1
            assert s.line_end >= s.line_start


class TestDartIntegration:
    """Make sure CodeNavigator scans a project containing .dart files cleanly."""

    def test_scan_with_dart_files_does_not_crash(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "lib").mkdir()
        (proj / "lib" / "widget.dart").write_text(SAMPLE)

        navigator = CodeNavigator(str(proj))
        result = navigator.scan()
        assert result["stats"]["errors"] == 0
        assert result["stats"]["files_processed"] >= 1

    def test_dart_generated_files_are_ignored(self, tmp_path):
        # Note: avoid substrings like "build", "dist", "env" anywhere in the
        # tmp_path tree — DEFAULT_IGNORE_PATTERNS does substring matching on
        # the full path, which would mask the test result.
        proj = tmp_path / "app"
        (proj / ".dart_tool").mkdir(parents=True)
        (proj / ".dart_tool" / "cache.dart").write_text("class ShouldBeIgnored {}")
        (proj / "lib").mkdir()
        (proj / "lib" / "real.dart").write_text("class Real {}")
        (proj / "lib" / "real.g.dart").write_text("class Generated {}")

        navigator = CodeNavigator(str(proj))
        result = navigator.scan()
        all_symbols = []
        for file_data in result["files"].values():
            for sym in file_data.get("symbols", []):
                all_symbols.append(sym["name"])
        assert "Real" in all_symbols
        assert "ShouldBeIgnored" not in all_symbols
        assert "Generated" not in all_symbols
