# Changelog

All notable changes to Code Navigator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.0] - 2026-07-25

### Added
- **Ruby/Rails metaprogramming extraction.** A static parser that only sees
  `def` captures ~1 of 13 invocable methods on a typical ActiveRecord model —
  the associations, accessors, delegations and scopes are generated at load
  time by class-body macros. The Ruby analyzer now extracts them:
  `belongs_to`/`has_one`/`has_many`/`has_and_belongs_to_many` → the association
  method; `attr_accessor`/`reader`/`writer` → each attribute; `delegate` → each
  target (honoring `prefix: true`/`:sym`); `scope` → the scope; `define_method`
  with a symbol literal → the method. Each is parented to its class and tagged
  with a `modifiers` marker (`association:<kind>`, `attr`, `delegated`, `scope`,
  `dynamic`). Measured 1/13 → 12/13 invocable on a model; `validates` is
  intentionally not emitted; `method_missing` stays a plain def with its dynamic
  targets not invented.
- **`codenav_lookup` MCP tool.** Fuses locate + body + callers into one call:
  returns the top matches' source (clipped to a repo-size-scaled, monotonic
  per-symbol budget) plus, for each, the symbols that call it. Promoted as the
  primary lookup path in the server instructions to cut the
  search→structure→read round-trips.
- **Reverse caller index.** `CodeSearcher.find_callers(name)` answers "who calls
  X" — the reverse of the dependency edges, the relation a plain `grep` cannot
  resolve — built once from the map and cached.
- **A/B evaluation harness** (`scripts/agent-eval/`): `run-ab.sh` isolates arms
  by `--mcp-config` only; `parse-run.mjs` reads every metric from the
  stream-json trace; `TASKS.md` pre-registers tasks + rubrics; `setup-corpus.sh`
  clones and indexes the public corpora. Plus `docs/competitive-and-regimen.md`
  with measured per-language coverage and the usage régimen.

## [2.3.0] - 2026-07-25

### Added
- **Arquitectura LanguageSpec portada desde codegraph-nav** (`src/codenav/languages/`):
  specs declarativas por lenguaje consumidas por un único `TreeSitterExtractor`,
  con registry central de gramáticas (tree-sitter-language-pack → wheels
  individuales → fallback regex). Los analyzers de go/ruby/dart/rust/js-ts
  quedan como shims de compatibilidad (~30 líneas) sobre sus specs.
- **7 lenguajes nuevos de primera clase**: Java, Kotlin, Swift, C#, C, C++ y PHP
  pasan de regex/ast-grep a extracción AST con tree-sitter (símbolos con parent,
  doc comments, deps e imports). Java/C/C++/PHP conservan ast-grep (`[fast]`)
  como fallback intermedio antes del regex. `LANGUAGE_EXTENSIONS` añade
  `.kt/.kts`, `.swift` y `.cs`.
- **Enrichment de símbolos**: campos nuevos `visibility` (Go exportado/no,
  modificadores Ruby, `_` de Dart), `modifiers` (`static`, `async`, `abstract`,
  `factory`, `getter`, `setter`…), `mixins` (include/extend/prepend de Ruby) y
  `return_type` normalizado. Se emiten en el mapa solo cuando tienen valor y
  hacen round-trip en scans incrementales.
- **Imports por archivo**: cada analyzer captura sus especificadores de import
  y `generate_map` los resuelve (ImportResolver con aliases de
  tsconfig/pyproject) a rutas internas del repo bajo la clave `imports` de cada
  archivo. Doc comments para Go/Ruby/Dart (antes ausentes) vía
  `collect_doc_comment`.
- **`Symbol.source`**: procedencia del engine por símbolo
  (`"ast" | "ast-grep" | "regex"`); los mapas antiguos sin la clave siguen
  cargando.
- **Parity del analyzer Python**: subclases de Enum tipadas como `enum`,
  constantes UPPER_CASE a nivel de módulo, funciones anidadas con parent de su
  función contenedora y deps deterministas (ordenadas, sin fugas de defs
  anidados).

### Changed
- **`[ast]` ahora instala `tree-sitter-language-pack`** (160+ gramáticas
  precompiladas, una sola dependencia) en lugar de wheels individuales; el
  registry sigue resolviendo los wheels `tree-sitter-<lang>` antiguos.
  `[dart]` queda como alias deprecado de `[ast]`.

### Fixed
- **Constructores Dart**: los constructores con nombre (`Foo._internal`) se
  emiten como `constructor` con el nombre del ctor (`_internal`), los factory
  llevan `modifiers=["factory"]` y getters/setters se distinguen con
  `modifiers=["getter"|"setter"]` (el adaptador `_Node` fue eliminado).
