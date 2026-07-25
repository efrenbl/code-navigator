"""Tests for the fused codenav_lookup tool and the reverse caller index."""

from __future__ import annotations

import json

from codenav.code_navigator import CodeNavigator
from codenav.code_search import CodeSearcher

SOURCE = """\
def helper(x):
    return x + 1


def process(data):
    result = helper(data)
    return validate(result)


def validate(v):
    return v > 0
"""


def _index(tmp_path):
    (tmp_path / "app.py").write_text(SOURCE)
    code_map = CodeNavigator(str(tmp_path)).scan()
    map_path = tmp_path / ".codenav.json"
    map_path.write_text(json.dumps(code_map))
    return map_path


class TestReverseCallers:
    def test_find_callers(self, tmp_path):
        searcher = CodeSearcher(str(_index(tmp_path)))
        assert [c["name"] for c in searcher.find_callers("helper")] == ["process"]
        assert [c["name"] for c in searcher.find_callers("validate")] == ["process"]

    def test_no_callers(self, tmp_path):
        searcher = CodeSearcher(str(_index(tmp_path)))
        assert searcher.find_callers("process") == []
        assert searcher.find_callers("nonexistent") == []

    def test_index_built_once(self, tmp_path):
        searcher = CodeSearcher(str(_index(tmp_path)))
        searcher.find_callers("helper")
        assert searcher._callers_index is not None


class TestCodenavLookup:
    def _run(self, tmp_path, query, **kw):
        _index(tmp_path)
        from codenav.mcp import server

        server.get_handler().workspace_root = str(tmp_path)
        return server.codenav_lookup(query, path=str(tmp_path), **kw)

    def test_returns_body_and_callers_in_one_call(self, tmp_path):
        out = self._run(tmp_path, "helper")
        assert "def helper(x):" in out  # body present
        assert "return x + 1" in out
        assert "called by (1): process" in out  # relation present
        assert "[function] helper" in out

    def test_empty_query_discloses_index_health(self, tmp_path):
        out = self._run(tmp_path, "does_not_exist")
        assert "No matching symbols found." in out

    def test_body_is_clipped_to_budget(self, tmp_path):
        big = "def huge():\n" + "\n".join(f"    a{i} = {i}" for i in range(400)) + "\n"
        (tmp_path / "big.py").write_text(big)
        from codenav.mcp import server

        code_map = CodeNavigator(str(tmp_path)).scan()
        (tmp_path / ".codenav.json").write_text(json.dumps(code_map))
        server.get_handler().workspace_root = str(tmp_path)
        out = server.codenav_lookup("huge", path=str(tmp_path))
        # Clipped: the continuation hint points back to codenav_read.
        assert "more lines" in out
        assert "codenav_read" in out
