"""Tests for the central tree-sitter grammar registry."""

import sys

import pytest

from codenav.languages import registry


@pytest.fixture(autouse=True)
def fresh_cache():
    registry.clear_cache()
    yield
    registry.clear_cache()


class TestGetLanguage:
    def test_unknown_language_returns_none(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)
        monkeypatch.setitem(sys.modules, "tree_sitter_no_such_language", None)
        assert registry.get_language("no_such_language") is None

    def test_nothing_installed_returns_none(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)
        monkeypatch.setitem(sys.modules, "tree_sitter_go", None)
        assert registry.get_language("go") is None
        assert registry.is_available("go") is False
        assert registry.backend("go") is None

    def test_result_is_cached(self):
        assert registry.get_language("go") is registry.get_language("go")

    def test_cache_survives_backend_removal(self, monkeypatch):
        language = registry.get_language("go")
        if language is None:
            pytest.skip("no go grammar installed")
        monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)
        monkeypatch.setitem(sys.modules, "tree_sitter_go", None)
        assert registry.get_language("go") is language

    def test_miss_is_cached_too(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)
        monkeypatch.setitem(sys.modules, "tree_sitter_go", None)
        assert registry.get_language("go") is None
        # Backends reappear, but the miss stays cached until clear_cache().
        monkeypatch.delitem(sys.modules, "tree_sitter_go")
        assert registry.get_language("go") is None
        registry.clear_cache()

    def test_backend_reports_source(self):
        if registry.get_language("go") is None:
            assert registry.backend("go") is None
        else:
            assert registry.backend("go") in ("pack", "wheel")

    def test_is_available_matches_get_language(self):
        assert registry.is_available("go") == (registry.get_language("go") is not None)


class TestWheelSpecialCases:
    def test_typescript_dialects_are_distinct(self):
        ts = registry.get_language("typescript")
        tsx = registry.get_language("tsx")
        if ts is None or tsx is None:
            pytest.skip("typescript grammar not installed")
        assert ts is not tsx
