"""Tests for the code_mapper module."""

import tempfile
from pathlib import Path

import pytest

from code_map_navigator.code_mapper import (
    CodeMapper,
    GenericAnalyzer,
    PythonAnalyzer,
    Symbol,
)


class TestSymbol:
    """Tests for the Symbol dataclass."""

    def test_symbol_creation(self):
        """Test creating a Symbol with required fields."""
        symbol = Symbol(
            name="test_func",
            type="function",
            file_path="test.py",
            line_start=10,
            line_end=20,
        )
        assert symbol.name == "test_func"
        assert symbol.type == "function"
        assert symbol.line_start == 10
        assert symbol.line_end == 20

    def test_symbol_with_optional_fields(self):
        """Test creating a Symbol with all fields."""
        symbol = Symbol(
            name="TestClass",
            type="class",
            file_path="test.py",
            line_start=1,
            line_end=50,
            signature="class TestClass(Base)",
            docstring="A test class.",
            parent=None,
            dependencies=["Base", "helper"],
            decorators=["dataclass"],
        )
        assert symbol.signature == "class TestClass(Base)"
        assert symbol.docstring == "A test class."
        assert "Base" in symbol.dependencies

    def test_symbol_default_lists(self):
        """Test that mutable defaults are properly initialized."""
        symbol1 = Symbol(name="a", type="function", file_path="a.py", line_start=1, line_end=1)
        symbol2 = Symbol(name="b", type="function", file_path="b.py", line_start=1, line_end=1)

        # They should have separate lists
        symbol1.dependencies.append("test")
        assert "test" not in symbol2.dependencies


class TestPythonAnalyzer:
    """Tests for the PythonAnalyzer class."""

    def test_simple_function(self):
        """Test detecting a simple function."""
        source = '''
def hello():
    """Say hello."""
    return "Hello, World!"
'''
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert symbols[0].name == "hello"
        assert symbols[0].type == "function"
        assert "def hello()" in symbols[0].signature

    def test_function_with_types(self):
        """Test detecting a function with type hints."""
        source = '''
def greet(name: str, age: int = 0) -> str:
    """Greet someone."""
    return f"Hello, {name}!"
'''
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert "def greet(" in symbols[0].signature
        assert "name" in symbols[0].signature
        # Type hints are only available in Python 3.9+ (ast.unparse)
        # So we just verify the function is detected with its parameters

    def test_async_function(self):
        """Test detecting an async function."""
        source = """
async def fetch(url: str) -> dict:
    return {}
"""
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert "async def" in symbols[0].signature

    def test_class_with_methods(self):
        """Test detecting a class with methods."""
        source = '''
class MyClass:
    """A test class."""

    def __init__(self, value):
        self.value = value

    def get_value(self):
        return self.value
'''
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        # Should find: class + __init__ + get_value
        assert len(symbols) == 3

        class_symbol = [s for s in symbols if s.type == "class"][0]
        assert class_symbol.name == "MyClass"

        methods = [s for s in symbols if s.type == "method"]
        assert len(methods) == 2
        for method in methods:
            assert method.parent == "MyClass"

    def test_class_inheritance(self):
        """Test detecting class inheritance."""
        source = """
class Derived(Base, Mixin):
    pass
"""
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert "class Derived" in symbols[0].signature
        # Base classes in signature only available in Python 3.9+ (ast.unparse)

    def test_decorated_function(self):
        """Test detecting decorators."""
        source = """
@decorator
@another_decorator
def decorated():
    pass
"""
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert "decorator" in symbols[0].decorators
        assert "another_decorator" in symbols[0].decorators

    def test_dependency_tracking(self):
        """Test that function calls are tracked."""
        source = """
def caller():
    result = helper()
    process(result)
    return result
"""
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert "helper" in symbols[0].dependencies
        assert "process" in symbols[0].dependencies

    def test_docstring_truncation(self):
        """Test that long docstrings are truncated."""
        source = '''
def long_doc():
    """Line 1.

    Line 2.
    Line 3.
    Line 4.
    Line 5.
    """
    pass
'''
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        assert len(symbols) == 1
        assert symbols[0].docstring.endswith("...")

    def test_syntax_error_handling(self):
        """Test that syntax errors are handled gracefully."""
        source = "def broken(:"
        analyzer = PythonAnalyzer("test.py", source)
        symbols = analyzer.analyze()

        # Should return empty list, not crash
        assert symbols == []


