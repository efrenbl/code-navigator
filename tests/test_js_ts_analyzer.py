"""Tests for JavaScript and TypeScript analyzers.

This module tests both tree-sitter-based and regex-based (fallback) analysis
for JavaScript and TypeScript files.
"""

import pytest
from pathlib import Path

from code_map_navigator.js_ts_analyzer import (
    TREE_SITTER_AVAILABLE,
    JavaScriptAnalyzer,
    TypeScriptAnalyzer,
)
from code_map_navigator.code_mapper import GenericAnalyzer


# Paths to fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
JS_FIXTURE = FIXTURES_DIR / "sample_javascript.js"
TS_FIXTURE = FIXTURES_DIR / "sample_typescript.ts"


class TestTreeSitterAvailability:
    """Tests for tree-sitter availability detection."""

    def test_tree_sitter_flag_is_boolean(self):
        """TREE_SITTER_AVAILABLE should be a boolean."""
        assert isinstance(TREE_SITTER_AVAILABLE, bool)

    def test_can_import_analyzers_regardless_of_tree_sitter(self):
        """Analyzers should be importable even without tree-sitter."""
        # This test passes if we got here - imports worked
        assert JavaScriptAnalyzer is not None
        assert TypeScriptAnalyzer is not None


class TestJavaScriptAnalyzer:
    """Tests for JavaScriptAnalyzer."""

    @pytest.fixture
    def js_source(self):
        """Load JavaScript fixture."""
        return JS_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, js_source):
        """Analyzer should return a list of symbols."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
        assert len(symbols) > 0

    def test_detect_regular_function(self, js_source):
        """Should detect regular function declarations."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        function_names = [s.name for s in symbols if s.type == "function"]
        assert "simpleFunction" in function_names

    def test_detect_async_function(self, js_source):
        """Should detect async function declarations."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        function_names = [s.name for s in symbols if s.type == "function"]
        assert "asyncFunction" in function_names

    def test_detect_arrow_function(self, js_source):
        """Should detect arrow functions assigned to variables."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        function_names = [s.name for s in symbols if s.type in ("function", "arrow")]
        assert "arrowFunction" in function_names

    def test_detect_class(self, js_source):
        """Should detect class declarations."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        class_names = [s.name for s in symbols if s.type == "class"]
        assert "SimpleClass" in class_names
        assert "DerivedClass" in class_names

    def test_detect_class_methods(self, js_source):
        """Should detect class methods."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        method_names = [s.name for s in symbols if s.type == "method"]
        assert "getValue" in method_names
        assert "setValue" in method_names

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="parent tracking requires tree-sitter")
    def test_method_parent_class(self, js_source):
        """Methods should have their parent class set (tree-sitter only)."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        get_value = next((s for s in symbols if s.name == "getValue"), None)
        assert get_value is not None
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"

    def test_symbol_has_line_numbers(self, js_source):
        """Symbols should have valid line numbers."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        for symbol in symbols:
            assert symbol.line_start > 0
            assert symbol.line_end >= symbol.line_start

    def test_symbol_has_file_path(self, js_source):
        """Symbols should have the correct file path."""
        analyzer = JavaScriptAnalyzer("test.js", js_source)
        symbols = analyzer.analyze()

        for symbol in symbols:
            assert symbol.file_path == "test.js"

    def test_empty_source(self):
        """Should handle empty source gracefully."""
        analyzer = JavaScriptAnalyzer("empty.js", "")
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
        assert len(symbols) == 0

    def test_jsx_mode(self):
        """Should accept is_jsx parameter."""
        source = """
        function App() {
            return <div>Hello</div>;
        }
        """
        analyzer = JavaScriptAnalyzer("app.jsx", source, is_jsx=True)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)


class TestJavaScriptAnalyzerInlineExamples:
    """Tests with inline JavaScript examples for precise verification."""

    def test_simple_function(self):
        """Test basic function detection."""
        source = """
function greet(name) {
    return "Hello, " + name;
}
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        assert len(symbols) >= 1
        greet = next((s for s in symbols if s.name == "greet"), None)
        assert greet is not None
        assert greet.type == "function"

    def test_async_function_signature(self):
        """Test async function detection and signature."""
        source = """
