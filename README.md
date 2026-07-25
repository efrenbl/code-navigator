<p align="center">
  <img src="https://img.shields.io/badge/MCP-1.0+-blue.svg" alt="MCP 1.0+">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/github/v/release/efrenbl/code-navigator?label=version&color=orange" alt="Latest release">
</p>

<h1 align="center">🧭 Code Navigator</h1>

<p align="center">
  <strong>An MCP server for token-efficient code navigation</strong>
</p>

<p align="center">
  <em>Reduce token usage by 97% when exploring large codebases with Claude</em>
</p>

---

## What is Code Navigator?

Code Navigator is a **Model Context Protocol (MCP) server** that helps AI assistants like Claude explore codebases efficiently. Instead of reading entire files, it provides:

- **Instant symbol search** - Find functions, classes, methods by name
- **Surgical reads** - Load only the exact lines you need
- **Dependency awareness** - See what calls what without reading everything

```
┌─────────────────────────────────────────────────────────────┐
│                    WITHOUT CODE NAVIGATOR                   │
├─────────────────────────────────────────────────────────────┤
│  User: "Fix the payment bug"                                │
│                                                             │
│  Claude reads:                                              │
│  • payments.py      (500 lines)  → 7,500 tokens             │
│  • billing.py       (300 lines)  → 4,500 tokens             │
│  • models/order.py  (200 lines)  → 3,000 tokens             │
│  ─────────────────────────────────────────────              │
│  Total:                            15,000 tokens            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     WITH CODE NAVIGATOR                     │
├─────────────────────────────────────────────────────────────┤
│  User: "Fix the payment bug"                                │
│                                                             │
│  1. codenav_search("payment") → payments.py:45-89           │
│     Cost: ~100 tokens                                       │
│                                                             │
│  2. codenav_read(payments.py, 45, 89)                       │
│     Cost: ~400 tokens                                       │
│  ─────────────────────────────────────────────              │
│  Total:                               500 tokens            │
│                                                             │
│  SAVINGS: 97% fewer tokens!                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install

```bash
pip install "codenav @ git+https://github.com/efrenbl/code-navigator.git"
```

> Codenav is **not published on PyPI** — install it directly from the git
> repository. The import package and CLI commands are `codenav` / `cnv`.
> Add extras with `pip install "codenav[mcp] @ git+https://github.com/efrenbl/code-navigator.git"`.

### 2. Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codenav": {
      "command": "codenav-mcp"
    }
  }
}
```

### 3. Configure Claude Code (CLI)

Add to `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "codenav": {
      "command": "codenav-mcp"
    }
  }
}
```

### 4. Configure Claude Code (VS Code)

Add to your VS Code `settings.json`:

```json
{
  "claude.mcpServers": {
    "codenav": {
      "command": "codenav-mcp"
    }
  }
}
```

### 5. Verify Installation

```bash
# Check the entry point is available
codenav-mcp --help

# Test with MCP Inspector (optional)
npx @anthropic/mcp-inspector codenav-mcp
```

### 6. Use It

In Claude, just ask to explore your codebase:

```
"Scan this project and find the payment function"
"Show me the architecture of this codebase"
"What files import the UserService class?"
```

Claude will automatically use the Code Navigator tools to explore efficiently.

---

## Available Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `codenav_scan` | Index codebase | First step for any new project |
| `codenav_search` | Find symbols | Looking for specific function/class |
| `codenav_read` | Read lines | After finding symbol location |
| `codenav_stats` | Codebase overview | Understanding project size |
| `codenav_get_hubs` | Find central files | Architecture analysis |
| `codenav_get_structure` | File outline | Before reading a file |
| `codenav_get_dependencies` | Import graph | Understanding coupling |

---

## How It Works

```mermaid
flowchart TB
    subgraph SCAN["Step 1: Scan (one-time)"]
        A[(Codebase)] --> B[codenav_scan]
        B --> C[.codenav.json index]
    end

    subgraph USE["Step 2: Use"]
        D[codenav_search] --> E[file:line locations]
        E --> F[codenav_read]
        F --> G[Only needed code]
    end

    C --> D
```