class TestGenericAnalyzer:
    """Tests for the GenericAnalyzer class (JavaScript patterns)."""

    def test_javascript_function(self):
        """Test detecting JavaScript functions."""
        source = """
function hello() {
    return "Hello!";
}
"""
        analyzer = GenericAnalyzer("test.js", source, "javascript")
        symbols = analyzer.analyze()

        assert len(symbols) >= 1
        func = [s for s in symbols if s.name == "hello"][0]
        assert func.type == "function"

    def test_javascript_class(self):
        """Test detecting JavaScript classes."""
        source = """
class MyClass extends Base {
    constructor() {
        this.value = 0;
    }
}
"""
        analyzer = GenericAnalyzer("test.js", source, "javascript")
        symbols = analyzer.analyze()

        classes = [s for s in symbols if s.type == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "MyClass"


class TestCodeMapper:
    """Tests for the CodeMapper class."""

    def test_mapper_initialization(self):
        """Test CodeMapper initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mapper = CodeMapper(tmpdir)
            assert mapper.root_path == Path(tmpdir).resolve()
            assert mapper.symbols == []
            assert mapper.stats["files_processed"] == 0

    def test_should_ignore(self):
        """Test ignore pattern matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mapper = CodeMapper(tmpdir)

            # Should ignore
            assert mapper.should_ignore(Path(tmpdir) / "node_modules" / "test.js")
            assert mapper.should_ignore(Path(tmpdir) / "__pycache__" / "test.pyc")
            assert mapper.should_ignore(Path(tmpdir) / ".git" / "config")

            # Should not ignore
            assert not mapper.should_ignore(Path(tmpdir) / "src" / "main.py")
            assert not mapper.should_ignore(Path(tmpdir) / "lib" / "utils.js")

    def test_get_language(self):
        """Test language detection from file extension."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mapper = CodeMapper(tmpdir)

            assert mapper.get_language(Path("test.py")) == "python"
            assert mapper.get_language(Path("test.js")) == "javascript"
            assert mapper.get_language(Path("test.ts")) == "typescript"
            assert mapper.get_language(Path("test.java")) == "java"
            assert mapper.get_language(Path("test.go")) == "go"
            assert mapper.get_language(Path("test.rs")) == "rust"
            assert mapper.get_language(Path("test.txt")) is None

    def test_scan_simple_project(self):
        """Test scanning a simple project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()

            (src_dir / "main.py").write_text('''
def main():
    """Main entry point."""
    print("Hello!")

class App:
    """Main application."""
    pass
''')

            mapper = CodeMapper(tmpdir)
            result = mapper.scan()

            assert result["version"] == "1.0"
            assert result["stats"]["files_processed"] == 1
            assert result["stats"]["symbols_found"] >= 2  # main + App

            # Check files map (normalize path separators for Windows compatibility)
            file_keys = [k.replace("\\", "/") for k in result["files"].keys()]
            assert "src/main.py" in file_keys

            # Check index
            assert "main" in result["index"]
            assert "app" in result["index"]

    def test_scan_with_custom_ignore(self):
        """Test scanning with custom ignore patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files
            (Path(tmpdir) / "main.py").write_text("def keep(): pass")
            (Path(tmpdir) / "test_main.py").write_text("def ignore(): pass")

            mapper = CodeMapper(tmpdir, ignore_patterns=["test_*.py"])
            result = mapper.scan()

            assert "main.py" in result["files"]
            assert "test_main.py" not in result["files"]

    def test_generate_map_structure(self):
        """Test the structure of generated map."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.py").write_text("def hello(): pass")

            mapper = CodeMapper(tmpdir)
            result = mapper.scan()

            # Check required keys
            assert "version" in result
            assert "root" in result
            assert "generated_at" in result
            assert "stats" in result
            assert "files" in result
            assert "index" in result

            # Check stats structure
            assert "files_processed" in result["stats"]
            assert "symbols_found" in result["stats"]
            assert "errors" in result["stats"]


class TestIntegration:
    """Integration tests using the fixtures."""

    @pytest.fixture
    def fixtures_dir(self):
        """Path to test fixtures."""
        return Path(__file__).parent / "fixtures"

    def test_analyze_sample_python(self, fixtures_dir):
        """Test analyzing the sample Python fixture."""
        sample_file = fixtures_dir / "sample_python.py"
        if not sample_file.exists():
            pytest.skip("Sample fixture not found")

        with open(sample_file) as f:
            source = f.read()

        analyzer = PythonAnalyzer("sample_python.py", source)
        symbols = analyzer.analyze()

        # Check for expected symbols
        names = [s.name for s in symbols]

        assert "simple_function" in names
        assert "function_with_args" in names
        assert "async_function" in names
        assert "SimpleClass" in names
        assert "DerivedClass" in names

        # Check method detection
        methods = [s for s in symbols if s.type == "method"]
        assert any(m.name == "get_value" for m in methods)

    def test_map_fixtures_directory(self, fixtures_dir):
        """Test mapping the fixtures directory."""
        if not fixtures_dir.exists():
            pytest.skip("Fixtures directory not found")

        mapper = CodeMapper(str(fixtures_dir))
        result = mapper.scan()

        assert result["stats"]["files_processed"] >= 1
        assert result["stats"]["symbols_found"] >= 5
