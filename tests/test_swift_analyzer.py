"""Tests for the Swift language spec."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SWIFT_FIXTURE = FIXTURES_DIR / "sample_swift.swift"

SWIFT_AVAILABLE = registry.is_available("swift")


def _analyze(source: str, path: str = "sample_swift.swift"):
    return TreeSitterExtractor(path, source, get_spec("swift")).analyze()


class TestSwiftSpec:
    @pytest.fixture
    def swift_source(self):
        return SWIFT_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, swift_source):
        assert len(_analyze(swift_source)) > 0

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_classify_class_struct_enum_extension(self, swift_source):
        symbols = _analyze(swift_source)
        by_type = {}
        for s in symbols:
            by_type.setdefault(s.type, []).append(s.name)
        assert "SimpleClass" in by_type["class"]
        assert "Subclass" in by_type["class"]
        assert "Point" in by_type["struct"]
        assert "Status" in by_type["enum"]
        assert "SimpleClass" in by_type["extension"]
        assert "Repository" in by_type["protocol"]

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_method_parent_and_kind(self, swift_source):
        symbols = _analyze(swift_source)
        get_value = next(s for s in symbols if s.name == "getValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"
        farewell = next(s for s in symbols if s.name == "farewell")
        assert farewell.parent == "SimpleClass"  # extension scope

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_init_is_constructor(self, swift_source):
        constructor = next(s for s in _analyze(swift_source) if s.type == "constructor")
        assert constructor.name == "init"
        assert constructor.parent == "SimpleClass"

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_protocol_method(self, swift_source):
        find_all = next(s for s in _analyze(swift_source) if s.name == "findAll")
        assert find_all.type == "method"
        assert find_all.parent == "Repository"

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_doc_comment(self, swift_source):
        greet = next(s for s in _analyze(swift_source) if s.name == "greet")
        assert greet.docstring == "Greets someone by name."

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_dependencies_positional_calls(self, swift_source):
        get_value = next(s for s in _analyze(swift_source) if s.name == "getValue")
        assert "greet" in get_value.dependencies

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_imports_collected(self, swift_source):
        extractor = TreeSitterExtractor("sample_swift.swift", swift_source, get_spec("swift"))
        extractor.analyze()
        assert "Foundation" in extractor.imports
        assert "UIKit" in extractor.imports

    @pytest.mark.skipif(not SWIFT_AVAILABLE, reason="requires a swift grammar")
    def test_typealias(self, swift_source):
        types = [s.name for s in _analyze(swift_source) if s.type == "type"]
        assert "Handler" in types

    def test_empty_source(self):
        assert _analyze("") == []


class TestSwiftFallback:
    def test_regex_fallback_produces_symbols(self):
        source = SWIFT_FIXTURE.read_text()
        symbols = GenericAnalyzer("sample_swift.swift", source, "swift").analyze()
        names = [s.name for s in symbols]
        assert "greet" in names
        assert "SimpleClass" in names
        assert "Point" in names