1. **Scan once** - Creates `.codenav.json` with all symbols indexed
2. **Search by name** - Find functions/classes/methods instantly
3. **Read surgically** - Load only the lines you need

---

## CLI Usage (Secondary)

While the primary use case is via MCP, you can also use the CLI directly:

```bash
# Generate code map (scan is an alias for map)
codenav scan .
codenav map .

# Search for symbols
codenav search "process_payment"

# Search by type
codenav search -t class -o table

# Search for files
codenav search --files "models" -o table

# Read specific lines
codenav read src/payments.py 45-89

# Read with context lines
codenav read src/payments.py 45-89 -c 3

# Get file structure
codenav search --structure src/payments.py

# Get symbol dependencies
codenav search --deps process_payment

# Get codebase stats
codenav stats

# Check if map needs updating
codenav search --check-stale

# Incremental update (only changed files)
codenav scan --incremental .

# Export as markdown
codenav export -f markdown -o docs/codebase.md
```

---

## Configuration

### Alternative: Using uv or pipx

```bash
# Using uv
uv pip install "codenav @ git+https://github.com/efrenbl/code-navigator.git"

# Using pipx (isolated environment)
pipx install "git+https://github.com/efrenbl/code-navigator.git"
```

### Claude Desktop with explicit Python path

If you have multiple Python installations:

```json
{
  "mcpServers": {
    "codenav": {
      "command": "python",
      "args": ["-m", "codenav.mcp"]
    }
  }
}
```

### With workspace directory

```json
{
  "mcpServers": {
    "codenav": {
      "command": "codenav-mcp",
      "args": ["--workspace", "/path/to/your/project"]
    }
  }
}
```

---

## Supported Languages

| Language | Analysis Type | Symbols | Parents | Doc comments | Calls (deps) | Imports | Quality |
|----------|---------------|:------:|:-------:|:------------:|:------------:|:-------:|---------|
| Python | Full AST (stdlib) | ✅ (+enums, constants, nested fns) | ✅ | ✅ docstrings | ✅ | ✅ resolved | ⭐⭐⭐⭐⭐ |
| JavaScript | AST (tree-sitter)* | ✅ | ✅ | — | ✅ | ✅ resolved | ⭐⭐⭐⭐⭐ |
| TypeScript | AST (tree-sitter)* | ✅ (+interfaces, enums, types) | ✅ | — | ✅ | ✅ resolved | ⭐⭐⭐⭐⭐ |
| Ruby | AST (tree-sitter)* | ✅ | ✅ | ✅ `#` | ✅ | ✅ `require` | ⭐⭐⭐⭐⭐ |
| Go | AST (tree-sitter)* | ✅ (+structs, interfaces) | ✅ | ✅ `//` | ✅ | ✅ resolved | ⭐⭐⭐⭐⭐ |
| Rust | AST (tree-sitter)* | ✅ (+structs, traits, enums) | ✅ | ✅ `///` | ✅ (+macros) | ✅ `use` | ⭐⭐⭐⭐⭐ |
| Dart / Flutter | AST (tree-sitter)* | ✅ (+mixins, extensions) | ✅ | ✅ `///` | ✅ | ✅ resolved | ⭐⭐⭐⭐⭐ |
| Java | AST (tree-sitter)*† | ✅ (+records, annotations) | ✅ | ✅ Javadoc | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| Kotlin | AST (tree-sitter)* | ✅ (+objects, data classes) | ✅ | ✅ KDoc | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| Swift | AST (tree-sitter)* | ✅ (+protocols, extensions) | ✅ | ✅ `///` | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| C# | AST (tree-sitter)* | ✅ (+records, delegates) | ✅ | ✅ `///` | ✅ | ✅ `using` | ⭐⭐⭐⭐⭐ |
| C | AST (tree-sitter)*† | ✅ (+prototypes, typedefs) | — | ✅ | ✅ | ✅ includes | ⭐⭐⭐⭐⭐ |
| C++ | AST (tree-sitter)*† | ✅ (+out-of-line members) | ✅ | ✅ | ✅ | ✅ includes | ⭐⭐⭐⭐⭐ |
| PHP | AST (tree-sitter)*† | ✅ (+traits, enums) | ✅ | ✅ docblocks | ✅ | ✅ `use`/require | ⭐⭐⭐⭐⭐ |

