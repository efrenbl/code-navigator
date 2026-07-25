"""Tests for the mapping-coverage metrics surfaced in scan stats.

Covers files_skipped, files_unmapped, unmapped_extensions, symbols_truncated
and coverage_pct. These do not depend on any optional analyzer (ast-grep /
tree-sitter) — they count files.

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
    and one ignored directory (node_modules). (.zig stands in as an unmapped
    code extension — .kt graduated to a mapped language in v0.4.0.)"""
    proj = tmp_path / "proj"
    (proj / "lib").mkdir(parents=True)
    (proj / "lib" / "app.py").write_text("def main():\n    return 1\n")
    (proj / "lib" / "util.zig").write_text("fn greet() void {}\n")
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
        assert stats["files_unmapped"] == 4  # .zig .sh .json .txt
        exts = stats["unmapped_extensions"]
        assert exts.get(".zig") == 1
        assert exts.get(".sh") == 1
        assert exts.get(".json") == 1
        assert exts.get(".txt") == 1
        # mapped / (mapped + unmapped) = 1 / 5 = 20%
        assert stats["coverage_pct"] == 20.0

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
        assert stats["unmapped_extensions"].get(".zig") == 1


class TestTruncation:
    """max_symbol_lines is the regex (GenericAnalyzer) cap; tree-sitter/ast-grep
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
        # Force the regex path so the cap actually applies (Java resolves
        # tree-sitter → ast-grep → regex since v0.4.0; disable the first two),
        # then confirm the navigator threads max_symbol_lines through.
        import codenav.ast_grep_analyzer as ag
        from codenav.languages import registry

        monkeypatch.setattr(ag, "is_ast_grep_available", lambda: False)
        monkeypatch.setattr(registry, "get_language", lambda name: None)
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


class TestSymbolProvenance:
    """Symbol.source ("ast" / "ast-grep" / "regex") in maps and stats."""

    def test_python_symbols_marked_ast(self, tmp_path):
        proj = tmp_path / "pyproj"
        proj.mkdir()
        (proj / "app.py").write_text("def main():\n    return 1\n")
        data = CodeNavigator(str(proj)).scan()
        symbols = data["files"]["app.py"]["symbols"]
        assert symbols and all(s["source"] == "ast" for s in symbols)

    def test_regex_fallback_marked_regex(self, tmp_path, monkeypatch):
        import codenav.ast_grep_analyzer as ag
        from codenav.languages import registry

        monkeypatch.setattr(ag, "is_ast_grep_available", lambda: False)
        monkeypatch.setattr(registry, "get_language", lambda name: None)
        proj = tmp_path / "javaproj"
        proj.mkdir()
        (proj / "A.java").write_text("public class A {\n  void f() {}\n}\n")
        data = CodeNavigator(str(proj)).scan()
        symbols = data["files"]["A.java"]["symbols"]
        assert symbols and all(s["source"] == "regex" for s in symbols)

    def test_old_map_without_source_roundtrips(self, tmp_path):
        proj = tmp_path / "old"
        proj.mkdir()
        (proj / "app.py").write_text("def main():\n    return 1\n")
        first = CodeNavigator(str(proj)).scan()
        # Simulate a pre-v0.4.0 map: strip every source field.
        for info in first["files"].values():
            for sym in info["symbols"]:
                sym.pop("source", None)
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(first))

        result = CodeNavigator(str(proj)).scan_incremental(str(map_path))
        # Unchanged file: symbols round-trip without inventing a source.
        symbols = result["files"]["app.py"]["symbols"]
        assert symbols and all("source" not in s for s in symbols)

    def test_incremental_reanalysis_stamps_source(self, tmp_path):
        proj = tmp_path / "inc"
        proj.mkdir()
        (proj / "app.py").write_text("def main():\n    return 1\n")
        first = CodeNavigator(str(proj)).scan()
        for info in first["files"].values():
            for sym in info["symbols"]:
                sym.pop("source", None)
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(first))

        (proj / "app.py").write_text("def main():\n    return 2\n")
        result = CodeNavigator(str(proj)).scan_incremental(str(map_path))
        symbols = result["files"]["app.py"]["symbols"]
        assert symbols and all(s["source"] == "ast" for s in symbols)

    def test_old_map_without_enrichment_keys_roundtrips(self, tmp_path):
        """Pre-v0.4.1 maps (no visibility/modifiers/...) load and re-emit cleanly."""
        proj = tmp_path / "plain"
        proj.mkdir()
        (proj / "app.py").write_text("def main():\n    return 1\n")
        first = CodeNavigator(str(proj)).scan()
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(first))

        result = CodeNavigator(str(proj)).scan_incremental(str(map_path))
        symbols = result["files"]["app.py"]["symbols"]
        assert symbols
        for sym in symbols:
            for key in ("visibility", "modifiers", "mixins", "return_type"):
                assert key not in sym

    def test_enrichment_keys_roundtrip_for_unchanged_files(self, tmp_path):
        """Enrichment values survive an incremental scan of an unchanged file."""
        proj = tmp_path / "enriched"
        proj.mkdir()
        (proj / "app.py").write_text("def main():\n    return 1\n")
        first = CodeNavigator(str(proj)).scan()
        sym = first["files"]["app.py"]["symbols"][0]
        sym["visibility"] = "private"
        sym["modifiers"] = ["static"]
        sym["return_type"] = "Foo"
        map_path = tmp_path / "map.json"
        map_path.write_text(json.dumps(first))

        result = CodeNavigator(str(proj)).scan_incremental(str(map_path))
        loaded = result["files"]["app.py"]["symbols"][0]
        assert loaded["visibility"] == "private"
        assert loaded["modifiers"] == ["static"]
        assert loaded["return_type"] == "Foo"