async function fetchUser(id) {
    const response = await fetch('/users/' + id);
    return response.json();
}
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        fetch_user = next((s for s in symbols if s.name == "fetchUser"), None)
        assert fetch_user is not None
        assert "async" in fetch_user.signature.lower()

    def test_class_with_extends(self):
        """Test class inheritance detection."""
        source = """
class Animal {
    speak() {
        console.log("...");
    }
}

class Dog extends Animal {
    speak() {
        console.log("Woof!");
    }
}
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        dog = next((s for s in symbols if s.name == "Dog"), None)
        assert dog is not None
        assert dog.type == "class"
        if TREE_SITTER_AVAILABLE:
            assert "extends" in dog.signature

    def test_static_method(self):
        """Test static method detection."""
        source = """
class Utils {
    static formatDate(date) {
        return date.toISOString();
    }
}
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        format_date = next((s for s in symbols if s.name == "formatDate"), None)
        assert format_date is not None
        if TREE_SITTER_AVAILABLE and format_date.type == "method":
            assert "static" in format_date.signature


class TestTypeScriptAnalyzer:
    """Tests for TypeScriptAnalyzer."""

    @pytest.fixture
    def ts_source(self):
        """Load TypeScript fixture."""
        return TS_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, ts_source):
        """Analyzer should return a list of symbols."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)
        assert len(symbols) > 0

    def test_detect_interface(self, ts_source):
        """Should detect interface declarations."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()

        interfaces = [s.name for s in symbols if s.type == "interface"]
        # At minimum, the analyzer should find some interfaces
        assert len(interfaces) > 0
        # With tree-sitter, we should find User; regex may vary
        if TREE_SITTER_AVAILABLE:
            assert "User" in interfaces
            assert "Config" in interfaces

    def test_detect_type_alias(self, ts_source):
        """Should detect type alias declarations."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()

        types = [s.name for s in symbols if s.type == "type"]
        assert "Status" in types

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="enum detection requires tree-sitter")
    def test_detect_enum(self, ts_source):
        """Should detect enum declarations (tree-sitter only)."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()

        enums = [s.name for s in symbols if s.type == "enum"]
        assert "Color" in enums
        assert "Direction" in enums

    def test_detect_class(self, ts_source):
        """Should detect class declarations."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()

        classes = [s.name for s in symbols if s.type == "class"]
        assert "UserRepository" in classes
        # Stack and other generic classes need tree-sitter for accurate detection
        if TREE_SITTER_AVAILABLE:
            assert "Stack" in classes
            assert "BaseService" in classes

    def test_detect_function(self, ts_source):
        """Should detect function declarations."""
        analyzer = TypeScriptAnalyzer("test.ts", ts_source)
        symbols = analyzer.analyze()

        functions = [s.name for s in symbols if s.type == "function"]
        assert "processUser" in functions

    def test_tsx_mode(self):
        """Should accept is_tsx parameter."""
        source = """
interface Props {
    name: string;
}

function Greeting({ name }: Props) {
    return <h1>Hello, {name}!</h1>;
}
"""
        analyzer = TypeScriptAnalyzer("component.tsx", source, is_tsx=True)
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)


class TestTypeScriptAnalyzerInlineExamples:
    """Tests with inline TypeScript examples for precise verification."""

    def test_interface_with_extends(self):
        """Test interface inheritance detection."""
        source = """
interface Base {
    id: number;
}

interface Extended extends Base {
    name: string;
}
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        extended = next((s for s in symbols if s.name == "Extended"), None)
        assert extended is not None
        assert extended.type == "interface"
        if TREE_SITTER_AVAILABLE:
            assert "extends" in extended.signature

    def test_generic_interface(self):
        """Test generic interface detection."""
        source = """
interface Container<T> {
    value: T;
    getValue(): T;
}
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        container = next((s for s in symbols if s.name == "Container"), None)
        assert container is not None
        assert container.type == "interface"
        if TREE_SITTER_AVAILABLE:
            assert "<T>" in container.signature

    def test_type_alias_union(self):
        """Test union type alias detection."""
        source = """
