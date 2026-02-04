# API Reference

This document provides detailed API documentation for Code Navigator.

## Table of Contents

- [CodeNavigator](#codenavper)
- [CodeSearcher](#codesearcher)
- [LineReader](#linereader)
- [Data Classes](#data-classes)
- [Command Line Interface](#command-line-interface)

---

## CodeNavigator

The `CodeNavigator` class scans a codebase and generates a searchable index.

### Import

```python
from codenav import CodeNavigator
```

### Constructor

```python
CodeNavigator(root_path: str, ignore_patterns: List[str] = None)
```

**Parameters:**
- `root_path` (str): Path to the root directory to scan
- `ignore_patterns` (List[str], optional): Patterns to ignore. Merged with defaults.

**Example:**
```python
# Basic usage
mapper = CodeNavigator('/path/to/project')

# With custom ignore patterns
mapper = CodeNavigator('/path/to/project', ignore_patterns=['*.test.py', 'vendor/'])
```

### Methods

#### scan()

```python
def scan(self) -> Dict[str, Any]
```

Scan the entire codebase and generate a code map.

**Returns:**
- Dict containing the complete code map with files, index, and stats

**Example:**
```python
mapper = CodeNavigator('/my/project')
result = mapper.scan()

print(f"Files: {result['stats']['files_processed']}")
print(f"Symbols: {result['stats']['symbols_found']}")
```

#### analyze_file()

```python
def analyze_file(self, file_path: Path) -> List[Symbol]
```

Analyze a single file and extract its symbols.

**Parameters:**
- `file_path` (Path): Path to the file to analyze

**Returns:**
- List of Symbol objects found in the file

#### should_ignore()

```python
def should_ignore(self, path: Path) -> bool
```

Check if a path should be ignored during scanning.

**Parameters:**
- `path` (Path): Path to check

**Returns:**
- True if the path matches any ignore pattern

#### get_language()

```python
def get_language(self, file_path: Path) -> Optional[str]
```

Determine the programming language from file extension.

**Parameters:**
- `file_path` (Path): Path to the file

**Returns:**
- Language identifier string ('python', 'javascript', etc.) or None

### Class Attributes

- `LANGUAGE_EXTENSIONS`: Dict mapping language names to file extensions
- `DEFAULT_IGNORE_PATTERNS`: Default list of patterns to ignore

---

## CodeSearcher

The `CodeSearcher` class searches through a pre-built code map.

### Import

```python
from codenav import CodeSearcher
```

### Constructor

```python
CodeSearcher(map_path: str)
```

**Parameters:**
- `map_path` (str): Path to the .codenav.json file

**Example:**
```python
searcher = CodeSearcher('.codenav.json')
```

### Methods

#### search_symbol()

```python
def search_symbol(
    self,
    query: str,
    symbol_type: Optional[str] = None,
    file_pattern: Optional[str] = None,
    limit: int = 10,
    fuzzy: bool = True
) -> List[SearchResult]
```

Search for symbols by name.

**Parameters:**
- `query` (str): Symbol name or pattern to search for
- `symbol_type` (str, optional): Filter by type ('function', 'class', 'method')
- `file_pattern` (str, optional): Regex pattern to filter by file path
- `limit` (int): Maximum results to return (default: 10)
- `fuzzy` (bool): Enable fuzzy matching (default: True)

**Returns:**
- List of SearchResult objects sorted by relevance score

**Example:**
```python
# Basic search
results = searcher.search_symbol('payment')

# Filter by type
results = searcher.search_symbol('User', symbol_type='class')

# Filter by file
results = searcher.search_symbol('handler', file_pattern='api/')

# Exact match only
results = searcher.search_symbol('main', fuzzy=False)
```

#### list_by_type()

```python
def list_by_type(
    self,
    symbol_type: str,
    file_pattern: Optional[str] = None,
    limit: int = 100
) -> List[SearchResult]
```

List all symbols of a specific type without requiring a search query.

**Parameters:**
- `symbol_type` (str): Type to filter by ('function', 'class', 'method', etc.)
- `file_pattern` (str, optional): Regex pattern to filter by file path
- `limit` (int): Maximum results to return (default: 100)

**Returns:**
- List of SearchResult objects sorted by file path and name

**Example:**
```python
# List all classes in the codebase
classes = searcher.list_by_type('class')
for c in classes:
    print(f"{c.name} in {c.file}:{c.lines[0]}")

# List all functions in a specific directory
functions = searcher.list_by_type('function', file_pattern='api/')

# List methods with a limit
methods = searcher.list_by_type('method', limit=50)
```

**CLI Usage:**
```bash
# List all classes
codenav search --type class

# List all functions in api/
codenav search --type function --file "api/"
```

#### search_file()

```python
def search_file(self, pattern: str, limit: int = 20) -> List[Dict]
```

Search for files by path pattern.

**Parameters:**
- `pattern` (str): Regex pattern or substring to match
- `limit` (int): Maximum results (default: 20)

**Returns:**
- List of dicts with file info (path, hash, symbol counts)

**Example:**
```python
files = searcher.search_file('models/')
for f in files:
    print(f"{f['file']}: {f['total_symbols']} symbols")
```

#### get_file_structure()

```python
def get_file_structure(self, file_path: str) -> Optional[Dict]
```

Get the structure of a specific file.

**Parameters:**
- `file_path` (str): Path to the file (can be partial)

**Returns:**
- Dict with classes, functions, and other symbols, or None

**Example:**
```python
structure = searcher.get_file_structure('src/api/handlers.py')
print(list(structure['classes'].keys()))
```

#### find_dependencies()

```python
def find_dependencies(
    self,
    symbol_name: str,
    file_path: Optional[str] = None
) -> Dict
```

Find what a symbol depends on and what depends on it.

**Parameters:**
- `symbol_name` (str): Name of the symbol to analyze
- `file_path` (str, optional): File path filter

**Returns:**
- Dict with 'calls' and 'called_by' lists

**Example:**
```python
deps = searcher.find_dependencies('process_payment')
print(f"Calls: {deps['calls']}")
print(f"Called by: {len(deps['called_by'])} functions")
```

#### get_stats()

```python
def get_stats(self) -> Dict
```

Get statistics about the codebase.

**Returns:**
- Dict with root path, generation time, file count, symbol count, and breakdown by type

---

## LineReader

The `LineReader` class reads specific lines from files.

### Import

```python
from codenav import LineReader
```

### Constructor

```python
LineReader(root_path: Optional[str] = None)
```

**Parameters:**
- `root_path` (str, optional): Base directory for resolving relative paths

**Example:**
```python
reader = LineReader('/my/project')
```

### Methods

#### read_lines()

```python
def read_lines(
    self,
    file_path: str,
    start: int,
    end: Optional[int] = None,
    context: int = 0
) -> Dict
```

Read specific lines from a file.

**Parameters:**
- `file_path` (str): Path to the file
- `start` (int): Starting line number (1-indexed)
- `end` (int, optional): Ending line number (defaults to start)
- `context` (int): Number of context lines

**Returns:**
- Dict with file, requested/actual ranges, total_lines, and lines list

**Example:**
```python
result = reader.read_lines('src/api.py', 45, 60, context=2)
for line in result['lines']:
    marker = '>' if line['in_range'] else ' '
    print(f"{marker}{line['num']}: {line['content']}")
```

#### read_ranges()

```python
def read_ranges(
    self,
    file_path: str,
    ranges: List[Tuple[int, int]],
    context: int = 0,
    collapse_gap: int = 5
) -> Dict
```

Read multiple line ranges from a file.

**Parameters:**
- `file_path` (str): Path to the file
- `ranges` (List[Tuple[int, int]]): List of (start, end) tuples
- `context` (int): Context lines for each range
- `collapse_gap` (int): Merge ranges if gap is smaller

**Returns:**
- Dict with file, total_lines, and sections list

**Example:**
```python
ranges = [(10, 20), (45, 55), (100, 110)]
result = reader.read_ranges('api.py', ranges, context=2)
print(f"Got {len(result['sections'])} sections")
```

#### read_symbol()

```python
def read_symbol(
    self,
    file_path: str,
    start: int,
    end: int,
    include_context: bool = True,
    max_lines: int = 100
) -> Dict
```

Read a symbol with smart truncation.

**Parameters:**
- `file_path` (str): Path to the file
- `start` (int): Symbol start line
- `end` (int): Symbol end line
- `include_context` (bool): Add context lines
- `max_lines` (int): Maximum lines before truncation

**Returns:**
- Dict with file, range, truncated flag, and lines

**Example:**
```python
result = reader.read_symbol('api.py', 100, 300, max_lines=50)
if result['truncated']:
    print(f"Skipped {result['skipped_lines']} lines")
```

#### search_in_file()

```python
def search_in_file(
    self,
    file_path: str,
    pattern: str,
    context: int = 2,
    max_matches: int = 10
) -> Dict
```

Search for a pattern in a file.

**Parameters:**
- `file_path` (str): Path to the file
- `pattern` (str): Regex or literal pattern
- `context` (int): Context lines around matches
- `max_matches` (int): Maximum matches

**Returns:**
- Dict with file, pattern, matches count, and sections

---

## Data Classes

### Symbol

```python
@dataclass
class Symbol:
    name: str
    type: str  # 'function', 'class', 'method', etc.
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent: Optional[str] = None
    dependencies: List[str] = None
    decorators: List[str] = None
```

### SearchResult

```python
@dataclass
class SearchResult:
    name: str
    type: str
    file: str
    lines: List[int]
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent: Optional[str] = None
    score: float = 0.0

    def to_dict(self) -> Dict: ...
```

---

## Command Line Interface

### codenav map

```bash
codenav map PATH [-o OUTPUT] [-i IGNORE...] [--pretty] [-v]
```

**Options:**
- `PATH`: Root directory to scan
- `-o, --output`: Output file (default: .codenav.json)
- `-i, --ignore`: Additional ignore patterns
- `--pretty`: Pretty-print JSON
- `-v, --version`: Show version

### codenav search

```bash
codenav search QUERY [-m MAP] [-t TYPE] [-f FILE] [-l LIMIT] [--no-fuzzy] [--pretty]
codenav search --structure FILE
codenav search --deps SYMBOL
codenav search --stats
```

**Options:**
- `QUERY`: Search query
- `-m, --map`: Code map file (default: .codenav.json)
- `-t, --type`: Filter by symbol type
- `-f, --file`: Filter by file pattern
- `-l, --limit`: Max results (default: 10)
- `--no-fuzzy`: Disable fuzzy matching
- `--structure`: Show file structure
- `--deps`: Show dependencies
- `--stats`: Show codebase stats
- `--pretty`: Pretty-print JSON

### codenav read

```bash
codenav read FILE LINES [-r ROOT] [-c CONTEXT] [--symbol] [--max-lines N] [-o FORMAT]
codenav read FILE --search PATTERN
```

**Options:**
- `FILE`: File to read
- `LINES`: Line range (e.g., "10", "10-20", "10,20,30-40")
- `-r, --root`: Root directory
- `-c, --context`: Context lines
- `--symbol`: Smart truncation mode
- `--max-lines`: Max lines before truncation
- `-s, --search`: Search pattern
- `-o, --output`: Format ('json' or 'code')