- **Receivers genéricos de Go**: `func (s *Stack[T]) Push(...)` vincula el
  método a su tipo (`parent="Stack"`); los métodos de interfaces Go se extraen
  con parent de la interfaz.

## [2.2.9] - 2026-07-25

### Fixed
- **Gitignore matching is now real gitignore semantics, not a substring test.**
  `should_ignore` matched each pattern as a raw substring against the full path,
  so a `.gitignore` containing `main` silently dropped every path that merely
  *contained* the word — `internal/domain/entity/` (via "do**main**") and
  `cmd/api/main.go` — while `git check-ignore` reported none of them ignored.
  Whole subtrees vanished from the index with `errors: 0` and coverage looking
  healthy. New self-contained `gitignore.py` (zero dependencies) implements
  path-component matching, `/` anchoring, `dir/`, `**`, negation (including the
  "cannot re-include under an excluded parent" rule), nested `.gitignore`
  precedence, `.git/info/exclude` and `core.excludesFile`, validated in tests
  against `git check-ignore` as the oracle.

### Added
- **Coverage invariant.** After a scan, each detected language's source files
  are compared against files that produced symbols. A language with real code
  but zero symbols anywhere means its analyzer silently broke — now a hard error
  (`exit 2`), not a statistic. The map always carries a `per_language`
  breakdown.
- **Distinguishable skip causes.** `files_skipped` is split into
  `skipped_gitignore` / `skipped_symlink` / `skipped_not_tracked`, shown in the
  coverage summary, so `errors: 0` can no longer coexist with a fifth of the
  code quietly missing.
- **Runtime self-disclosure (MCP).** `codenav_search` (no matches) and
  `codenav_get_structure` (file not found) now report whether the index is
  partial, and `codenav_get_structure` distinguishes "exists on disk but not
  indexed" from "does not exist" — so the agent can tell "not in the code" from
  "not in the index".

### Changed
- **Index format version bumped `1.0` → `2`.** `scan_incremental` discards a
  map with a mismatched version and performs a full rebuild, so the gitignore
  fix's changed membership cannot be masked by a carried-over pre-2.2.9 index.
  Existing `.codenav.json` files are invalidated automatically on the next
  `codenav map --incremental`.
- **`--use-gitignore` now honors `.gitignore` even outside a git repository**
  (it is a plain file and the matcher is self-contained). `.git/info/exclude`
  and `core.excludesFile` still require git.

## [2.2.8] - 2026-07-23

### Security
- **Refresh de SHAs pineados en GitHub Actions** (`ci.yml`, `release.yml`).
  Los tags `actions/checkout@v5` y `actions/setup-python@v6` habían sido
  actualizados upstream desde el último pinning; se actualizan a sus commits
  actuales para evitar correr el código antiguo de las actions. `codecov@v5`
  y `upload-artifact@v4` se verificaron como correctos.

## [2.2.7] - 2026-07-22

### Security
- **Guard ReDoS centralizado** (`src/codenav/regex_safety.py`). Todos los
  `re.compile` de patrones de usuario pasan ahora por un único `safe_compile`;
  se cerró el path sin protección en `line_reader.search_in_file` (grep vía CLI
  `codenav read --search`) y se reforzó el heurístico de nested quantifiers
  (ahora también detecta las formas `(a+b)+` y `{n,}`). Cobertura nueva en
  `tests/test_regex_safety.py` (+18 casos).
- **Triage Snyk SCA**: los hallazgos estaban stale (bleach/pygments/idna/urllib3/
  cryptography/zipp ya parchados en `uv.lock`). Se consolidó el `dev-requirements.txt`
  legacy para que derive del extra de instalación `.[dev]` (una sola fuente de
  verdad para las dependencias de desarrollo).

### Removed
- **Se eliminó `twine`** de las dependencias de desarrollo y de los flujos de CI/
  Makefile. Codenav es git-only (no publica a PyPI), así que `twine check`/`twine
  upload` no aportaban nada; quitarlo poda 22 paquetes transitivos (twine, urllib3,
  nh3, readme-renderer, keyring, requests, secretstorage, rich…) del árbol de
  dependencias. El job `build` de CI sigue validando el empaquetado con `python -m build`.

## [2.2.6] - 2026-07-21

### Security
- **Bump `mcp>=1.28.1`** en los extras `[mcp]`/`[dev]`/`[all]` para descartar
  CVE-2026-59950 (el transporte WebSocket del MCP Python SDK no validaba
  Host/Origin). Codenav corre FastMCP sobre stdio, así que la exposición real era
  baja, pero se sube el floor para que ningún consumidor resuelva una versión
  vulnerable.
