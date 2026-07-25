"""Tests for the Java language spec."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JAVA_FIXTURE = FIXTURES_DIR / "sample_java.java"

JAVA_AVAILABLE = registry.is_available("java")


def _analyze(source: str, path: str = "sample_java.java"):
    return TreeSitterExtractor(path, source, get_spec("java")).analyze()


class TestJavaSpec:
    @pytest.fixture
    def java_source(self):
        return JAVA_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, java_source):
        assert len(_analyze(java_source)) > 0

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_detect_class(self, java_source):
        classes = [s.name for s in _analyze(java_source) if s.type == "class"]
        assert "SimpleClass" in classes
        assert "Nested" in classes
        assert "Point" in classes  # record

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_detect_interface(self, java_source):
        interfaces = [s.name for s in _analyze(java_source) if s.type == "interface"]
        assert "Repository" in interfaces
        assert "Marker" in interfaces  # annotation type

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_detect_enum(self, java_source):
        enums = [s.name for s in _analyze(java_source) if s.type == "enum"]
        assert "Status" in enums

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_method_parent_and_kind(self, java_source):
        symbols = _analyze(java_source)
        get_value = next(s for s in symbols if s.name == "getValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"
        constructor = next(s for s in symbols if s.type == "constructor")
        assert constructor.name == "SimpleClass"
        assert constructor.parent == "SimpleClass"

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_record_method_parent(self, java_source):
        distance = next(s for s in _analyze(java_source) if s.name == "distance")
        assert distance.parent == "Point"

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_javadoc_docstring(self, java_source):
        symbols = _analyze(java_source)
        simple = next(s for s in symbols if s.name == "SimpleClass" and s.type == "class")
        assert simple.docstring == "A simple user with a name."
        get_value = next(s for s in symbols if s.name == "getValue")
        assert get_value.docstring == "Returns the stored value."

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_dependencies_from_method_invocations(self, java_source):
        get_value = next(s for s in _analyze(java_source) if s.name == "getValue")
        assert "helperMethod" in get_value.dependencies
        assert "trim" in get_value.dependencies

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_imports_collected(self, java_source):
        extractor = TreeSitterExtractor("sample_java.java", java_source, get_spec("java"))
        extractor.analyze()
        assert "java.util.List" in extractor.imports
        assert "java.util.Map" in extractor.imports

    @pytest.mark.skipif(not JAVA_AVAILABLE, reason="requires a java grammar")
    def test_signature_skips_annotations(self):
        source = 'class A {\n    @Override\n    public String toString() { return ""; }\n}\n'
        to_string = next(s for s in _analyze(source) if s.name == "toString")
        assert to_string.signature.startswith("public String toString")

    def test_line_numbers(self, java_source):
        for s in _analyze(java_source):
            assert s.line_start > 0
            assert s.line_end >= s.line_start

    def test_empty_source(self):
        assert _analyze("") == []


class TestJavaFallback:
    def test_regex_fallback_produces_symbols(self):
        source = JAVA_FIXTURE.read_text()
        symbols = GenericAnalyzer("sample_java.java", source, "java").analyze()
        assert "SimpleClass" in [s.name for s in symbols]
