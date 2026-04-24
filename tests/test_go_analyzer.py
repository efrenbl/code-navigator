"""Tests for Go analyzer."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.go_analyzer import TREE_SITTER_AVAILABLE, GoAnalyzer

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GO_FIXTURE = FIXTURES_DIR / "sample_go.go"


class TestTreeSitterAvailability:
    def test_tree_sitter_flag_is_boolean(self):
        assert isinstance(TREE_SITTER_AVAILABLE, bool)

    def test_can_import_analyzer_regardless_of_tree_sitter(self):
        assert GoAnalyzer is not None


class TestGoAnalyzer:
    @pytest.fixture
    def go_source(self):
        return GO_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        assert len(symbols) > 0

    def test_detect_function(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "simpleFunction" in names

    def test_detect_struct(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        structs = [s for s in symbols if s.type == "struct"]
        names = [s.name for s in structs]
        assert "User" in names

    def test_detect_interface(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        ifaces = [s for s in symbols if s.type == "interface"]
        names = [s.name for s in ifaces]
        assert "Repository" in names

    def test_detect_method(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        methods = [s for s in symbols if s.type == "method"]
        names = [s.name for s in methods]
        assert "String" in names

    def test_detect_init_function(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "init" in names

    def test_detect_test_function(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "TestSimpleFunction" in names

    def test_symbol_has_line_numbers(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        for s in symbols:
            assert s.line_start > 0
            assert s.line_end >= s.line_start

    def test_empty_source(self):
        analyzer = GoAnalyzer("empty.go", "")
        symbols = analyzer.analyze()
        assert symbols == []

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="generics require tree-sitter")
    def test_detect_generic_function(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "Map" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="parent tracking requires tree-sitter")
    def test_method_parent_type(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        string_method = next(s for s in symbols if s.name == "String")
        assert string_method.parent == "User"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="const detection requires tree-sitter")
    def test_detect_const(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        consts = [s for s in symbols if s.type == "const"]
        names = [s.name for s in consts]
        assert "StatusPending" in names
        assert "StatusActive" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="type alias requires tree-sitter")
    def test_detect_type_alias(self, go_source):
        analyzer = GoAnalyzer("sample_go.go", go_source)
        symbols = analyzer.analyze()
        types = [s for s in symbols if s.type == "type"]
        names = [s.name for s in types]
        assert "Status" in names


class TestGoAnalyzerInlineExamples:
    def test_simple_function(self):
        source = """package main

func hello() string {
    return "world"
}
"""
        analyzer = GoAnalyzer("test.go", source)
        symbols = analyzer.analyze()
        assert len(symbols) >= 1
        assert symbols[0].name == "hello"

    def test_struct_with_methods(self):
        source = """package main

type Point struct {
    X int
    Y int
}

func (p *Point) Distance() float64 {
    return 0.0
}
"""
        analyzer = GoAnalyzer("test.go", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Point" in names
        assert "Distance" in names

    def test_interface_definition(self):
        source = """package main

type Reader interface {
    Read(p []byte) (n int, err error)
}
"""
        analyzer = GoAnalyzer("test.go", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Reader" in names


class TestGoFallbackBehavior:
    def test_go_fallback_produces_symbols(self):
        source = """package main

func hello() string {
    return "world"
}

type MyStruct struct {
    Value int
}
"""
        fallback = GenericAnalyzer("test.go", source, "go")
        symbols = fallback.analyze()
        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "MyStruct" in names

    def test_go_generic_function_regex(self):
        source = """package main

func Map[T any, U any](slice []T, f func(T) U) []U {
    return nil
}
"""
        fallback = GenericAnalyzer("test.go", source, "go")
        symbols = fallback.analyze()
        names = [s.name for s in symbols]
        assert "Map" in names


class TestGoEdgeCases:
    def test_syntax_error_handling(self):
        source = "func broken( {"
        analyzer = GoAnalyzer("bad.go", source)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