*Install tree-sitter support: `pip install "codenav[ast] @ git+https://github.com/efrenbl/code-navigator.git"`
All tree-sitter analyzers fall back to regex when tree-sitter is not installed.

†Java/C/C++/PHP keep [ast-grep](https://ast-grep.github.io/) as an intermediate
fallback: with the `[fast]` extra installed but no tree-sitter grammar, they
get a real AST parse (symbols + parents) before degrading to regex.

Every tree-sitter language extracts symbols with parent context, cross-file
call dependencies (`deps`), and import specifiers resolved to internal repo
files (the per-file `imports` key in the map). All except JS/TS also capture
leading doc comments. Each symbol records which engine produced it
(`"source": "ast" | "ast-grep" | "regex"`).

**AST grammars ship through `tree-sitter-language-pack`** (installed by the
`[ast]` extra): one dependency with 160+ pre-compiled grammars for
Linux/macOS/Windows — no C compiler needed. Installations that predate the
pack keep working: the grammar registry also resolves the old individual
`tree-sitter-<lang>` wheels. `[dart]` remains as a deprecated alias of
`[ast]`. Without any grammar installed, every language falls back to the
regex analyzer. Flutter needs no separate grammar; widgets are ordinary
Dart classes.

### Mapping coverage

`codenav map` reports how much of a tree it actually mapped. The scan stats
include `files_processed`, `files_unmapped` (with a per-extension breakdown in
`unmapped_extensions`), `files_skipped` (ignored), `symbols_truncated` and a
`coverage_pct`. The CLI prints a one-line summary, e.g.:

```
Coverage: mapped 636 · unmapped 12 (.kt:8 .sh:4) · skipped 1204 · coverage 98.2%
```

Use it to spot languages you're missing (a big `.cs`/`.kt` bucket) or an ignore
pattern that's eating real source. The per-symbol cap for the regex analyzer is
configurable with `--max-symbol-lines` (default 500) when large functions are
being truncated.

### Dart/Flutter setup

Dart files are analyzed via regex out-of-the-box (classes, mixins, enums,
extensions, top-level functions). To enable AST-level analysis (parented
methods, constructors, accurate signatures), install the tree-sitter extra:

```bash
pip install "codenav[ast] @ git+https://github.com/efrenbl/code-navigator.git"
```

The Dart grammar ships pre-compiled inside `tree-sitter-language-pack` — no C
compiler or manual build step required — and loads through the standard
tree-sitter interface, exactly like the other languages. Flutter needs no
separate grammar: Flutter widgets are ordinary Dart classes. `[dart]` is kept
as a deprecated alias of `[ast]`; if no grammar is installed, codenav
transparently falls back to the regex analyzer.

---

## Performance

Tested on real-world open source projects:

| Project | Files | Symbols | Map Size | Map Time |
|---------|-------|---------|----------|----------|
| Flask | 142 | 1,847 | 89 KB | 0.8s |
| Django | 2,156 | 28,493 | 1.2 MB | 8.2s |
| requests | 47 | 412 | 23 KB | 0.3s |

**Token savings:**
- Small projects (50-100 files): 85-90% reduction
- Medium projects (100-500 files): 92-96% reduction
- Large projects (500+ files): 97-99% reduction

---

## Requirements

- Python 3.10+
- MCP SDK 1.0+

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Stop burning tokens reading entire files.</strong><br>
  <em>Scan once, search instantly, read surgically.</em>
</p>
