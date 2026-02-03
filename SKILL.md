# Codenav - Token-Efficient Code Navigation Skill

## Overview

Codenav provides token-efficient code navigation capabilities for AI assistants, reducing token usage by up to 97% when exploring large codebases.

## When to Use This Skill

**ALWAYS use Codenav tools when:**
- You need to understand a codebase structure
- You're looking for specific functions, classes, or symbols
- You want to find the most important files (architectural hubs)
- You need to read specific sections of code without loading entire files
- You're analyzing dependencies between files

**Benefits:**
- Scans entire codebases in seconds
- Returns compact, token-optimized responses
- Identifies architectural patterns automatically
- Supports Python, JavaScript, TypeScript, Go, Rust, and more

## Available Tools

### 1. `codenav_scan`
Scan a codebase and generate a structural map.

```
Arguments:
  path: string (required) - Root directory to scan
  ignore_patterns: array - Patterns to ignore
  git_only: boolean - Only scan git-tracked files
  max_depth: integer - Maximum tree depth to display
```

**Example:**
```json
{"path": "/my/project", "git_only": true}
```

### 2. `codenav_search`
Search for symbols by name or pattern.

```
Arguments:
  query: string (required) - Search query
  symbol_type: "function" | "class" | "method" | "any"
  file_pattern: string - Filter by file glob
  limit: integer - Max results (default: 20)
```

**Example:**
```json
{"query": "process_payment", "symbol_type": "function"}
```

### 3. `codenav_read`
Read specific lines from a file.

```
Arguments:
  file_path: string (required) - Path to file
  start_line: integer (required) - First line (1-indexed)
  end_line: integer (required) - Last line
  context: integer - Extra lines before/after
```

**Example:**
```json
{"file_path": "src/api.py", "start_line": 45, "end_line": 60}
```

### 4. `codenav_get_hubs`
Find the most important files in a codebase.

```
Arguments:
  path: string (required) - Root directory
  top_n: integer - Number of hubs to return
  min_imports: integer - Minimum import threshold
```

**Example:**
```json
{"path": "/my/project", "top_n": 5}
```

### 5. `codenav_get_dependencies`
Get import/export relationships.

```
Arguments:
  path: string (required) - Root directory
  file: string - Specific file to analyze
  direction: "imports" | "imported_by" | "both"
  depth: integer - Traversal depth
```

### 6. `codenav_get_structure`
Get all symbols in a specific file.

```
Arguments:
  file_path: string (required) - Path to file
  include_private: boolean - Include _private symbols
```

## Recommended Workflow

1. **Start with `codenav_scan`** to understand the overall structure
2. **Use `codenav_get_hubs`** to identify critical files
3. **Search with `codenav_search`** when looking for specific functionality
4. **Read with `codenav_read`** only the lines you need

## Token Efficiency

Codenav responses are pre-formatted for minimal token usage:

| Traditional | With Codenav | Savings |
|-------------|--------------|---------|
| Read entire file (500 lines) | Read specific function (20 lines) | 96% |
| JSON with full metadata | Compact tree with inline meta | 75% |
| Raw file listing | Structural map with hubs | 80% |

## Configuration

Add to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "codenav": {
      "command": "python",
      "args": ["-m", "codenav.mcp"],
      "env": {
        "CODENAV_WORKSPACE": "/path/to/project"
      }
    }
  }
}
```

Or install globally:

```bash
pip install codenav
```

## Resources

The skill also exposes MCP Resources:

- `codenav://code-map` - Full structural map (JSON)
- `codenav://dependencies` - Dependency graph (JSON)

## Tips for Best Results

1. **Be specific with searches** - Use exact names when possible
2. **Use file patterns** - Filter searches to relevant directories
3. **Read in chunks** - Request only the lines you need
4. **Check hubs first** - They often contain the core logic
5. **Leverage structure** - Get file overview before diving into details
