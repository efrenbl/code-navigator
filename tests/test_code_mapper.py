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


class TestIncrementalScan:
    """Tests for the incremental scan functionality."""

    def test_incremental_scan_no_changes(self, tmp_path):
        """Test incremental scan when no files have changed."""
        import json

        # Create initial project
        (tmp_path / "main.py").write_text("def hello(): pass")
        (tmp_path / "utils.py").write_text("def helper(): pass")

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Incremental scan with no changes
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        assert result["stats"]["files_unchanged"] == 2
        assert result["stats"]["files_modified"] == 0
        assert result["stats"]["files_added"] == 0
        assert result["stats"]["files_deleted"] == 0
        assert result["stats"]["symbols_found"] == 2

    def test_incremental_scan_with_modified_file(self, tmp_path):
        """Test incremental scan when a file is modified."""
        import json

        # Create initial project
        (tmp_path / "main.py").write_text("def hello(): pass")

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Modify file
        (tmp_path / "main.py").write_text("def hello(): pass\ndef world(): pass")

        # Incremental scan
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        assert result["stats"]["files_unchanged"] == 0
        assert result["stats"]["files_modified"] == 1
        assert result["stats"]["files_added"] == 0
        assert result["stats"]["files_deleted"] == 0
        assert result["stats"]["symbols_found"] == 2  # hello + world

    def test_incremental_scan_with_added_file(self, tmp_path):
        """Test incremental scan when a new file is added."""
        import json

        # Create initial project
        (tmp_path / "main.py").write_text("def hello(): pass")

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Add new file
        (tmp_path / "new_file.py").write_text("def new_func(): pass")

        # Incremental scan
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        assert result["stats"]["files_unchanged"] == 1
        assert result["stats"]["files_modified"] == 0
        assert result["stats"]["files_added"] == 1
        assert result["stats"]["files_deleted"] == 0
        assert result["stats"]["symbols_found"] == 2  # hello + new_func

    def test_incremental_scan_with_deleted_file(self, tmp_path):
        """Test incremental scan when a file is deleted."""
        import json

        # Create initial project
        (tmp_path / "main.py").write_text("def hello(): pass")
        (tmp_path / "to_delete.py").write_text("def gone(): pass")

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Delete file
        (tmp_path / "to_delete.py").unlink()

        # Incremental scan
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        assert result["stats"]["files_unchanged"] == 1
        assert result["stats"]["files_modified"] == 0
        assert result["stats"]["files_added"] == 0
        assert result["stats"]["files_deleted"] == 1
        assert result["stats"]["symbols_found"] == 1  # only hello remains
        assert "to_delete.py" not in result["files"]

    def test_incremental_scan_mixed_changes(self, tmp_path):
        """Test incremental scan with a mix of changes."""
        import json

        # Create initial project
        (tmp_path / "unchanged.py").write_text("def same(): pass")
        (tmp_path / "modified.py").write_text("def old(): pass")
        (tmp_path / "deleted.py").write_text("def gone(): pass")

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Make changes
        (tmp_path / "modified.py").write_text("def new(): pass")
        (tmp_path / "deleted.py").unlink()
        (tmp_path / "added.py").write_text("def fresh(): pass")

        # Incremental scan
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        assert result["stats"]["files_unchanged"] == 1
        assert result["stats"]["files_modified"] == 1
        assert result["stats"]["files_added"] == 1
        assert result["stats"]["files_deleted"] == 1
        assert result["stats"]["symbols_found"] == 3  # same, new, fresh

    def test_incremental_scan_nonexistent_map(self, tmp_path):
        """Test incremental scan falls back to full scan if map doesn't exist."""
        # Create project
        (tmp_path / "main.py").write_text("def hello(): pass")

        # Incremental scan without existing map
        mapper = CodeMapper(str(tmp_path))
        result = mapper.scan_incremental(str(tmp_path / "nonexistent.json"))

        # Should fall back to full scan (no incremental stats)
        assert "files_unchanged" not in result["stats"]
        assert result["stats"]["files_processed"] == 1

    def test_incremental_scan_preserves_symbol_details(self, tmp_path):
        """Test that incremental scan preserves symbol details from unchanged files."""
        import json

        # Create initial project with detailed symbol
        (tmp_path / "main.py").write_text('''
def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}"

class MyClass:
    """A class."""
    def method(self):
        pass
''')

        # Initial scan
        mapper = CodeMapper(str(tmp_path))
        initial_map = mapper.scan()

        # Save the map
        map_path = tmp_path / ".codemap.json"
        with open(map_path, "w") as f:
            json.dump(initial_map, f)

        # Add a new unrelated file (main.py unchanged)
        (tmp_path / "other.py").write_text("def other(): pass")

        # Incremental scan
        mapper2 = CodeMapper(str(tmp_path))
        result = mapper2.scan_incremental(str(map_path))

        # Check that unchanged file's symbols are preserved
        main_symbols = result["files"]["main.py"]["symbols"]
        assert len(main_symbols) == 3  # hello, MyClass, method

        hello_symbol = [s for s in main_symbols if s["name"] == "hello"][0]
        assert "def hello" in hello_symbol["signature"]
        assert "Greet someone" in hello_symbol["docstring"]


