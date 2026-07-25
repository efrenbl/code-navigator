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


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not available")
class TestGoEnrichment:
    """v0.4.1 parity features: visibility, vars, generic receivers, return types."""

    def _analyze(self, source):
        return GoAnalyzer("test.go", source).analyze()

    def test_visibility_exported_vs_unexported(self):
        symbols = self._analyze("package main\n\nfunc Public() {}\n\nfunc private() {}\n")
        by_name = {s.name: s for s in symbols}
        assert by_name["Public"].visibility is None
        assert by_name["private"].visibility == "private"

    def test_struct_and_interface_visibility(self):
        symbols = self._analyze(
            "package main\n\ntype hidden struct{}\n\ntype Visible interface{}\n"
        )
        by_name = {s.name: s for s in symbols}
        assert by_name["hidden"].visibility == "private"
        assert by_name["Visible"].visibility is None

    def test_package_level_var(self):
        symbols = self._analyze(
            "package main\n\n// ErrNotFound is returned when missing.\n"
            'var ErrNotFound = errors.New("not found")\n'
        )
        var = next(s for s in symbols if s.type == "variable")
        assert var.name == "ErrNotFound"
        assert var.docstring == "ErrNotFound is returned when missing."

    def test_var_spec_multiple_identifiers(self):
        symbols = self._analyze("package main\n\nvar a, b = 1, 2\n")
        names = [s.name for s in symbols if s.type == "variable"]
        assert names == ["a", "b"]

    def test_function_local_vars_skipped(self):
        symbols = self._analyze(
            "package main\n\nfunc run() {\n    var local = 1\n    _ = local\n}\n"
        )
        assert [s.name for s in symbols if s.type == "variable"] == []

    def test_const_spec_multiple_identifiers_and_doc(self):
        symbols = self._analyze(
            "package main\n\n// Limits for the pool.\nconst MinSize, MaxSize = 1, 10\n"
        )
        consts = [s for s in symbols if s.type == "const"]
        assert [s.name for s in consts] == ["MinSize", "MaxSize"]
        assert consts[0].docstring == "Limits for the pool."

    def test_generic_receiver_binds_method_to_type(self):
        symbols = self._analyze(
            "package main\n\ntype Stack[T any] struct{}\n\nfunc (s *Stack[T]) Push(v T) {}\n"
        )
        push = next(s for s in symbols if s.name == "Push")
        assert push.parent == "Stack"
        assert push.signature == "func (s *Stack[T]) Push(v T)"

    def test_return_type_first_of_multi_return(self):
        symbols = self._analyze(
            "package main\n\nfunc NewUser() (*User, error) { return nil, nil }\n"
        )
        assert symbols[0].return_type == "User"

    def test_return_type_qualified_and_generic(self):
        symbols = self._analyze(
            "package main\n\nfunc load() pkg.Thing[int] { return pkg.Thing[int]{} }\n"
        )
        assert symbols[0].return_type == "Thing"

    def test_return_type_absent(self):
        symbols = self._analyze("package main\n\nfunc run() {}\n")
        assert symbols[0].return_type is None

    def test_interface_methods_extracted(self):
        symbols = self._analyze(
            "package main\n\n"
            "type Core interface {\n"
            "    // Marshal encodes v.\n"
            "    Marshal(v any) ([]byte, error)\n"
            "    io.Reader\n"
            "}\n"
        )
        marshal = next(s for s in symbols if s.name == "Marshal")
        assert marshal.type == "method"
        assert marshal.parent == "Core"
        assert marshal.return_type == "byte" or marshal.return_type is None
        # Embedded interfaces are not symbols.
        assert not any(s.name == "Reader" for s in symbols)
