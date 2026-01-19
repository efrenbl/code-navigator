"""Tests for the code_search module."""

import json
import tempfile

import pytest

from code_map_navigator.code_search import CodeSearcher, SearchResult


@pytest.fixture
def sample_codemap():
    """Create a sample code map for testing."""
    return {
        "version": "1.0",
        "root": "/test/project",
        "generated_at": "2024-01-15T10:00:00",
        "stats": {
            "files_processed": 3,
            "symbols_found": 8,
            "errors": 0,
        },
        "files": {
            "src/main.py": {
                "hash": "abc123",
                "symbols": [
                    {
                        "name": "main",
                        "type": "function",
                        "lines": [10, 20],
                        "signature": "def main() -> None",
                        "docstring": "Main entry point.",
                        "deps": ["setup", "run"],
                    },
                    {
                        "name": "setup",
                        "type": "function",
                        "lines": [25, 35],
                        "signature": "def setup(config: dict) -> None",
                        "deps": ["load_config"],
                    },
                ],
            },
            "src/api/handlers.py": {
                "hash": "def456",
                "symbols": [
                    {
                        "name": "UserHandler",
                        "type": "class",
                        "lines": [5, 50],
                        "signature": "class UserHandler(BaseHandler)",
                        "docstring": "Handle user requests.",
                    },
                    {
                        "name": "get",
                        "type": "method",
                        "lines": [10, 25],
                        "signature": "def get(self, user_id: int)",
                        "parent": "UserHandler",
                    },
                    {
                        "name": "post",
                        "type": "method",
                        "lines": [30, 45],
                        "signature": "def post(self, data: dict)",
                        "parent": "UserHandler",
                    },
                ],
            },
            "src/utils/helpers.py": {
                "hash": "ghi789",
                "symbols": [
                    {
                        "name": "process_payment",
                        "type": "function",
                        "lines": [1, 30],
                        "signature": "def process_payment(amount: Decimal)",
                        "docstring": "Process a payment transaction.",
                        "deps": ["validate", "charge"],
                    },
                    {
                        "name": "validate",
                        "type": "function",
                        "lines": [35, 45],
                        "signature": "def validate(data: dict) -> bool",
                    },
                ],
            },
        },
        "index": {
            "main": [
                {"file": "src/main.py", "type": "function", "lines": [10, 20], "parent": None}
            ],
            "setup": [
                {"file": "src/main.py", "type": "function", "lines": [25, 35], "parent": None}
            ],
            "userhandler": [
                {"file": "src/api/handlers.py", "type": "class", "lines": [5, 50], "parent": None}
            ],
            "get": [
                {
                    "file": "src/api/handlers.py",
                    "type": "method",
                    "lines": [10, 25],
                    "parent": "UserHandler",
                }
            ],
            "post": [
                {
                    "file": "src/api/handlers.py",
                    "type": "method",
                    "lines": [30, 45],
                    "parent": "UserHandler",
                }
            ],
            "process_payment": [
                {
                    "file": "src/utils/helpers.py",
                    "type": "function",
                    "lines": [1, 30],
                    "parent": None,
                }
            ],
            "validate": [
                {
                    "file": "src/utils/helpers.py",
                    "type": "function",
                    "lines": [35, 45],
                    "parent": None,
                }
            ],
        },
    }


