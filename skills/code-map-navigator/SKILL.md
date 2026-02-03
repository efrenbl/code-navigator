---
name: code-map-navigator
description: >
  Token-efficient code navigation for large codebases. Generates structural
  maps/graphs of code locally, enabling targeted symbol search and line-specific
  reading without loading entire files. Use when working with large projects,
  optimizing token usage, finding specific functions/classes, making targeted
  code changes, or when the user mentions token optimization, code mapping,
  or efficient navigation. Essential for projects with 50+ files or when
  context window efficiency matters.
license: MIT
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - Write
metadata:
  owner: efrenbl
  category: code-navigation
  version: "2.0.0"
---

# Code Map Navigator

Token-efficient code navigation skill that reduces context usage by up to 97% when exploring large codebases.

## Objective

Enable AI assistants to efficiently navigate and understand codebases without consuming excessive tokens by loading entire files. Instead, generate structural maps and read only the specific lines needed.

## When to Use This Skill

**ALWAYS activate when:**
- User needs to understand a codebase structure
- Looking for specific functions, classes, or symbols
- Finding the most important files (architectural hubs)
- Reading specific sections of code without loading entire files
- Analyzing dependencies between files
- User mentions "token optimization", "code mapping", or "efficient navigation"
- Working with projects containing 50+ files

## Workflow

### Step 1: Scan the Codebase
Start by generating a structural map:

```bash
python -m codenav.cli scan /path/to/project --git-only
```

Or via MCP tool `codenav_scan`:
```json
{"path": "/path/to/project", "git_only": true}
```

### Step 2: Identify Hub Files
Find the most important files (high connectivity):

```bash
python -m codenav.cli hubs /path/to/project --top 5
```

Or via MCP tool `codenav_get_hubs`:
```json
{"path": "/path/to/project", "top_n": 5}
```

### Step 3: Search for Symbols
Find specific functions, classes, or methods:

```bash
python -m codenav.cli search "process_payment" --type function
```

Or via MCP tool `codenav_search`:
```json
{"query": "process_payment", "symbol_type": "function"}
```

### Step 4: Read Specific Lines
Only load the lines you need:

```bash
python -m codenav.cli read src/api.py --start 45 --end 60
```

Or via MCP tool `codenav_read`:
```json
{"file_path": "src/api.py", "start_line": 45, "end_line": 60}
```

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `codenav_scan` | Scan codebase and generate structural map |
| `codenav_search` | Search for symbols by name or pattern |
| `codenav_read` | Read specific lines from a file |
| `codenav_get_hubs` | Find most important files |
| `codenav_get_dependencies` | Get import/export relationships |
| `codenav_get_structure` | Get all symbols in a file |

## Token Efficiency

| Traditional Approach | With Codenav | Savings |
|---------------------|--------------|---------|
| Read entire file (500 lines) | Read specific function (20 lines) | 96% |
| JSON with full metadata | Compact tree with inline meta | 75% |
| Raw file listing | Structural map with hubs | 80% |

## Usage of scripts/

Scripts in this skill provide CLI utilities:
- See `references/cli-usage.md` for detailed CLI documentation

## Usage of references/

Reference documents provide detailed information:
- `api-reference.md` - Full API documentation
- `mcp-integration.md` - MCP server setup guide
- `troubleshooting.md` - Common issues and solutions
- `advanced-usage.md` - Advanced features and workflows

## Examples

### Example 1: Understand a New Codebase
```
User: "I need to understand this React project"

1. codenav_scan {"path": ".", "git_only": true}
   → Returns structural map with 150 files organized by type

2. codenav_get_hubs {"path": ".", "top_n": 5}
   → Identifies: App.tsx, api/index.ts, store/index.ts, hooks/useAuth.ts, utils/helpers.ts

3. codenav_get_structure {"file_path": "src/App.tsx"}
   → Shows component structure without loading full file
```

### Example 2: Find and Fix a Bug
```
User: "Find where handleSubmit is defined"

1. codenav_search {"query": "handleSubmit", "symbol_type": "function"}
   → Found in: src/components/Form.tsx:45, src/hooks/useForm.ts:23

2. codenav_read {"file_path": "src/components/Form.tsx", "start_line": 40, "end_line": 60}
   → Reads only the relevant 20 lines
```

## Configuration

Add to Claude Code settings (`~/.claude/settings.json`):

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

## Best Practices

1. **Be specific with searches** - Use exact names when possible
2. **Use file patterns** - Filter searches to relevant directories
3. **Read in chunks** - Request only the lines you need
4. **Check hubs first** - They often contain the core logic
5. **Leverage structure** - Get file overview before diving into details
