# Changelog

All notable changes to Claude Code Navigator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [1.3.0] - 2026-01-20

### Added
- **AST support for JavaScript/TypeScript** via tree-sitter (optional dependency)
  - Install with `pip install claude-code-navigator[ast]`
  - Detects functions, arrow functions, classes, methods, interfaces, types, enums
  - Automatic fallback to regex when tree-sitter not installed
  - New `js_ts_analyzer.py` module with `JavaScriptAnalyzer` and `TypeScriptAnalyzer`

- **Git integration**
  - `--git-only` flag: Only scan git-tracked files
  - `--use-gitignore` flag: Respect .gitignore patterns
  - `--since-commit` flag: Show symbols in files changed since a commit
  - New `GitIntegration` class with helper methods

- **Stale detection**
  - `--check-stale` flag: Check if code map is outdated
  - `--warn-stale` flag: Warn before showing results if files changed
  - `check_stale_files()` method in `CodeSearcher`

- **Watch mode** (`codemap watch`)
  - Auto-update code map when files change
  - Polling-based (no external dependencies)
  - Configurable debounce
  - New `watcher.py` module with `CodeMapWatcher`

- **Export formats** (`codemap export`)
  - Markdown: Documentation with statistics and symbol index
  - HTML: Interactive page with search and dark theme
  - GraphViz: DOT format dependency graph
  - New `exporters.py` module with `MarkdownExporter`, `HTMLExporter`, `GraphVizExporter`

- **Shell completions** (`codemap completion`)
  - Bash and Zsh completion scripts
  - Completes commands, options, and symbol names
  - New `completions.py` module

- **Unified CLI**: New `codemap` command with subcommands (`map`, `search`, `read`, `stats`, `watch`, `export`, `completion`)
- **Incremental map updates**: `--incremental` flag for `codemap map`
- New `cli.py` module providing unified entry point
- Comprehensive test suite (146 tests)

### Changed
- Refactored modules with reusable `add_*_arguments()` and `run_*()` functions
- Maps now include all analyzed files for accurate incremental tracking
- Updated skill file with new CLI documentation

### Backward Compatibility
- Legacy commands (`code-map`, `code-search`, `code-read`) still work
- Existing `.codemap.json` files are fully compatible
- JS/TS analysis falls back to regex if tree-sitter not installed

## [1.2.0] - 2026-01-19

### Added
- **Terminal colors**: Colored output for better readability in terminal
- New `colors.py` module with ANSI color support
- `--no-color` flag for all commands to disable colors
- New `-o table` format for `code-search` with colored, human-readable output
- Colored output for `code-read -o code` format
- Colored success/stats messages for `code-map`
- Respects `NO_COLOR` and `FORCE_COLOR` environment variables
- Auto-detection of terminal color support (TTY, Windows Terminal, etc.)

### Color Scheme
- Green: Found symbols, success messages
- Cyan: File paths, line numbers, info
- Magenta: Symbol types
- Yellow: Line ranges, warnings
- Dim: Context lines, less prominent text

## [1.1.0] - 2026-01-19

### Changed
- **Pretty output by default**: All commands now output pretty-printed JSON with indentation for better readability
- Replaced `--pretty` flag with `--compact` flag for minified JSON output
- Updated help text to reflect new default behavior

### Added
- `--compact` flag for all commands to output minified JSON when needed

## [1.0.1] - 2026-01-19

### Added
- New `list_by_type()` method in `CodeSearcher` to list all symbols of a specific type without requiring a search query
- CLI support: `code-search --type class` now works without a query
- Tests for `list_by_type()` functionality
- Claude Code CLI usage section in README

### Fixed
- `code-search --type <type>` no longer requires a query argument
- Test compatibility with Python 3.8 (tests no longer assume `ast.unparse` availability)
- Fixed test assertions for line number formatting in code output

## [1.0.0] - 2024-01-15

### Added

- **Code Mapper** (`code_mapper.py`)
  - Full AST analysis for Python files
  - Regex-based analysis for JavaScript, TypeScript, Java, Go, Rust, C/C++
  - Automatic detection of functions, classes, methods
  - Signature and docstring extraction
  - Dependency tracking (what calls what)
  - File hash tracking for change detection
  - Configurable ignore patterns
  - Pretty-print JSON option

- **Code Search** (`code_search.py`)
  - Symbol search with fuzzy matching
  - Filter by symbol type (function, class, method, etc.)
  - Filter by file path pattern
  - File structure visualization
  - Dependency analysis (find callers/callees)
  - Codebase statistics
  - Configurable result limits

- **Line Reader** (`line_reader.py`)
  - Read specific line ranges
  - Read multiple ranges in single call
  - Smart range merging
  - Context lines support
  - Symbol mode with smart truncation
  - Pattern search within files
  - JSON and code output formats

- **Package Features**
  - CLI commands: `code-map`, `code-search`, `code-read`
  - Zero external dependencies
  - Python 3.8+ support
  - Comprehensive test suite
  - Full documentation

### Performance

- Typical map generation: < 10 seconds for 1000+ file codebases
- Search queries: < 15ms even on large maps
- Memory efficient: streams large files

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 1.3.0 | 2026-01-20 | AST for JS/TS, git integration, watch, export, completions |
| 1.2.0 | 2026-01-19 | Terminal colors, `--no-color` flag, table format |
| 1.1.0 | 2026-01-19 | Pretty output by default, `--compact` flag |
| 1.0.1 | 2026-01-19 | Added `list_by_type()`, CLI improvements |
| 1.0.0 | 2024-01-15 | Initial release |

---

## Upgrade Guide

### Upgrading to 1.0.0

This is the initial release. No upgrade steps needed.

---

## Deprecation Notices

None at this time.

---

[Unreleased]: https://github.com/efrenbl/claude-code-navigator/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/efrenbl/claude-code-navigator/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/efrenbl/claude-code-navigator/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/efrenbl/claude-code-navigator/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/efrenbl/claude-code-navigator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/efrenbl/claude-code-navigator/releases/tag/v1.0.0
