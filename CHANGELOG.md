# Changelog

All notable changes to Code Navigator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

No unreleased changes.

## [1.4.1] - 2026-01-21

### Security
- **CRITICAL: Path Traversal Prevention** - Added security validation in `LineReader` to prevent reading files outside root directory
- **CRITICAL: Atomic File Writes** - Watch mode now writes code maps atomically using temp files to prevent corruption
- **CRITICAL: TOCTOU Race Conditions** - Fixed time-of-check to time-of-use vulnerabilities in watcher and incremental scan
- **HIGH: Thread Safety** - Added double-checked locking pattern to `get_colors()` singleton

### Fixed
- **Bare Except Clauses** - Replaced 6 bare `except:` blocks with specific exception types across completions.py, code_navigator.py, and watcher.py
- **Memory Leak** - Fixed `scan_incremental()` holding entire map in memory; now releases after extracting file data
- **Silent Data Truncation** - `GenericAnalyzer` now sets `truncated=True` flag when 500-line limit is hit
- **Input Validation** - Added comprehensive validation for line range parsing in CLI (negative numbers, invalid ranges, malformed input)
- **API Consistency** - `find_dependencies()` now returns `found: true/false` field for consistency with other methods

### Changed
- **DRY Refactor** - Extracted `compute_content_hash()` to `__init__.py` as single source of truth (was duplicated in 3 modules)
- Improved error messages for path traversal attempts with detailed security context

### Tests
- Added 6 new tests for path traversal prevention
- Updated test fixtures to use proper temp directories with root paths
- All 174 tests passing

## [1.4.0] - 2026-01-20

### Added
- **Aggressive Claude Code integration**: Enhanced skill description with explicit triggers
  - Skill now activates on common phrases: "where is", "find", "search", "how does X work"
  - Lowered threshold from 50+ to 20+ files for recommendations
  - Added trigger keywords for better automatic activation

### Changed
- Updated skill description in SKILL.md with clearer, more comprehensive triggers
- Skill file regenerated with v1.4.0 metadata

### Documentation
- Added recommended global CLAUDE.md configuration
- Added recommended hooks configuration for settings.json
- Documented best practices for integrating with Claude Code sessions

## [1.3.0] - 2026-01-20

### Added
- **AST support for JavaScript/TypeScript** via tree-sitter (optional dependency)
  - Install with `pip install code-navigator[ast]`
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

- **Watch mode** (`codenav watch`)
  - Auto-update code map when files change
  - Polling-based (no external dependencies)
  - Configurable debounce
  - New `watcher.py` module with `CodenavWatcher`

- **Export formats** (`codenav export`)
  - Markdown: Documentation with statistics and symbol index
  - HTML: Interactive page with search and dark theme
  - GraphViz: DOT format dependency graph
  - New `exporters.py` module with `MarkdownExporter`, `HTMLExporter`, `GraphVizExporter`

- **Shell completions** (`codenav completion`)
  - Bash and Zsh completion scripts
  - Completes commands, options, and symbol names
  - New `completions.py` module

- **Unified CLI**: New `codenav` command with subcommands (`map`, `search`, `read`, `stats`, `watch`, `export`, `completion`)
- **Incremental map updates**: `--incremental` flag for `codenav map`
- New `cli.py` module providing unified entry point
- Comprehensive test suite (146 tests)

### Changed
- Refactored modules with reusable `add_*_arguments()` and `run_*()` functions
- Maps now include all analyzed files for accurate incremental tracking
- Updated skill file with new CLI documentation

### Backward Compatibility
- Legacy commands (`code-map`, `code-search`, `code-read`) still work
- Existing `.codenav.json` files are fully compatible
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

- **Code Mapper** (`code_navigator.py`)
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
| 1.4.1 | 2026-01-21 | Security audit fixes: path traversal, TOCTOU, atomic writes |
| 1.4.0 | 2026-01-20 | Aggressive Claude Code integration |
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

[Unreleased]: https://github.com/efrenbl/code-navigator/compare/v1.4.1...HEAD
[1.4.1]: https://github.com/efrenbl/code-navigator/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/efrenbl/code-navigator/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/efrenbl/code-navigator/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/efrenbl/code-navigator/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/efrenbl/code-navigator/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/efrenbl/code-navigator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/efrenbl/code-navigator/releases/tag/v1.0.0