- **Bump de dependencias transitivas del lock** vía `uv lock --upgrade`
  (`starlette` 0.52.1→1.3.1, `urllib3` 2.6.3→2.7.0, `cryptography` 46.0.3→49.0.0,
  entre otras) para descartar advisories conocidos en el árbol bloqueado.
- **Escaneo de vulnerabilidades en CI**: nuevo job `security-audit` que exporta el
  árbol bloqueado (`uv export --frozen --all-extras`) y corre `pip-audit` sobre él;
  el CI falla si una dependencia tiene un advisory conocido. Auditar el lock (en vez
  del entorno instalado) lo hace determinista y evita falsos positivos del tooling
  base del runner.

### Changed
- **Versión en una sola fuente de verdad** (`src/codenav/_version.py`). Se eliminaron
  los `__version__` hardcodeados y desincronizados de los módulos; `__init__`, los CLIs
  y la metadata del paquete (`pyproject` dinámico) derivan todos de ahí. Subir versión
  ahora solo toca `_version.py`.

### Added
- **Publicación automática de GitHub Release** al pushear un tag `v*`
  (`.github/workflows/release.yml`, solo GitHub Release, sin PyPI) para mantener la
  página de Releases y el badge de versión en sync con los tags.

## [2.2.5] - 2026-07-12

### Changed
- **Nombre de distribución revertido a `codenav`.** El rename a `codemap-nav`
  (2.2.3/2.2.4) fue un error: rompía `pip install --upgrade` para clientes MCP en
  2.2.1 (pip veía una distribución nueva aportando los mismos archivos `codenav/` en
  vez de actualizar la instalación existente). El proyecto se consume solo desde el
  repositorio git; se abandona la publicación en PyPI por ahora. El paquete importable
  (`import codenav`), los comandos CLI (`codenav`, `cnv`, `codenav-mcp`) y las mejoras
  2.2.1–2.2.4 se conservan tal cual.

### Removed
- Workflow de PyPI Trusted Publishing (`.github/workflows/release.yml`).

## [2.2.4] - 2026-07-06

### Changed

- **PyPI distribution named `codemap-nav`** — supersedes the unpublished
  2.2.3: the `code-navigator` name was rejected by PyPI's ultra-normalized
  similarity check (it collapses to `codenavigator`, an existing package).

## [2.2.3] - 2026-07-05 (unpublished — PyPI name blocked)

### Changed

- **PyPI distribution renamed** (first attempt, as `code-navigator`) — the
  `codenav` name on PyPI belongs to an unrelated project, so earlier
  "releases" existed only as GitHub Releases. The import package
  (`import codenav`) and CLI commands (`codenav`, `cnv`, `codenav-mcp`) are
  unchanged.

### Added

- Tag-triggered release workflow (`release.yml`) publishing to PyPI/TestPyPI
  via OIDC Trusted Publishing, ported from codegraph-nav: quality gate on the
  tagged commit, tag↔version check, hyphenated tags rehearse on TestPyPI.

## [2.2.2] - 2026-07-04

### Fixed
- **UTF-8 byte-offset corruption in the Ruby analyzer** — the 2.2.1 fix
  covered JavaScript, TypeScript, Go, Rust and Dart but missed Ruby, which
  still sliced the source string with tree-sitter byte offsets. Multi-byte
  characters (emoji, accents) earlier in a `.rb` file corrupted every later
  symbol name and signature. Ruby now slices `source_bytes` like the rest.

### Added
- Regression suite `tests/test_symbol_uniqueness.py` (shared with
  codegraph-nav): parametrized over all seven analyzers, asserts no analyzer
  emits duplicate symbols and extraction survives multi-byte characters.

## [2.2.1] - 2026-06-21

### Fixed
- **UTF-8 byte-offset corruption in tree-sitter analyzers** — JavaScript,
  TypeScript, Go, Rust and Dart sliced source text with tree-sitter's byte
  offsets against the source *string*, so any multi-byte character (emoji,
  accents — common in comments, string literals, i18n) earlier in a file
  misaligned every later slice and corrupted symbol names, parents and
  dependencies. Analyzers now slice an encoded `source_bytes` view and decode.
  The ast-grep and regex paths were never affected. (Found by running
  `codenav map` on a real Rust repository.)

## [2.2.0] - 2026-06-21

### Added
- **Mapping coverage metrics** — `scan` and `scan_incremental` now report
  `files_skipped`, `files_unmapped`, `unmapped_extensions` (per-extension
  breakdown), `symbols_truncated` and `coverage_pct`. Existing stats keys are
  unchanged, so `.codenav.json` stays backward compatible. `codenav map` prints
  a one-line summary, e.g. `mapped 636 · unmapped 12 (.kt:8 .sh:4) · skipped
  1204 · coverage 98.2%`. Makes missing languages and over-broad ignore
  patterns observable.