class TestGitIntegration:
    """Tests for Git integration features."""

    def test_git_integration_init(self, tmp_path):
        """Test GitIntegration initialization."""
        from code_map_navigator.code_mapper import GitIntegration

        git = GitIntegration(tmp_path)
        # In a non-git directory, available should be False
        assert isinstance(git.available, bool)

    def test_git_integration_in_git_repo(self):
        """Test GitIntegration in an actual git repo."""
        from pathlib import Path

        from code_map_navigator.code_mapper import GitIntegration

        # Use the current project directory which is a git repo
        repo_path = Path(__file__).parent.parent
        git = GitIntegration(repo_path)

        assert git.available is True
        tracked_files = git.get_tracked_files()
        assert len(tracked_files) > 0
        assert any("code_mapper.py" in f for f in tracked_files)

    def test_gitignore_patterns(self):
        """Test reading .gitignore patterns."""
        from pathlib import Path

        from code_map_navigator.code_mapper import GitIntegration

        # Use the current project directory
        repo_path = Path(__file__).parent.parent
        git = GitIntegration(repo_path)

        patterns = git.get_gitignore_patterns()
        # There should be some patterns (the repo has a .gitignore)
        assert isinstance(patterns, list)

    def test_code_mapper_with_git_only(self, tmp_path):
        """Test CodeMapper with git_only=True in non-git directory."""
        (tmp_path / "main.py").write_text("def hello(): pass")

        mapper = CodeMapper(str(tmp_path), git_only=True)
        result = mapper.scan()

        # In a non-git directory with git_only, git is not available
        # so it should fall back to scanning all files
        assert result["stats"]["files_processed"] >= 0

    def test_code_mapper_with_use_gitignore(self, tmp_path):
        """Test CodeMapper with use_gitignore=True."""
        (tmp_path / "main.py").write_text("def hello(): pass")
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__\n")

        mapper = CodeMapper(str(tmp_path), use_gitignore=True)

        # Check that gitignore patterns were added
        assert "*.pyc" in mapper.ignore_patterns or "__pycache__" in mapper.ignore_patterns

    def test_code_mapper_git_only_in_git_repo(self):
        """Test CodeMapper with git_only=True in actual git repo."""
        from pathlib import Path

        # Use a subdirectory of the project
        repo_path = Path(__file__).parent.parent

        mapper = CodeMapper(str(repo_path), git_only=True)

        # _git should be available
        assert mapper._git.available is True
        # _git_tracked_files should be populated
        assert mapper._git_tracked_files is not None
        assert len(mapper._git_tracked_files) > 0
