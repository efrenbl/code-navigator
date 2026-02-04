# Tests

This directory contains the test suite for Code Navigator.

## Running Tests

### Quick Start

```bash
# From project root
make test

# Or directly with pytest
python -m pytest tests/ -v
```

### With Coverage

```bash
make coverage

# View HTML report
open htmlcov/index.html
```

### Run Specific Tests

```bash
# Run a specific test file
python -m pytest tests/test_code_navigator.py -v

# Run a specific test class
python -m pytest tests/test_code_navigator.py::TestPythonAnalyzer -v

# Run a specific test
python -m pytest tests/test_code_navigator.py::TestPythonAnalyzer::test_simple_function -v

# Run tests matching a pattern
python -m pytest tests/ -k "search" -v
```

## Test Structure

```
tests/
├── __init__.py
├── test_code_navigator.py   # Tests for code_navigator.py
├── test_code_search.py   # Tests for code_search.py
├── test_line_reader.py   # Tests for line_reader.py
├── fixtures/
│   ├── sample_python.py  # Sample Python code
│   └── sample_javascript.js  # Sample JavaScript code
└── README.md
```

## Test Categories

### Unit Tests

- `test_code_navigator.py`: Tests for the CodeNavigator, PythonAnalyzer, and GenericAnalyzer classes
- `test_code_search.py`: Tests for CodeSearcher and SearchResult
- `test_line_reader.py`: Tests for LineReader and format_output

### Integration Tests

- Tests that use the fixtures directory
- Tests that create temporary files/directories

## Writing Tests

### Conventions

1. Test files should start with `test_`
2. Test functions should start with `test_`
3. Use descriptive names: `test_search_finds_exact_match`
4. Group related tests in classes

### Example Test

```python
import pytest
from codenav import CodeNavigator

def test_mapper_creates_valid_json(tmp_path):
    """Test that the mapper creates valid JSON output."""
    # Arrange
    test_file = tmp_path / "example.py"
    test_file.write_text("def hello(): pass")

    # Act
    mapper = CodeNavigator(str(tmp_path))
    result = mapper.scan()

    # Assert
    assert 'files' in result
    assert 'index' in result
    assert result['stats']['symbols_found'] >= 1
```

### Using Fixtures

```python
@pytest.fixture
def sample_codenav():
    """Create a sample code map for testing."""
    return {
        "version": "1.0",
        "files": {...},
        "index": {...}
    }

def test_search_uses_codenav(sample_codenav):
    # Use the fixture
    pass
```

## Test Data

### fixtures/sample_python.py

Contains various Python constructs:
- Functions (simple, typed, async)
- Classes (simple, inherited)
- Decorators
- Methods

### fixtures/sample_javascript.js

Contains JavaScript patterns:
- Functions
- Arrow functions
- Classes
- Async functions

## Coverage Goals

- Aim for >80% code coverage
- Focus on edge cases and error handling
- Test both success and failure paths
