"""Tests for Rust analyzer."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.rust_analyzer import TREE_SITTER_AVAILABLE, RustAnalyzer

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RS_FIXTURE = FIXTURES_DIR / "sample_rust.rs"


class TestTreeSitterAvailability:
    def test_tree_sitter_flag_is_boolean(self):
        assert isinstance(TREE_SITTER_AVAILABLE, bool)

    def test_can_import_analyzer_regardless_of_tree_sitter(self):
        assert RustAnalyzer is not None


class TestRustAnalyzer:
    @pytest.fixture
    def rs_source(self):
        return RS_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        assert len(symbols) > 0

    def test_detect_struct(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        structs = [s for s in symbols if s.type == "struct"]
        names = [s.name for s in structs]
        assert "User" in names
        assert "Container" in names

    def test_detect_trait(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        traits = [s for s in symbols if s.type == "trait"]
        names = [s.name for s in traits]
        assert "Greetable" in names

    def test_detect_enum(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        enums = [s for s in symbols if s.type == "enum"]
        names = [s.name for s in enums]
        assert "Status" in names

    def test_detect_impl(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        impls = [s for s in symbols if s.type == "impl"]
        names = [s.name for s in impls]
        assert "User" in names

    def test_detect_function(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        funcs = [s for s in symbols if s.type == "function"]
        names = [s.name for s in funcs]
        assert "map_vec" in names
        assert "fetch_data" in names
        assert "test_user_new" in names

    def test_detect_method_in_impl(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        methods = [s for s in symbols if s.type == "method"]
        names = [s.name for s in methods]
        assert "new" in names
        assert "validate" in names
        assert "fmt" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="parent tracking requires tree-sitter")
    def test_method_parent_type(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        new_method = next(s for s in symbols if s.name == "new" and s.type == "method")
        assert new_method.parent == "User"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="async detection requires tree-sitter")
    def test_detect_async_function(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        fetch = next(s for s in symbols if s.name == "fetch_data")
        assert "async" in (fetch.signature or "")

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="generics require tree-sitter")
    def test_detect_generic_struct(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        container = next(s for s in symbols if s.name == "Container")
        assert "<T>" in (container.signature or "")

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="generics require tree-sitter")
    def test_detect_generic_function(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        map_vec = next(s for s in symbols if s.name == "map_vec")
        assert "<T, U>" in (map_vec.signature or "")

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="const requires tree-sitter")
    def test_detect_const(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        consts = [s for s in symbols if s.type == "const"]
        names = [s.name for s in consts]
        assert "MAX_SIZE" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="type alias requires tree-sitter")
    def test_detect_type_alias(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        types = [s for s in symbols if s.type == "type"]
        names = [s.name for s in types]
        assert "Result" in names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="module requires tree-sitter")
    def test_detect_module(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        mods = [s for s in symbols if s.type == "module"]
        names = [s.name for s in mods]
        assert "tests" in names

    def test_symbol_has_line_numbers(self, rs_source):
        analyzer = RustAnalyzer("sample_rust.rs", rs_source)
        symbols = analyzer.analyze()
        for s in symbols:
            assert s.line_start > 0
            assert s.line_end >= s.line_start

    def test_empty_source(self):
        analyzer = RustAnalyzer("empty.rs", "")
        symbols = analyzer.analyze()
        assert symbols == []


class TestRustAnalyzerInlineExamples:
    def test_simple_function(self):
        source = """
fn hello() -> String {
    "world".to_string()
}
"""
        analyzer = RustAnalyzer("test.rs", source)
        symbols = analyzer.analyze()
        assert len(symbols) >= 1
        assert symbols[0].name == "hello"

    def test_struct_with_impl(self):
        source = """
struct Point {
    x: f64,
    y: f64,
}

impl Point {
    fn distance(&self) -> f64 {
        (self.x * self.x + self.y * self.y).sqrt()
    }
}
"""
        analyzer = RustAnalyzer("test.rs", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Point" in names
        assert "distance" in names

    def test_trait_and_impl(self):
        source = """
trait Shape {
    fn area(&self) -> f64;
}

struct Circle {
    radius: f64,
}

impl Shape for Circle {
    fn area(&self) -> f64 {
        3.14159 * self.radius * self.radius
    }
}
"""
        analyzer = RustAnalyzer("test.rs", source)
        symbols = analyzer.analyze()
        names = [s.name for s in symbols]
        assert "Shape" in names
        assert "Circle" in names
        assert "area" in names


class TestRustFallbackBehavior:
    def test_rust_fallback_produces_symbols(self):
        source = """
pub fn hello() -> String {
    "world".to_string()
}

pub struct MyStruct {
    value: i32,
}

impl MyStruct {
    fn get_value(&self) -> i32 {
        self.value
    }
}
"""
        fallback = GenericAnalyzer("test.rs", source, "rust")
        symbols = fallback.analyze()
        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "MyStruct" in names


class TestRustEdgeCases:
    def test_syntax_error_handling(self):
        source = "fn broken( { }"
        analyzer = RustAnalyzer("bad.rs", source)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
