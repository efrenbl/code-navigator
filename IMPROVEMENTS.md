# Future Improvements - Claude Code Navigator

This document tracks potential improvements and enhancements for the project.

---

## Completed

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

---

## Planned Improvements

### High Priority

#### 1. Incremental map updates
**Effort:** High | **Impact:** High

Instead of regenerating the entire map, update only modified files:

```bash
code-map . --incremental
```

Compare file hashes and only re-analyze changed files.

#### 2. Short command aliases
**Effort:** Medium | **Impact:** High

```bash
# Instead of:
code-search "UserService" --type class

# Allow:
codemap search "UserService" -t class
codemap read src/api.py 45-60
codemap stats
```

---

### Medium Priority

#### 4. AST support for JavaScript/TypeScript
**Effort:** High | **Impact:** Medium

Currently uses regex for JS/TS. Could use:
- `esprima` or `acorn` for JavaScript
- TypeScript compiler API for TypeScript

This would improve symbol detection accuracy.

#### 5. Automatic change detection
**Effort:** Medium | **Impact:** Medium

Warn when files have changed since map generation:

```bash
code-search "user" -m .codemap.json
# Warning: 3 files have changed since map was generated. Run code-map to update.
```

#### 6. Git integration
**Effort:** Medium | **Impact:** Medium

- Only map files tracked by git
- Ignore patterns from .gitignore automatically
- Option `--since-commit` to see changes since a commit

---

### Low Priority

#### 7. Shell autocompletion
**Effort:** Medium | **Impact:** Low

Generate bash/zsh completion scripts with symbol names from codemap.

#### 8. Watch mode
**Effort:** Medium | **Impact:** Low

```bash
code-map . --watch
```

Automatically update map when files change.

#### 9. Export formats
**Effort:** Low | **Impact:** Low

Export map in different formats:
- Markdown (for documentation)
- HTML (for browsing)
- GraphViz (for dependency visualization)

---

## Language Support Improvements

| Language | Current | Improvement |
|----------|---------|-------------|
| Python | AST | Add type hint extraction |
| JavaScript | Regex | Add esprima/acorn AST |
| TypeScript | Regex | Add TS compiler API |
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
