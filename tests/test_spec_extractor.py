"""Tests for the generic spec-driven tree-sitter extractor framework."""

import pytest

from codenav.code_navigator import Symbol
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

GO_AVAILABLE = registry.is_available("go")

GO_SOURCE = """package main

import "fmt"

// Greet says hello.
func Greet(name string) string {
    return fmt.Sprintf("Hello, %s", name)
}
"""


class TestSpecLookup:
    def test_get_spec_returns_go(self):
        spec = get_spec("go")
        assert spec is not None
        assert spec.language == "go"
        assert spec.grammar_for("main.go") == "go"

    def test_get_spec_unknown_language(self):
        assert get_spec("cobol") is None


class TestFallback:
    def test_injected_fallback_used_when_grammar_missing(self, monkeypatch):
        monkeypatch.setattr(registry, "get_language", lambda name: None)
        sentinel = [Symbol(name="x", type="function", file_path="a.go", line_start=1, line_end=1)]
        extractor = TreeSitterExtractor(
            "a.go", GO_SOURCE, get_spec("go"), fallback=lambda: sentinel
        )
        assert extractor.analyze() is sentinel

    def test_generic_fallback_when_grammar_missing(self, monkeypatch):
        monkeypatch.setattr(registry, "get_language", lambda name: None)
        extractor = TreeSitterExtractor("a.go", GO_SOURCE, get_spec("go"))
        symbols = extractor.analyze()
        assert "Greet" in [s.name for s in symbols]

    @pytest.mark.skipif(not GO_AVAILABLE, reason="requires a go grammar")
    def test_parse_exception_falls_back_per_file(self, monkeypatch):
        real_get_language = registry.get_language

        class ExplodingLanguage:
            def __getattr__(self, item):
                raise RuntimeError("boom")

        monkeypatch.setattr(registry, "get_language", lambda name: ExplodingLanguage())
        extractor = TreeSitterExtractor("a.go", GO_SOURCE, get_spec("go"))
        symbols = extractor.analyze()
        # Regex fallback still finds the function even though parsing blew up.
        assert "Greet" in [s.name for s in symbols]
        monkeypatch.setattr(registry, "get_language", real_get_language)


class _StubNode:
    start_point = (0, 0)
    end_point = (0, 10)


class TestEmitEnrichment:
    """emit() normalizes the v0.4.1 enrichment fields."""

    def _emit(self, **kwargs):
        extractor = TreeSitterExtractor("a.go", GO_SOURCE, get_spec("go"))
        extractor.emit(name="x", kind="function", node=_StubNode(), **kwargs)
        return extractor.symbols[0]

    def test_public_visibility_normalized_to_none(self):
        assert self._emit(visibility="public").visibility is None

    def test_private_visibility_kept(self):
        assert self._emit(visibility="private").visibility == "private"

    def test_empty_modifiers_and_mixins_normalized_to_none(self):
        symbol = self._emit(modifiers=[], mixins=[])
        assert symbol.modifiers is None
        assert symbol.mixins is None

    def test_values_pass_through(self):
        symbol = self._emit(modifiers=["static"], mixins=["Comparable"], return_type="Foo")
        assert symbol.modifiers == ["static"]
        assert symbol.mixins == ["Comparable"]
        assert symbol.return_type == "Foo"

    def test_defaults_are_none(self):
        symbol = self._emit()
        assert symbol.visibility is None
        assert symbol.modifiers is None
        assert symbol.mixins is None
        assert symbol.return_type is None


@pytest.mark.skipif(not GO_AVAILABLE, reason="requires a go grammar")
class TestAstExtraction:
    def test_symbols_imports_docs_and_calls(self):
        extractor = TreeSitterExtractor("a.go", GO_SOURCE, get_spec("go"))
        symbols = extractor.analyze()
        greet = next(s for s in symbols if s.name == "Greet")
        assert greet.type == "function"
        assert greet.signature.startswith("func Greet")
        assert greet.docstring == "Greet says hello."
        assert "Sprintf" in (greet.dependencies or [])
        assert extractor.imports == ["fmt"]

    def test_signature_capped_at_100_chars(self):
        long_params = ", ".join(f"arg{i} string" for i in range(30))
        source = f"package main\n\nfunc Long({long_params}) {{}}\n"
        extractor = TreeSitterExtractor("a.go", source, get_spec("go"))
        symbols = extractor.analyze()
        long_fn = next(s for s in symbols if s.name == "Long")
        assert len(long_fn.signature) == 100

    def test_line_numbers_are_one_indexed(self):
        extractor = TreeSitterExtractor("a.go", GO_SOURCE, get_spec("go"))
        greet = next(s for s in extractor.analyze() if s.name == "Greet")
        assert greet.line_start == 6
        assert greet.line_end == 8
