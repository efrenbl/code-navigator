"""Tests for the C# language spec."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.csharp import _blank_preprocessor_directives
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CS_FIXTURE = FIXTURES_DIR / "sample_csharp.cs"

CSHARP_AVAILABLE = registry.is_available("csharp")


def _analyze(source: str, path: str = "sample_csharp.cs"):
    return TreeSitterExtractor(path, source, get_spec("csharp")).analyze()


class TestPreparse:
    def test_blanks_directives_preserving_byte_length(self):
        source = "#if DEBUG\nint x;\n#endif\n"
        blanked = _blank_preprocessor_directives(source)
        assert len(blanked.encode()) == len(source.encode())
        assert blanked.split("\n")[0].strip() == ""
        assert "int x;" in blanked

    def test_non_ascii_directive_line_keeps_byte_length(self):
        source = "#region áéí\ncode();\n"
        blanked = _blank_preprocessor_directives(source)
        assert len(blanked.encode()) == len(source.encode())


class TestCSharpSpec:
    @pytest.fixture
    def cs_source(self):
        return CS_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, cs_source):
        assert len(_analyze(cs_source)) > 0

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_detect_types(self, cs_source):
        symbols = _analyze(cs_source)
        by_type = {}
        for s in symbols:
            by_type.setdefault(s.type, []).append(s.name)
        assert "SimpleClass" in by_type["class"]
        assert "Person" in by_type["class"]  # record
        assert "IRepository" in by_type["interface"]
        assert "Point" in by_type["struct"]
        assert "Coord" in by_type["struct"]  # record struct
        assert "Status" in by_type["enum"]
        assert "Handler" in by_type["type"]  # delegate
        assert "Example" in by_type["module"]  # namespace

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_enum_with_preprocessor_directives_survives(self, cs_source):
        # Historically the grammar failed on #if inside enum bodies.
        status = next(s for s in _analyze(cs_source) if s.name == "Status")
        assert status.type == "enum"

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_method_and_constructor(self, cs_source):
        symbols = _analyze(cs_source)
        get_value = next(s for s in symbols if s.name == "GetValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"
        constructor = next(s for s in symbols if s.type == "constructor")
        assert constructor.name == "SimpleClass"

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_xml_doc_comment(self, cs_source):
        get_value = next(s for s in _analyze(cs_source) if s.name == "GetValue")
        assert "Returns the stored value." in get_value.docstring

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_dependencies(self, cs_source):
        get_value = next(s for s in _analyze(cs_source) if s.name == "GetValue")
        assert "HelperMethod" in get_value.dependencies
        assert "Trim" in get_value.dependencies

    @pytest.mark.skipif(not CSHARP_AVAILABLE, reason="requires a csharp grammar")
    def test_imports_collected(self, cs_source):
        extractor = TreeSitterExtractor("sample_csharp.cs", cs_source, get_spec("csharp"))
        extractor.analyze()
        assert "System" in extractor.imports
        assert "System.Collections.Generic" in extractor.imports

    def test_empty_source(self):
        assert _analyze("") == []


class TestCSharpFallback:
    def test_regex_fallback_produces_symbols(self):
        source = CS_FIXTURE.read_text()
        symbols = GenericAnalyzer("sample_csharp.cs", source, "csharp").analyze()
        names = [s.name for s in symbols]
        assert "SimpleClass" in names
        assert "IRepository" in names
