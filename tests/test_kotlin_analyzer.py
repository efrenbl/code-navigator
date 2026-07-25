"""Tests for the Kotlin language spec."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
KT_FIXTURE = FIXTURES_DIR / "sample_kotlin.kt"

KOTLIN_AVAILABLE = registry.is_available("kotlin")


def _analyze(source: str, path: str = "sample_kotlin.kt"):
    return TreeSitterExtractor(path, source, get_spec("kotlin")).analyze()


class TestKotlinSpec:
    @pytest.fixture
    def kt_source(self):
        return KT_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, kt_source):
        assert len(_analyze(kt_source)) > 0

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_detect_top_level_function(self, kt_source):
        functions = [s.name for s in _analyze(kt_source) if s.type == "function"]
        assert "greet" in functions
        assert "fetchData" in functions

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_detect_classes_and_object(self, kt_source):
        classes = [s.name for s in _analyze(kt_source) if s.type == "class"]
        assert "SimpleClass" in classes
        assert "Point" in classes  # data class
        assert "Singleton" in classes  # object declaration

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_classify_interface_and_enum(self, kt_source):
        symbols = _analyze(kt_source)
        interfaces = [s.name for s in symbols if s.type == "interface"]
        assert "Repository" in interfaces
        assert "Action" in interfaces  # fun interface
        enums = [s.name for s in symbols if s.type == "enum"]
        assert "Status" in enums

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_method_parent(self, kt_source):
        get_value = next(s for s in _analyze(kt_source) if s.name == "getValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_object_member_parent(self, kt_source):
        instance = next(s for s in _analyze(kt_source) if s.name == "instance")
        assert instance.type == "method"
        assert instance.parent == "Singleton"

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_type_alias(self, kt_source):
        types = [s.name for s in _analyze(kt_source) if s.type == "type"]
        assert "Handler" in types

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_kdoc_docstring(self, kt_source):
        greet = next(s for s in _analyze(kt_source) if s.name == "greet")
        assert greet.docstring == "Greets someone by name."

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_dependencies_positional_calls(self, kt_source):
        greet = next(s for s in _analyze(kt_source) if s.name == "greet")
        assert "abs" in greet.dependencies
        assert "formatName" in greet.dependencies
        assert "toString" in greet.dependencies

    @pytest.mark.skipif(not KOTLIN_AVAILABLE, reason="requires a kotlin grammar")
    def test_imports_collected(self, kt_source):
        extractor = TreeSitterExtractor("sample_kotlin.kt", kt_source, get_spec("kotlin"))
        extractor.analyze()
        assert "kotlin.math.abs" in extractor.imports

    def test_empty_source(self):
        assert _analyze("") == []


class TestKotlinFallback:
    def test_regex_fallback_produces_symbols(self):
        source = KT_FIXTURE.read_text()
        symbols = GenericAnalyzer("sample_kotlin.kt", source, "kotlin").analyze()
        names = [s.name for s in symbols]
        assert "greet" in names
        assert "SimpleClass" in names
        assert "Singleton" in names
