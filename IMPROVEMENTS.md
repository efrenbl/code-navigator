# Future Improvements - Claude Code Navigator

This document tracks potential improvements and enhancements for the project.

---

## Completed

### Incremental map updates
**Status:** Completed in v1.2.0

Added `--incremental` flag to update only changed files instead of regenerating the entire map:

```bash
# Initial full scan
codenav map . -o .codenav.json

# Subsequent incremental updates (much faster)
codenav map . -o .codenav.json --incremental
```

Output shows what changed:
```
Incremental scan at: /path/to/project
Existing map has 142 files
  Unchanged: 138
  Modified: 2
  Added: 1
  Deleted: 1
```

Features:
- Compares file hashes to detect changes
- Only re-analyzes modified and new files
- Preserves symbol data from unchanged files
- Falls back to full scan if no existing map

### Short command aliases (`codenav` unified CLI)
**Status:** Completed in v1.2.0

Added unified `codenav` command with subcommands:

```bash
# Before (still works for backward compatibility)
codenav scan /path/to/project -o .codenav.json
code-search "UserService" --type class
code-read src/api.py 45-60

# After (new unified CLI)
codenav map /path/to/project -o .codenav.json
codenav search "UserService" --type class
codenav read src/api.py 45-60
codenav stats  # shortcut for search --stats
```

Implementation:
- New `cli.py` with argparse subparsers
- Refactored modules with `add_*_arguments()` and `run_*()` functions
- Legacy commands maintained for backward compatibility

### Terminal colors
**Status:** Completed in v1.2.0

Added colored output for better terminal readability:

```bash
# Table format with colors
code-search --stats -o table
code-search "User" -o table

# Code output with colors
code-read src/api.py 10-20 -o code

# Disable colors
code-search --stats -o table --no-color
```

Color scheme:
- Green: found symbols, success messages
- Cyan: file paths, line numbers
- Magenta: symbol types
- Yellow: line ranges
- Dim: context lines

Respects `NO_COLOR` environment variable.

### Pretty output by default
**Status:** Completed in v1.1.0

All commands now output pretty-printed JSON by default for better readability:

```bash
# Pretty output (default)
code-search --stats
code-read src/api.py 10-20

# Compact output when needed
code-search --stats --compact
code-read src/api.py 10-20 --compact
```

### List symbols by type without query
**Status:** Fixed in v1.0.1

Added `list_by_type()` method to `CodeSearcher` class. Now you can list all symbols of a specific type:

```bash
# List all classes
code-search --type class

# List all functions in a specific directory
code-search --type function --file "src/api/"
```

### AST support for JavaScript/TypeScript
**Status:** Completed in v1.3.0

Added tree-sitter based AST parsing for JavaScript and TypeScript files as an optional dependency:

```bash
# Install with AST support
pip install claude-code-navigator[ast]

# Without AST (regex fallback, zero dependencies)
pip install claude-code-navigator
```

Features:
- Accurate symbol detection using tree-sitter
- Support for JSX/TSX files
- TypeScript interfaces, type aliases, and enums
- Automatic fallback to regex when tree-sitter not installed

New module `js_ts_analyzer.py` with:
- `JavaScriptAnalyzer` - Parses JS/JSX with tree-sitter
- `TypeScriptAnalyzer` - Extends JS analyzer for TS/TSX
- `TREE_SITTER_AVAILABLE` - Flag to check if tree-sitter is installed

Symbols detected:

| Language | Symbols |
|----------|---------|
| JavaScript | function, arrow function, class, method |
| TypeScript | + interface, type alias, enum |

### Automatic change detection
**Status:** Completed in v1.3.0

Warn when files have changed since map generation:

```bash
# Check if map is stale
codenav search --check-stale

# Warn before showing results
codenav search "user" --warn-stale
```

Output shows:
```
Stale File Check
  Generated: 2024-01-15T10:00:00
  Files checked: 142
  Modified (3):
    src/api/handlers.py
    src/models/user.py
    src/utils.py

Run 'codenav map --incremental' to update the map.
```

Features:
- `check_stale_files()` method in `CodeSearcher`
- `--check-stale` flag to explicitly check for stale files
- `--warn-stale` flag to warn before showing search results
- Compares current file hashes with stored hashes

### Git integration
**Status:** Completed in v1.3.0

Added git integration features:

```bash
# Only map git-tracked files
codenav map . --git-only

# Use .gitignore patterns
codenav map . --use-gitignore

# Show symbols in files changed since a commit
codenav search --since-commit HEAD~5
codenav search --since-commit main
codenav search --since-commit abc123
```

Features:
- `--git-only` flag: Only scan files tracked by git
- `--use-gitignore` flag: Add .gitignore patterns to ignore list
- `--since-commit` flag: Show symbols in files changed since a commit
- `GitIntegration` helper class with:
  - `get_tracked_files()` - Get all git-tracked files
  - `get_gitignore_patterns()` - Parse .gitignore
  - `get_files_changed_since()` - Files changed since commit
  - `get_uncommitted_changes()` - Files with uncommitted changes

### Shell autocompletion
**Status:** Completed in v1.3.0

Generate bash/zsh completion scripts with symbol names from codenav:

```bash
# Generate bash completion
codenav completion bash > ~/.bash_completion.d/codenav

# Generate zsh completion
codenav completion zsh > ~/.zfunc/_codenav

# Source directly (bash)
eval "$(codenav completion bash)"
```

Features:
- Completes commands: map, search, read, stats, completion, watch, export
- Completes options for each command
- Completes symbol types (function, class, method, etc.)
- Auto-completes symbol names from .codenav.json in current directory

### Watch mode
**Status:** Completed in v1.3.0

Automatically update map when files change:

```bash
# Watch with default settings
codenav watch /path/to/project

# With options
codenav watch . -o .codenav.json --debounce 2.0 --git-only
```

Features:
- Polls for file changes (no external dependencies)
- Debounce to avoid rapid updates
- Uses incremental scan for efficiency
- Shows real-time update statistics
- Supports --git-only and --use-gitignore
- Graceful shutdown with Ctrl+C

### Export formats
**Status:** Completed in v1.3.0

Export code map to different formats:

```bash
# Export to Markdown
codenav export -f markdown -o docs/codebase.md

# Export to HTML (interactive)
codenav export -f html -o docs/codebase.html

# Export to GraphViz (dependency graph)
codenav export -f graphviz -o docs/deps.dot
dot -Tpng docs/deps.dot -o docs/deps.png
```

Formats:
- **Markdown**: Documentation with statistics, file listing, symbol index
- **HTML**: Interactive page with search, collapsible files, dark theme
- **GraphViz**: DOT format dependency graph with file clusters

---

## Planned Improvements

*All planned improvements have been implemented!*

---

## Language Support Improvements

| Language | Current | Potential Improvement |
|----------|---------|----------------------|
| Python | AST ✅ | Add type hint extraction |
| JavaScript | AST (tree-sitter) ✅ | - |
| TypeScript | AST (tree-sitter) ✅ | - |
| Go | Regex | Add go/ast parsing |
| Rust | Regex | Add syn crate parsing |

---

## Contributing

Want to implement one of these improvements? Check [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Priority should be given to:
1. Bug fixes
2. High priority improvements
3. Language support improvements
4. Medium/Low priority features
