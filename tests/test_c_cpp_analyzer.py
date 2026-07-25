"""Tests for the C and C++ language specs (shared declarator machinery)."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
C_FIXTURE = FIXTURES_DIR / "sample_c.c"
CPP_FIXTURE = FIXTURES_DIR / "sample_cpp.cpp"

C_AVAILABLE = registry.is_available("c")
CPP_AVAILABLE = registry.is_available("cpp")


def _analyze_c(source: str, path: str = "sample_c.c"):
    return TreeSitterExtractor(path, source, get_spec("c")).analyze()


def _analyze_cpp(source: str, path: str = "sample_cpp.cpp"):
    return TreeSitterExtractor(path, source, get_spec("cpp")).analyze()


class TestCSpec:
    @pytest.fixture
    def c_source(self):
        return C_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, c_source):
        assert len(_analyze_c(c_source)) > 0

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_functions_with_declarator_chains(self, c_source):
        functions = [s.name for s in _analyze_c(c_source) if s.type == "function"]
        assert "simple_function" in functions
        assert "pointer_function" in functions  # name behind pointer_declarator
        assert "main" in functions

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_prototype_extracted(self, c_source):
        proto = next(s for s in _analyze_c(c_source) if s.name == "prototype_function")
        assert proto.type == "function"
        assert proto.signature == "int prototype_function(int value)"

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_struct_enum_union_typedef(self, c_source):
        symbols = _analyze_c(c_source)
        by_type = {}
        for s in symbols:
            by_type.setdefault(s.type, []).append(s.name)
        assert "point" in by_type["struct"]
        assert "color" in by_type["enum"]
        assert "value" in by_type["union"]
        assert "point_t" in by_type["type"]
        assert "uint_alias" in by_type["type"]

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_forward_declaration_skipped(self, c_source):
        names = [s.name for s in _analyze_c(c_source)]
        assert "forward_declaration" not in names

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_block_comment_docstring(self, c_source):
        add = next(s for s in _analyze_c(c_source) if s.name == "simple_function")
        assert add.docstring == "Adds two integers together."

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_dependencies(self, c_source):
        add = next(s for s in _analyze_c(c_source) if s.name == "simple_function")
        assert "helper_function" in add.dependencies

    @pytest.mark.skipif(not C_AVAILABLE, reason="requires a c grammar")
    def test_includes_as_imports(self, c_source):
        extractor = TreeSitterExtractor("sample_c.c", c_source, get_spec("c"))
        extractor.analyze()
        assert "stdio.h" in extractor.imports
        assert "local_header.h" in extractor.imports

    def test_empty_source(self):
        assert _analyze_c("") == []


class TestCppSpec:
    @pytest.fixture
    def cpp_source(self):
        return CPP_FIXTURE.read_text()

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_class_and_namespace(self, cpp_source):
        symbols = _analyze_cpp(cpp_source)
        classes = [s.name for s in symbols if s.type == "class"]
        assert "SimpleClass" in classes
        modules = [s.name for s in symbols if s.type == "module"]
        assert "example" in modules

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_inline_method_parent(self, cpp_source):
        get_value = next(s for s in _analyze_cpp(cpp_source) if s.name == "getValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_method_declaration_inside_class(self, cpp_source):
        declared = next(s for s in _analyze_cpp(cpp_source) if s.name == "declaredOnly")
        assert declared.parent == "SimpleClass"

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_out_of_line_member_parent_from_qualified_name(self, cpp_source):
        symbols = _analyze_cpp(cpp_source)
        # SimpleClass::SimpleClass out-of-line definition → constructor.
        constructors = [s for s in symbols if s.type == "constructor"]
        assert any(s.parent == "SimpleClass" for s in constructors)
        helper = next(s for s in symbols if s.name == "helperMethod" and s.line_start > 20)
        assert helper.type == "method"
        assert helper.parent == "SimpleClass"

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_template_function(self, cpp_source):
        twice = next(s for s in _analyze_cpp(cpp_source) if s.name == "twice")
        assert twice.type == "function"
        assert "dup" in twice.dependencies

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_struct_and_enum_class(self, cpp_source):
        symbols = _analyze_cpp(cpp_source)
        assert "Point" in [s.name for s in symbols if s.type == "struct"]
        assert "Color" in [s.name for s in symbols if s.type == "enum"]

    @pytest.mark.skipif(not CPP_AVAILABLE, reason="requires a cpp grammar")
    def test_doc_comment(self, cpp_source):
        simple = next(
            s for s in _analyze_cpp(cpp_source) if s.name == "SimpleClass" and s.type == "class"
        )
        assert simple.docstring == "A simple user with a name."

    def test_empty_source(self):
        assert _analyze_cpp("") == []


class TestCFallback:
    def test_c_regex_fallback(self):
        symbols = GenericAnalyzer("sample_c.c", C_FIXTURE.read_text(), "c").analyze()
        names = [s.name for s in symbols]
        assert "simple_function" in names
        assert "point" in names

    def test_cpp_regex_fallback(self):
        symbols = GenericAnalyzer("sample_cpp.cpp", CPP_FIXTURE.read_text(), "cpp").analyze()
        names = [s.name for s in symbols]
        assert "SimpleClass" in names