- **ast-grep wiring for Java / C / C++ / PHP** — the languages without a
  dedicated grammar are upgraded from regex to a real AST parse, with
  method→class parent linkage, when the optional `codenav[fast]` extra
  (`ast-grep-py`) is installed. Without it they use the regex fallback exactly
  as before (core stays zero-dependency).
- **Call / dependency extraction in the tree-sitter analyzers** — JavaScript,
  TypeScript, Go, Rust and Dart now populate `Symbol.dependencies` with the
  names each function/method calls (previously Python-only), enriching
  `CodeSearcher.find_dependencies`. New shared `call_extraction` module.
- **Configurable symbol-scan cap** — `--max-symbol-lines` (CLI) /
  `max_symbol_lines` (`CodeNavigator`, default 500) so large functions need not
  be truncated by the regex analyzer.

### Changed
- README: dynamic version badge (tracks the latest GitHub release) and a new
  "Mapping coverage" section; corrected a stale note that claimed the retired
  `code-map`/`code-search`/`code-read` commands still work.

### CI
- New `astgrep` and `ast-langs` jobs exercise the ast-grep and tree-sitter AST
  paths (including call extraction) across Linux/macOS/Windows; the default
  matrix continues to cover the regex-fallback path.

## [2.1.0] - 2026-06-21

### Added
- **Dart/Flutter support** — new `DartAnalyzer` with optional tree-sitter AST
  analysis plus a regex fallback that works out-of-the-box. Recognizes
  classes, mixins, enums, extensions, methods (with parent), constructors,
  and top-level functions.
- **Flutter build artifact filtering** — `.dart_tool/`, `.flutter-plugins*`,
  `*.g.dart`, `*.freezed.dart`, `*.gr.dart` added to `DEFAULT_IGNORE_PATTERNS`.
- **Pre-compiled Dart grammar** — the Dart tree-sitter grammar now ships via
  `tree-sitter-dart` behind a dedicated `codenav[dart]` extra, providing wheels
  for Linux/macOS/Windows. No C compiler or manual build step is required to
  enable AST-level Dart analysis. It loads through the standard tree-sitter
  interface like every other language (no adapter), and Flutter is covered by
  the same grammar (Flutter widgets are ordinary Dart classes).
- New symbol types exposed by the Dart analyzer: `mixin`, `extension`,
  `constructor`. Existing consumers that filter on a closed set of types
  may want to update their filters.

### Fixed
- **TypeScript class detection** — classes were silently dropped because the
  TypeScript grammar names them with a `type_identifier` node (not
  `identifier`); `abstract class` declarations were not handled at all
  (`abstract_class_declaration` node). Both are now detected.
- **Duplicate class methods** — JS/TS methods were emitted twice (the class
  extractor walked the class body *and* the generic node recursion re-visited
  it). Methods are now extracted once, with the correct parent.
- **PageRank crash without SciPy** — `networkx.pagerank` requires the optional
  SciPy/NumPy backend; the `graph` extra now declares them, and
  `_compute_pagerank` degrades to uniform scores instead of raising when they
  are absent.

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
  - Install with `pip install "codenav[ast]"`
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
- The legacy `code-map` / `code-search` / `code-read` entry points have been
  retired (use `codenav map` / `codenav search` / `codenav read`); they are
  commented out in `pyproject.toml` and will be removed entirely in v3.0.0
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
| 2.2.1 | 2026-06-21 | Fix UTF-8 byte-offset corruption of names/deps in tree-sitter analyzers |
| 2.2.0 | 2026-06-21 | Coverage metrics; ast-grep wiring (Java/C/C++/PHP); calls/deps for AST langs |
| 2.1.0 | 2026-06-21 | Dart/Flutter AST via tree-sitter-dart; TS class/dedup & PageRank fixes |
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

[Unreleased]: https://github.com/efrenbl/code-navigator/compare/v2.2.7...HEAD
[2.2.7]: https://github.com/efrenbl/code-navigator/compare/v2.2.6...v2.2.7
[2.2.1]: https://github.com/efrenbl/code-navigator/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/efrenbl/code-navigator/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/efrenbl/code-navigator/compare/v1.4.1...v2.1.0
[1.4.1]: https://github.com/efrenbl/code-navigator/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/efrenbl/code-navigator/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/efrenbl/code-navigator/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/efrenbl/code-navigator/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/efrenbl/code-navigator/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/efrenbl/code-navigator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/efrenbl/code-navigator/releases/tag/v1.0.0
