# Contributing to Claude Code Navigator

Thank you for your interest in contributing! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Running Tests](#running-tests)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

This project follows a simple code of conduct: be respectful, be constructive, and be collaborative. We welcome contributors of all experience levels.

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git
- Make (optional, but recommended)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/claude-code-navigator.git
   cd claude-code-navigator
   ```

3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/efrenbl/claude-code-navigator.git
   ```

## Development Setup

### Option 1: Using Make (Recommended)

```bash
# Set up development environment
make dev-setup

# This will:
# - Create a virtual environment
# - Install dependencies
# - Install pre-commit hooks
```

### Option 2: Manual Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Or using requirements files
pip install -r requirements.txt
pip install -r dev-requirements.txt
```

### Verify Setup

```bash
# Run tests to verify everything works
make test

# Or manually
python -m pytest tests/ -v
```

## Code Style

We follow **PEP 8** with some additional guidelines:

### Python Style Guidelines

1. **Line Length**: Maximum 100 characters
2. **Imports**: Group in order: standard library, third-party, local
3. **Docstrings**: Google style docstrings for all public functions/classes
4. **Type Hints**: Use type hints for function parameters and return values

### Docstring Example

```python
def search_symbol(
    self,
    query: str,
    symbol_type: Optional[str] = None,
    limit: int = 10
) -> List[SearchResult]:
    """Search for symbols by name.

    Performs fuzzy matching against the code map index to find
    functions, classes, methods, and other symbols.

    Args:
        query: Symbol name or pattern to search for.
        symbol_type: Filter by type ('function', 'class', 'method').
        limit: Maximum number of results to return.

    Returns:
        List of SearchResult objects sorted by relevance score.

    Raises:
        FileNotFoundError: If the code map file doesn't exist.

    Example:
        >>> searcher = CodeSearcher('.codemap.json')
        >>> results = searcher.search_symbol('process', symbol_type='function')
        >>> print(results[0].name)
        'process_payment'
    """
```

### Code Formatting

We use the following tools:

- **black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking (optional but encouraged)

```bash
# Format code
make format

# Check linting
make lint

# Or manually
black src/ tests/
isort src/ tests/
flake8 src/ tests/
```

## Running Tests

### Run All Tests

```bash
make test

# Or manually
python -m pytest tests/ -v
```

### Run Specific Tests

```bash
# Run a specific test file
python -m pytest tests/test_code_mapper.py -v

# Run a specific test
python -m pytest tests/test_code_mapper.py::test_python_analyzer -v

# Run with coverage
make coverage
```

### Test Structure

```
tests/
├── __init__.py
├── test_code_mapper.py    # Tests for code_mapper.py
├── test_code_search.py    # Tests for code_search.py
├── test_line_reader.py    # Tests for line_reader.py
├── fixtures/
│   ├── sample_python.py   # Sample Python code for testing
│   ├── sample_js.js       # Sample JavaScript code
│   └── sample_codemap.json
└── README.md
```

### Writing Tests

1. Test file names should start with `test_`
2. Test function names should be descriptive: `test_search_finds_exact_match`
3. Use fixtures for common test data
4. Test both success and error cases

```python
import pytest
from code_map_navigator import CodeMapper

def test_mapper_creates_valid_json(tmp_path):
    """Test that the mapper creates valid JSON output."""
    # Create test file
    test_file = tmp_path / "example.py"
    test_file.write_text("def hello(): pass")

    # Run mapper
    mapper = CodeMapper(str(tmp_path))
    result = mapper.scan()

    # Verify
    assert 'files' in result
    assert 'index' in result
    assert result['stats']['symbols_found'] >= 1
```

## Pull Request Process

### Before Submitting

1. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** and commit with clear messages:
   ```bash
   git commit -m "Add fuzzy matching threshold option to search"
   ```

3. **Run tests and linting**:
   ```bash
   make test
   make lint
   ```

4. **Update documentation** if needed (README, docstrings, etc.)

### Submitting

1. Push your branch to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template with:
   - Description of changes
   - Related issue (if any)
   - Testing done
   - Screenshots (if UI changes)

### PR Review Process

- All PRs require at least one review
- CI checks must pass
- Address review feedback promptly
- Squash commits when merging (handled automatically)

### PR Checklist

- [ ] Tests pass locally
- [ ] Code follows style guidelines
- [ ] Documentation updated (if needed)
- [ ] Changelog updated (for user-facing changes)
- [ ] Commit messages are clear

## Reporting Issues

### Bug Reports

When filing a bug report, include:

1. **Python version**: `python --version`
2. **OS**: Windows/macOS/Linux
3. **Steps to reproduce**
4. **Expected behavior**
5. **Actual behavior**
6. **Error messages** (if any)

Use the bug report template: [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md)

### Feature Requests

For feature requests:

1. Describe the problem you're trying to solve
2. Describe your proposed solution
3. Consider alternatives
4. Note if you're willing to implement it

Use the feature request template: [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md)

## Project Structure

```
claude-code-navigator/
├── src/
│   └── code_map_navigator/
│       ├── __init__.py
│       ├── code_mapper.py
│       ├── code_search.py
│       └── line_reader.py
├── tests/
├── docs/
├── examples/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   └── workflows/
├── pyproject.toml
├── Makefile
└── README.md
```

## Questions?

Feel free to:
- Open an issue for questions
- Start a discussion on GitHub Discussions
- Reach out to maintainers

Thank you for contributing!
