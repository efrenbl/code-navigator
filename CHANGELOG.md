# Changelog

All notable changes to Claude Code Navigator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nothing yet

### Changed
- Nothing yet

### Fixed
- Nothing yet

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

[Unreleased]: https://github.com/efrenbl/claude-code-navigator/compare/v1.0.1...HEAD
[1.0.1]: https://github.com/efrenbl/claude-code-navigator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/efrenbl/claude-code-navigator/releases/tag/v1.0.0