type Result = 'success' | 'error' | 'pending';
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        result = next((s for s in symbols if s.name == "Result"), None)
        assert result is not None
        assert result.type == "type"

    @pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="const enum detection requires tree-sitter")
    def test_const_enum(self):
        """Test const enum detection (tree-sitter only)."""
        source = """
const enum StatusCode {
    OK = 200,
    NotFound = 404,
}
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        status = next((s for s in symbols if s.name == "StatusCode"), None)
        assert status is not None
        assert status.type == "enum"
        assert "const" in status.signature

    def test_class_implements_interface(self):
        """Test class with implements clause."""
        source = """
interface Printable {
    print(): void;
}

class Document implements Printable {
    print(): void {
        console.log("Printing...");
    }
}
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        doc = next((s for s in symbols if s.name == "Document"), None)
        assert doc is not None
        assert doc.type == "class"


class TestFallbackBehavior:
    """Tests for fallback to GenericAnalyzer when tree-sitter is not available."""

    def test_javascript_fallback_produces_symbols(self):
        """Even without tree-sitter, JS analyzer should produce symbols."""
        source = """
function hello() {
    return "world";
}

class Greeter {
    greet() {
        return "Hello!";
    }
}
"""
        # Force fallback by using GenericAnalyzer directly
        fallback = GenericAnalyzer("test.js", source, "javascript")
        symbols = fallback.analyze()

        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "hello" in names
        assert "Greeter" in names

    def test_typescript_fallback_produces_symbols(self):
        """Even without tree-sitter, TS analyzer should produce symbols."""
        source = """
interface User {
    name: string;
}

type Status = 'active' | 'inactive';

function process(user: User): void {
    console.log(user.name);
}
"""
        # Force fallback by using GenericAnalyzer directly
        fallback = GenericAnalyzer("test.ts", source, "typescript")
        symbols = fallback.analyze()

        assert len(symbols) > 0
        names = [s.name for s in symbols]
        assert "User" in names
        assert "Status" in names


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_syntax_error_handling(self):
        """Should handle syntax errors gracefully."""
        source = """
function incomplete( {
    // Missing closing brace and paren
"""
        analyzer = JavaScriptAnalyzer("broken.js", source)
        # Should not raise exception
        symbols = analyzer.analyze()
        assert isinstance(symbols, list)

    def test_unicode_identifiers(self):
        """Should handle unicode in identifiers."""
        source = """
function saludar(nombre) {
    return "Hola, " + nombre;
}

const añoActual = 2024;
"""
        analyzer = JavaScriptAnalyzer("unicode.js", source)
        symbols = analyzer.analyze()

        names = [s.name for s in symbols]
        assert "saludar" in names

    def test_deeply_nested_classes(self):
        """Should handle nested structures."""
        source = """
class Outer {
    method() {
        class Inner {
            innerMethod() {
                return true;
            }
        }
        return new Inner();
    }
}
"""
        analyzer = JavaScriptAnalyzer("nested.js", source)
        symbols = analyzer.analyze()

        classes = [s.name for s in symbols if s.type == "class"]
        assert "Outer" in classes


@pytest.mark.skipif(not TREE_SITTER_AVAILABLE, reason="tree-sitter not installed")
class TestTreeSitterSpecific:
    """Tests that only run when tree-sitter is available."""

    def test_accurate_line_numbers(self):
        """Tree-sitter should provide accurate line numbers."""
        source = """// Line 1
// Line 2
function onLine3() {
    return true;
}
// Line 6
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        func = next((s for s in symbols if s.name == "onLine3"), None)
        assert func is not None
        assert func.line_start == 3

    def test_arrow_function_single_param(self):
        """Tree-sitter should handle single-param arrow functions."""
        source = """
const double = x => x * 2;
"""
        analyzer = JavaScriptAnalyzer("test.js", source)
        symbols = analyzer.analyze()

        double = next((s for s in symbols if s.name == "double"), None)
        assert double is not None
        assert double.type == "function"

    def test_typescript_generic_class(self):
        """Tree-sitter should handle generic classes."""
        source = """
class Box<T> {
    private value: T;

    constructor(value: T) {
        this.value = value;
    }

    getValue(): T {
        return this.value;
    }
}
"""
        analyzer = TypeScriptAnalyzer("test.ts", source)
        symbols = analyzer.analyze()

        box = next((s for s in symbols if s.name == "Box"), None)
        assert box is not None
        assert box.type == "class"