@pytest.fixture
def searcher(sample_codemap):
    """Create a CodeSearcher with the sample code map."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_codemap, f)
        f.flush()
        yield CodeSearcher(f.name)


class TestSearchResult:
    """Tests for the SearchResult dataclass."""

    def test_search_result_to_dict(self):
        """Test SearchResult.to_dict() method."""
        result = SearchResult(
            name="test_func",
            type="function",
            file="test.py",
            lines=[10, 20],
            signature="def test_func()",
            score=0.95,
        )

        d = result.to_dict()
        assert d["name"] == "test_func"
        assert d["type"] == "function"
        assert d["file"] == "test.py"
        assert d["lines"] == [10, 20]
        assert d["signature"] == "def test_func()"
        assert d["score"] == 0.95

    def test_search_result_optional_fields(self):
        """Test that optional fields are excluded when None."""
        result = SearchResult(
            name="test",
            type="function",
            file="test.py",
            lines=[1, 5],
            score=1.0,
        )

        d = result.to_dict()
        assert "signature" not in d
        assert "docstring" not in d
        assert "parent" not in d


class TestCodeSearcher:
    """Tests for the CodeSearcher class."""

    def test_exact_search(self, searcher):
        """Test exact symbol search."""
        results = searcher.search_symbol("main")

        assert len(results) >= 1
        assert results[0].name == "main"
        assert results[0].score == 1.0
        assert results[0].file == "src/main.py"

    def test_case_insensitive_search(self, searcher):
        """Test that search is case-insensitive."""
        results1 = searcher.search_symbol("userhandler")
        results2 = searcher.search_symbol("UserHandler")
        results3 = searcher.search_symbol("USERHANDLER")

        assert len(results1) >= 1
        assert len(results2) >= 1
        assert len(results3) >= 1

    def test_fuzzy_search(self, searcher):
        """Test fuzzy matching."""
        results = searcher.search_symbol("payment", fuzzy=True)

        assert len(results) >= 1
        # Should find process_payment
        assert any("payment" in r.name.lower() for r in results)

    def test_no_fuzzy_search(self, searcher):
        """Test that fuzzy can be disabled."""
        results = searcher.search_symbol("paymnt", fuzzy=False)  # Typo

        # Should not find anything with fuzzy disabled
        exact_matches = [r for r in results if r.score == 1.0]
        assert len(exact_matches) == 0

    def test_filter_by_type(self, searcher):
        """Test filtering by symbol type."""
        # Search for functions only
        results = searcher.search_symbol("", symbol_type="function")

        for r in results:
            assert r.type == "function"

        # Search for classes only
        results = searcher.search_symbol("handler", symbol_type="class")

        for r in results:
            assert r.type == "class"

    def test_filter_by_file_pattern(self, searcher):
        """Test filtering by file pattern."""
        results = searcher.search_symbol("", file_pattern="api/")

        for r in results:
            assert "api/" in r.file

    def test_search_limit(self, searcher):
        """Test result limiting."""
        results = searcher.search_symbol("", limit=2)

        assert len(results) <= 2

    def test_search_file(self, searcher):
        """Test file search."""
        results = searcher.search_file("handlers")

        assert len(results) >= 1
        assert any("handlers.py" in r["file"] for r in results)

    def test_get_file_structure(self, searcher):
        """Test getting file structure."""
        structure = searcher.get_file_structure("src/api/handlers.py")

        assert structure is not None
        assert structure["file"] == "src/api/handlers.py"
        assert "UserHandler" in structure["classes"]
        assert len(structure["classes"]["UserHandler"]["methods"]) == 2

    def test_get_file_structure_partial_match(self, searcher):
        """Test file structure with partial path."""
        structure = searcher.get_file_structure("handlers.py")

        assert structure is not None
        assert "handlers.py" in structure["file"]

    def test_get_file_structure_not_found(self, searcher):
        """Test file structure for non-existent file."""
        structure = searcher.get_file_structure("nonexistent.py")

        assert structure is None

    def test_find_dependencies(self, searcher):
        """Test finding dependencies."""
        deps = searcher.find_dependencies("process_payment")

        assert deps["symbol"] == "process_payment"
        assert deps["file"] == "src/utils/helpers.py"
        assert "validate" in deps["calls"]
        assert "charge" in deps["calls"]

    def test_find_dependencies_called_by(self, searcher):
        """Test finding what calls a symbol."""
        deps = searcher.find_dependencies("setup")

        # main calls setup
        called_by = [d["name"] for d in deps["called_by"]]
        assert "main" in called_by

    def test_get_stats(self, searcher):
        """Test getting codebase statistics."""
        stats = searcher.get_stats()

        assert stats["files"] == 3
        assert stats["total_symbols"] == 8
        assert "function" in stats["by_type"]
        assert "class" in stats["by_type"]
        assert "method" in stats["by_type"]


class TestSearchScoring:
    """Tests for search result scoring."""

    def test_exact_match_highest_score(self, searcher):
        """Test that exact matches get score 1.0."""
        results = searcher.search_symbol("main")

        exact = [r for r in results if r.name.lower() == "main"]
        assert all(r.score == 1.0 for r in exact)

    def test_contains_query_high_score(self, searcher):
        """Test that containing query gets high score."""
        results = searcher.search_symbol("process")

        matches = [r for r in results if "process" in r.name.lower()]
        assert all(r.score >= 0.7 for r in matches)

    def test_results_sorted_by_score(self, searcher):
        """Test that results are sorted by score descending."""
        results = searcher.search_symbol("a", limit=10)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestListByType:
    """Tests for list_by_type functionality."""

    def test_list_all_functions(self, searcher):
        """Test listing all functions."""
        results = searcher.list_by_type("function")

        assert len(results) > 0
        assert all(r.type == "function" for r in results)

    def test_list_all_classes(self, searcher):
        """Test listing all classes."""
        results = searcher.list_by_type("class")

        assert len(results) > 0
        assert all(r.type == "class" for r in results)
        class_names = [r.name for r in results]
        assert "UserHandler" in class_names

    def test_list_all_methods(self, searcher):
        """Test listing all methods."""
        results = searcher.list_by_type("method")

        assert len(results) > 0
        assert all(r.type == "method" for r in results)

    def test_list_with_file_pattern(self, searcher):
        """Test listing symbols filtered by file pattern."""
        results = searcher.list_by_type("function", file_pattern="helpers")

        assert len(results) > 0
        assert all("helpers" in r.file for r in results)

    def test_list_with_limit(self, searcher):
        """Test listing with result limit."""
        results = searcher.list_by_type("function", limit=2)

        assert len(results) <= 2

    def test_list_nonexistent_type(self, searcher):
        """Test listing a type that doesn't exist."""
        results = searcher.list_by_type("nonexistent_type")

        assert len(results) == 0

    def test_list_results_sorted(self, searcher):
        """Test that list results are sorted by file and name."""
        results = searcher.list_by_type("function")

        # Should be sorted by (file, name)
        sorted_results = sorted(results, key=lambda x: (x.file, x.name))
        assert results == sorted_results
