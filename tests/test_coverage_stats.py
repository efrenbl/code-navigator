"""Tests for the mapping-coverage metrics surfaced in scan stats.

Covers the denominator/visibility work: files_skipped, files_unmapped,
unmapped_extensions, symbols_truncated and coverage_pct. These do not depend
on any optional analyzer (ast-grep / tree-sitter) — they count files.

Note: test names and temp dir/file names deliberately avoid substrings in
DEFAULT_IGNORE_PATTERNS (e.g. "coverage", "build", "env", "bin") — the ignore
matcher is substring-based on the full path, so such a name would silently
ignore the whole tmp tree.
"""

import json

from codenav.code_navigator import (
    CodeNavigator,
    GenericAnalyzer,
    coverage_summary_line,
)


def _build_polyglot(tmp_path):
    """A tree with one mapped language (.py), several unmapped extensions,
    and one ignored directory (node_modules)."""
    proj = tmp_path / "proj"
    (proj / "lib").mkdir(parents=True)
    (proj / "lib" / "app.py").write_text("def main():\n    return 1\n")
    (proj / "lib" / "util.kt").write_text("fun greet() {}\n")
    (proj / "deploy.sh").write_text("#!/bin/bash\necho hi\n")
    (proj / "data.json").write_text('{"a": 1}\n')
    (proj / "notes.txt").write_text("hello\n")
    (proj / "node_modules").mkdir()
    (proj / "node_modules" / "lib.js").write_text("function x() {}\n")
    return proj


class TestMappingMetrics:
    def test_full_scan_reports_unmapped(self, tmp_path):
        proj = _build_polyglot(tmp_path)
        stats = CodeNavigator(str(proj)).scan()["stats"]

        assert stats["files_processed"] == 1  # app.py
        assert stats["files_unmapped"] == 4  # .kt .sh .json .txt
        exts = stats["unmapped_extensions"]
        assert exts.get(".kt") == 1
        assert exts.get(".sh") == 1
        assert exts.get(".json") == 1
        assert exts.get(".txt") == 1
        # mapped / (mapped + unmapped) = 1 / 5 = 20%
        assert stats["coverage_pct"] == 20.0
        # node_modules is pruned at the directory level, so its files never
        # surface; metrics stay focused on the real tree.

    def test_files_skipped_counts_ignored_files(self, tmp_path):
        proj = tmp_path / "p"
        proj.mkdir()
        (proj / "real.py").write_text("x = 1\n")
        (proj / "vendor.min.js").write_text("var a=1;\n")  # matches *.min.js
        stats = CodeNavigator(str(proj)).scan()["stats"]
        assert stats["files_skipped"] >= 1
        assert stats["files_processed"] == 1

    def test_pct_is_100_when_all_mapped(self, tmp_path):
        proj = tmp_path / "allpy"
        proj.mkdir()
        (proj / "a.py").write_text("def a():\n    pass\n")
        (proj / "b.py").write_text("def b():\n    pass\n")
        stats = CodeNavigator(str(proj)).scan()["stats"]
        assert stats["files_unmapped"] == 0
        assert stats["coverage_pct"] == 100.0

    def test_empty_dir_pct_is_100(self, tmp_path):
        proj = tmp_path / "empty"
        proj.mkdir()
        stats = CodeNavigator(str(proj)).scan()["stats"]
        assert stats["coverage_pct"] == 100.0
        assert stats["files_processed"] == 0

    def test_incremental_scan_reports_metrics(self, tmp_path):
        proj = _build_polyglot(tmp_path)
        first = CodeNavigator(str(proj)).scan()
        # Write the map OUTSIDE the project so it does not add a .json file.
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(first))

        result = CodeNavigator(str(proj)).scan_incremental(str(map_path))
        stats = result["stats"]
        assert "coverage_pct" in stats
        assert stats["files_unmapped"] == 4
        assert stats["unmapped_extensions"].get(".kt") == 1


class TestTruncation:
    """MAX_SYMBOL_LINES is the regex (GenericAnalyzer) cap; tree-sitter/ast-grep
    analyzers do not truncate."""

    def test_generic_analyzer_truncates_at_cap(self):
        body = "\n".join(f"    int x{i} = {i};" for i in range(30))
        src = f"public class Big {{\n  void huge() {{\n{body}\n  }}\n}}\n"
        syms = GenericAnalyzer("Big.java", src, "java", max_symbol_lines=5).analyze()
        assert any(s.truncated for s in syms)

    def test_generic_analyzer_default_does_not_truncate_small(self):
        src = "public class S {\n  void f() {\n    int x = 1;\n  }\n}\n"
        syms = GenericAnalyzer("S.java", src, "java").analyze()
        assert not any(s.truncated for s in syms)

    def test_navigator_forwards_max_symbol_lines(self, tmp_path, monkeypatch):
        # Force the regex path so the cap actually applies, then confirm the
        # navigator threads max_symbol_lines through to GenericAnalyzer.
        import codenav.ast_grep_analyzer as ag

        monkeypatch.setattr(ag, "is_ast_grep_available", lambda: False)
        proj = tmp_path / "big"
        proj.mkdir()
        body = "\n".join(f"    int x{i} = {i};" for i in range(30))
        (proj / "Big.java").write_text(f"public class Big {{\n  void huge() {{\n{body}\n  }}\n}}\n")
        stats = CodeNavigator(str(proj), max_symbol_lines=5).scan()["stats"]
        assert stats["symbols_truncated"] >= 1


class TestSummaryLine:
    def test_summary_includes_unmapped_breakdown(self):
        stats = {
            "files_processed": 636,
            "files_unmapped": 12,
            "unmapped_extensions": {".kt": 8, ".sh": 4},
            "files_skipped": 1204,
            "coverage_pct": 98.2,
        }
        line = coverage_summary_line(stats)
        assert "mapped 636" in line
        assert "unmapped 12" in line
        assert ".kt:8" in line
        assert "skipped 1204" in line
        assert "coverage 98.2%" in line

    def test_summary_minimal(self):
        stats = {"files_processed": 3, "files_unmapped": 0, "coverage_pct": 100.0}
        line = coverage_summary_line(stats)
        assert "mapped 3" in line
        assert "coverage 100.0%" in line
        assert "unmapped" not in line
