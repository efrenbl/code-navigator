# Codenav MCP Integration Guide

## Overview

Codenav can run as an MCP (Model Context Protocol) server, exposing its code navigation capabilities to AI assistants like Claude. This enables seamless integration with Claude Code, Claude Desktop, and other MCP-compatible tools.

## Quick Start

### 1. Install Codenav with MCP Support

```bash
# Install with MCP dependencies
pip install codenav[mcp]

# Or install from source
pip install -e ".[mcp]"
```

### 2. Configure Claude Code

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "codenav": {
      "command": "python",
      "args": ["-m", "codenav.mcp"],
      "env": {}
    }
  }
}
```

### 3. Start Using

Once configured, Claude will automatically have access to Codenav tools:

```
You: "Scan this project and show me the structure"
Claude: [Uses codenav_scan tool]

You: "Find all authentication-related functions"
Claude: [Uses codenav_search with query="auth"]

You: "What are the most important files?"
Claude: [Uses codenav_get_hubs]
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code / Desktop                   │
├─────────────────────────────────────────────────────────────┤
│                         MCP Protocol                         │
│                    (JSON-RPC over stdio)                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  Codenav MCP Server                  │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │                                                      │   │
│  │  TOOLS                       RESOURCES               │   │
│  │  ───────────────────        ────────────────        │   │
│  │  • codenav_scan             • codenav://code-map    │   │
│  │  • codenav_search           • codenav://deps        │   │
│  │  • codenav_read                                      │   │
│  │  • codenav_get_hubs         PROMPTS                 │   │
│  │  • codenav_get_dependencies ────────────────        │   │
│  │  • codenav_get_structure    • analyze-architecture  │   │
│  │                             • find-entry-points     │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Codenav Core                      │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │  CodeNavigator │ CodeSearcher │ LineReader │ ...    │   │
│  └─────────────────────────────────────────────────────┘   │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                      Codebase                        │   │
│  │             (Python, JS, TS, Go, Rust...)            │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Tool Reference

### codenav_scan

Scan a codebase and generate a structural map.

**Input:**
```json
{
  "path": "/path/to/project",
  "ignore_patterns": ["*.test.py", "node_modules/"],
  "git_only": true,
  "max_depth": 3
}
```

**Output:**
```
# Code Map: my-project
Files: 127 | Symbols: 1,432

my-project/
├── src/
│   ├── api/
│   │   ├── client.py [C:APIClient M:get,post,delete] (Hub:8←)
│   │   └── auth.py [C:Auth F:login,logout] (Hub:12←)
│   └── models/
│       └── user.py [C:User,Profile M:save,load]
├── tests/
└── README.md
```

### codenav_search

Search for symbols by name or pattern.

**Input:**
```json
{
  "query": "process_payment",
  "symbol_type": "function",
  "file_pattern": "src/**/*.py",
  "limit": 10
}
```

**Output:**
```
# Search Results (3 matches)

- `src/payments/processor.py:45` [fn] **process_payment**
- `src/payments/stripe.py:120` [fn] **process_payment_stripe**
- `src/payments/paypal.py:89` [fn] **process_payment_paypal**
```

### codenav_read

Read specific lines from a file.

**Input:**
```json
{
  "file_path": "src/api/auth.py",
  "start_line": 45,
  "end_line": 60,
  "context": 2
}
```

**Output:**
```python
43: # Context lines before
44:
45: def authenticate(username: str, password: str) -> User:
46:     """Authenticate a user and return a User object."""
47:     user = User.find_by_username(username)
48:     if user and user.verify_password(password):
49:         return user
50:     raise AuthenticationError("Invalid credentials")
...
62: # Context lines after
```

### codenav_get_hubs

Identify architectural hub files.

**Input:**
```json
{
  "path": "/path/to/project",
  "top_n": 5,
  "min_imports": 3
}
```

**Output:**
```
# Architectural Hubs (most imported files)

1. **src/api/client.py** (12← imports)
   Contains: APIClient, Request, Response
2. **src/models/user.py** (10← imports)
   Contains: User, Profile, Session
3. **src/config.py** (8← imports)
   Contains: Config, Settings
```

### codenav_get_dependencies

Get dependency relationships.

**Input:**
```json
{
  "path": "/path/to/project",
  "file": "src/api/client.py",
  "direction": "both",
  "depth": 1
}
```

**Output:**
```
# Dependencies for: src/api/client.py

## Imports (5)
  → src/config.py
  → src/models/user.py
  → src/utils/http.py
  → requests
  → json

## Imported By (12)
  ← src/api/auth.py
  ← src/api/payments.py
  ← src/services/user_service.py
  ...
```

### codenav_get_structure

Get file structure with symbols.

**Input:**
```json
{
  "file_path": "src/api/client.py",
  "include_private": false
}
```

**Output:**
```
# Structure: src/api/client.py

## Classes
- `APIClient` (L15-120)
- `Response` (L122-145)

## Functions
- `create_client` (L147-155)
- `make_request` (L157-180)

## Methods (8)
- `get` (L25)
- `post` (L45)
- `delete` (L65)
...
```

## Token Efficiency

Codenav responses are designed for minimal token usage:

| Operation | Without Codenav | With Codenav | Savings |
|-----------|-----------------|--------------|---------|
| Understand project | Read all files (~50K tokens) | codenav_scan (~2K tokens) | 96% |
| Find function | grep + read files (~10K tokens) | codenav_search (~500 tokens) | 95% |
| Read implementation | Full file (~2K tokens) | codenav_read (~200 tokens) | 90% |
| Find entry points | Manual search (~20K tokens) | codenav_get_hubs (~1K tokens) | 95% |

## Configuration Options

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CODENAV_WORKSPACE` | Default workspace directory | Current directory |
| `CODENAV_CACHE_DIR` | Directory for cached maps | `.codenav/` |
| `CODENAV_LOG_LEVEL` | Logging level | `INFO` |

### Claude Code Settings

```json
{
  "mcpServers": {
    "codenav": {
      "command": "python",
      "args": ["-m", "codenav.mcp", "--workspace", "/path/to/project"],
      "env": {
        "CODENAV_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### Claude Desktop Settings

For Claude Desktop on macOS, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "codenav": {
      "command": "/usr/local/bin/python3",
      "args": ["-m", "codenav.mcp"],
      "env": {}
    }
  }
}
```

## Skills.sh Integration

Codenav includes a `SKILL.md` manifest for auto-discovery:

1. Copy `SKILL.md` to your skills directory
2. Claude will automatically recognize Codenav capabilities
3. The skill triggers on relevant queries

## Troubleshooting

### Server not starting

```bash
# Test the server manually
python -m codenav.mcp --debug

# Check MCP is installed
pip show mcp
```

### Tools not appearing

1. Restart Claude Code/Desktop
2. Check the configuration file syntax
3. Verify the Python path is correct

### Slow scans

For large codebases:
- Use `git_only: true` to limit to tracked files
- Add ignore patterns for `node_modules`, `venv`, etc.
- The first scan creates a cache; subsequent scans are faster

## Development

### Running the server locally

```bash
# Development mode with auto-reload
python -m codenav.mcp --debug

# With specific workspace
python -m codenav.mcp --workspace /path/to/project
```

### Testing tools

```bash
# Use MCP Inspector
npx @anthropic/mcp-inspector python -m codenav.mcp
```

## Security Considerations

- The MCP server only has access to the specified workspace
- No network requests are made except for the MCP protocol
- All file operations are read-only
- Sensitive files can be excluded via ignore patterns

---

*For more information, see the [main README](../README.md) or the [API Reference](api-reference.md).*
