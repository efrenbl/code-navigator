"""Tests for the PHP language spec."""

from pathlib import Path

import pytest

from codenav.code_navigator import GenericAnalyzer
from codenav.languages import get_spec, registry
from codenav.languages.extractor import TreeSitterExtractor

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PHP_FIXTURE = FIXTURES_DIR / "sample_php.php"

PHP_AVAILABLE = registry.is_available("php")


def _analyze(source: str, path: str = "sample_php.php"):
    return TreeSitterExtractor(path, source, get_spec("php")).analyze()


class TestPhpSpec:
    @pytest.fixture
    def php_source(self):
        return PHP_FIXTURE.read_text()

    def test_analyze_returns_symbols(self, php_source):
        assert len(_analyze(php_source)) > 0

    @pytest.mark.skipif(not PHP_AVAILABLE, reason="requires a php grammar")
    def test_detect_types(self, php_source):
        symbols = _analyze(php_source)
        by_type = {}
        for s in symbols:
            by_type.setdefault(s.type, []).append(s.name)
        assert "SimpleClass" in by_type["class"]
        assert "Repository" in by_type["interface"]
        assert "Loggable" in by_type["trait"]
        assert "Status" in by_type["enum"]
        assert "Example" in by_type["module"]  # namespace

    @pytest.mark.skipif(not PHP_AVAILABLE, reason="requires a php grammar")
    def test_function_and_method(self, php_source):
        symbols = _analyze(php_source)
        greet = next(s for s in symbols if s.name == "greet")
        assert greet.type == "function"
        get_value = next(s for s in symbols if s.name == "getValue")
        assert get_value.type == "method"
        assert get_value.parent == "SimpleClass"
        log = next(s for s in symbols if s.name == "log")
        assert log.parent == "Loggable"

    @pytest.mark.skipif(not PHP_AVAILABLE, reason="requires a php grammar")
    def test_docblock(self, php_source):
        greet = next(s for s in _analyze(php_source) if s.name == "greet")
        assert greet.docstring == "Greets someone by name."

    @pytest.mark.skipif(not PHP_AVAILABLE, reason="requires a php grammar")
    def test_dependencies_all_call_shapes(self, php_source):
        get_value = next(s for s in _analyze(php_source) if s.name == "getValue")
        # member call ($this->formatter->format) and function call (greet).
        assert "format" in get_value.dependencies
        assert "greet" in get_value.dependencies

    @pytest.mark.skipif(not PHP_AVAILABLE, reason="requires a php grammar")
    def test_imports_use_and_require(self, php_source):
        extractor = TreeSitterExtractor("sample_php.php", php_source, get_spec("php"))
        extractor.analyze()
        assert "Example\\Models\\User" in extractor.imports
        assert "lib/helpers.php" in extractor.imports

    def test_empty_source(self):
        assert _analyze("") == []


class TestPhpFallback:
    def test_regex_fallback_produces_symbols(self):
        symbols = GenericAnalyzer("sample_php.php", PHP_FIXTURE.read_text(), "php").analyze()
        names = [s.name for s in symbols]
        assert "greet" in names
        assert "SimpleClass" in names
