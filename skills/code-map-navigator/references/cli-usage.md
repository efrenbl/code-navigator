# CLI Usage Reference

Complete reference for the `codenav` command-line interface.

## Installation

```bash
# Install via pip
pip install claude-code-navigator

# Or install from source
git clone https://github.com/efrenbl/claude-code-navigator.git
cd claude-code-navigator
pip install -e .
```

## Commands

### `codenav map` - Generate Code Map

Creates a structural index of your codebase.

```bash
# Basic usage
codenav map /path/to/project

# Git-tracked files only
codenav map . --git-only

# Incremental update (faster for large repos)
codenav map . --incremental

# Custom output file
codenav map . --output custom-map.json
```

**Options:**
- `--git-only` - Only include git-tracked files
- `--incremental` - Update only changed files
- `--output FILE` - Output file path (default: `.codenav.json`)
- `--ignore PATTERN` - Additional patterns to ignore

### `codenav search` - Find Symbols

Search for functions, classes, methods, and other symbols.

```bash
# Search by name
codenav search "process_payment"

# Filter by symbol type
codenav search "User" --type class

# Filter by file pattern
codenav search "handle" --file "*.tsx"

# Limit results
codenav search "test" --limit 10
```

**Options:**
- `--type TYPE` - Filter by: `function`, `class`, `method`, `any`
- `--file PATTERN` - Filter by file glob pattern
- `--limit N` - Maximum results (default: 20)
- `--json` - Output as JSON

### `codenav read` - Read Specific Lines

Read only the lines you need from a file.

```bash
# Read line range
codenav read src/api.py 45-89

# Read with context
codenav read src/api.py 45-89 --context 5

# Read single line
codenav read src/api.py 45
```

**Options:**
- `--context N` - Lines of context before/after
- `--json` - Output as JSON with metadata

### `codenav hubs` - Find Important Files

Identify the most connected files in your codebase.

```bash
# Top 5 hub files
codenav hubs .

# Custom number of results
codenav hubs . --top 10

# Minimum import threshold
codenav hubs . --min-imports 5
```

**Options:**
- `--top N` - Number of hubs to return (default: 5)
- `--min-imports N` - Minimum imports to qualify as hub

### `codenav deps` - Analyze Dependencies

Show import/dependency relationships.

```bash
# All dependencies for a file
codenav deps src/api.py

# Files that import this file
codenav deps src/models.py --direction imported_by

# Multi-level dependency tree
codenav deps src/app.py --depth 2
```

**Options:**
- `--direction DIR` - `imports`, `imported_by`, or `both`
- `--depth N` - Traversal depth (default: 1)
- `--json` - Output as JSON

### `codenav structure` - File Structure

Get all symbols defined in a file.

```bash
# All symbols
codenav structure src/api.py

# Include private symbols
codenav structure src/api.py --include-private

# JSON output
codenav structure src/api.py --json
```

**Options:**
- `--include-private` - Include `_private` symbols
- `--json` - Output as JSON

### `codenav stats` - Codebase Statistics

Show statistics about your indexed codebase.

```bash
codenav stats
```

Output includes:
- Total files indexed
- Lines of code
- Symbol counts by type
- Language distribution
- Hub file rankings

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CODENAV_WORKSPACE` | Default project path | Current directory |
| `CODENAV_INDEX` | Index file path | `.codenav.json` |
| `CODENAV_IGNORE` | Additional ignore patterns | None |

## Examples

### Example 1: Explore a New Codebase

```bash
cd /new/project
codenav map . --git-only
codenav stats
codenav hubs . --top 5
```

### Example 2: Find and Read a Function

```bash
codenav search "handleSubmit" --type function
# Output: src/components/Form.tsx:45

codenav read src/components/Form.tsx 40-60
```

### Example 3: Trace Dependencies

```bash
codenav deps src/core/engine.py --direction both --depth 2
```
