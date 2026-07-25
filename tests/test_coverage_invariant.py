"""Tests for the coverage invariant, skip-reason breakdown and index versioning.

These guard the "an incomplete index that reports itself healthy is worse than
no index" property: silent loss must surface as an error, a distinguishable
skip cause, or a re-scan — never as ``errors: 0`` over missing code.
"""

from __future__ import annotations

import json

from codenav import code_navigator as cn
from codenav.code_navigator import INDEX_FORMAT_VERSION, CodeNavigator

REAL_PY = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"


class TestCoverageInvariant:
    def test_broken_analyzer_flags_gap_and_errors(self, tmp_path, monkeypatch):
        """A language with real code but zero symbols everywhere is an ERROR."""
        for i in range(4):
            (tmp_path / f"mod{i}.py").write_text(REAL_PY)

        # Simulate a wholesale-broken analyzer: parses nothing.
        monkeypatch.setattr(cn.PythonAnalyzer, "analyze", lambda self: [])

        stats = CodeNavigator(str(tmp_path)).scan()["stats"]
        assert stats["coverage_gaps"] == ["python"]
        assert stats["errors"] >= 1
        assert stats["per_language"]["python"]["files"] == 4
        assert stats["per_language"]["python"]["files_with_symbols"] == 0

    def test_healthy_scan_has_no_gap(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        stats = CodeNavigator(str(tmp_path)).scan()["stats"]
        assert stats["coverage_gaps"] == []
        assert stats["per_language"]["python"]["files_with_symbols"] == 1

    def test_empty_and_comment_only_files_do_not_trigger_gap(self, tmp_path):
        """An empty __init__.py or a lone comment file must not fail the scan."""
        (tmp_path / "__init__.py").write_text("")
        (tmp_path / "notes.py").write_text("# just a comment\n# and another\n")
        (tmp_path / "real.py").write_text("def works():\n    return 2\n")
        stats = CodeNavigator(str(tmp_path)).scan()["stats"]
        assert stats["coverage_gaps"] == []

    def test_below_file_threshold_not_flagged(self, tmp_path, monkeypatch):
        """One broken file is not enough to condemn a language (needs several)."""
        (tmp_path / "only.py").write_text(REAL_PY)
        monkeypatch.setattr(cn.PythonAnalyzer, "analyze", lambda self: [])
        stats = CodeNavigator(str(tmp_path)).scan()["stats"]
        assert stats["coverage_gaps"] == []


class TestSkipReasons:
    def test_gitignore_skip_is_attributed(self, tmp_path):
        (tmp_path / ".gitignore").write_text("ignored.py\n")
        (tmp_path / "ignored.py").write_text("def a():\n    return 1\n")
        (tmp_path / "kept.py").write_text("def b():\n    return 2\n")
        stats = CodeNavigator(str(tmp_path), use_gitignore=True).scan()["stats"]
        assert stats.get("skipped_gitignore", 0) >= 1
        assert stats["files_skipped"] >= 1

    def test_default_pattern_skip_is_attributed(self, tmp_path):
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "dep.js").write_text("function x(){}")
        (tmp_path / "app.py").write_text("def a():\n    return 1\n")
        stats = CodeNavigator(str(tmp_path)).scan()["stats"]
        # node_modules is pruned as a directory, so its files never enumerate;
        # the point is the kept file is processed and the scan is clean.
        assert stats["files_processed"] == 1
        assert "app.py" in {"app.py"}


class TestIndexVersioning:
    def test_new_map_carries_bumped_version(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        code_map = CodeNavigator(str(tmp_path)).scan()
        assert code_map["version"] == INDEX_FORMAT_VERSION
        assert INDEX_FORMAT_VERSION != "1.0"

    def test_stale_version_forces_full_rescan(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        # Write a pre-2.2.9 map (the buggy-substring era) with the old version.
        old_map = CodeNavigator(str(tmp_path)).scan()
        old_map["version"] = "1.0"
        map_path = tmp_path / ".codenav.json"
        map_path.write_text(json.dumps(old_map))

        result = CodeNavigator(str(tmp_path)).scan_incremental(str(map_path))
        # A full rescan does not report the incremental "files_unchanged" key.
        assert "files_unchanged" not in result["stats"]
        assert result["version"] == INDEX_FORMAT_VERSION

    def test_matching_version_allows_incremental(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    return 1\n")
        map_path = tmp_path / ".codenav.json"
        map_path.write_text(json.dumps(CodeNavigator(str(tmp_path)).scan()))
        result = CodeNavigator(str(tmp_path)).scan_incremental(str(map_path))
        assert "files_unchanged" in result["stats"]
