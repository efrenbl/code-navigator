# Frequently Asked Questions

## General

### What is Code Navigator?

Code Navigator is a tool that creates a searchable index of your codebase, allowing you to find and read specific code sections without loading entire files. This dramatically reduces token usage when working with AI coding assistants like Claude.

### How much does it reduce token usage?

In typical workflows, token usage is reduced by **90-97%**. For example:
- Traditional approach: Read 5 files × 200 lines × 15 tokens = 15,000 tokens
- With Navigator: Search (100 tokens) + Read 50 lines (750 tokens) = 850 tokens
- Savings: ~94%

### Does it work with all AI assistants?

Yes! While designed for Claude Code, the tools are standalone and work with any AI assistant or IDE that can run Python scripts.

---

## Installation

### What Python version is required?

Python 3.8 or higher.

### Are there any dependencies?

No! Code Navigator uses only the Python standard library. Zero external dependencies.

### Can I use it in a Docker container?

Yes. Example Dockerfile:
```dockerfile
FROM python:3.11-slim
RUN pip install code-navigator
WORKDIR /code
ENTRYPOINT ["codenav map"]
```

### Does it work on Windows?

Yes, it works on Windows, macOS, and Linux.

---

## Code Map

### How large is the generated .codenav.json file?

Typically 1-5% of your source code size:
- 1 MB codebase → ~10-50 KB map
- 10 MB codebase → ~100-500 KB map

### How long does it take to generate?

Very fast. Benchmarks on a modern laptop:
- 100 files: < 1 second
- 1,000 files: 5-10 seconds
- 10,000 files: 30-60 seconds

### Should I commit .codenav.json to git?

It depends:
- **Yes**: If team members use the same tools and regeneration is slow
- **No**: If it changes frequently and adds noise to diffs

Recommendation: Add to `.gitignore` and regenerate as needed.

### Does it detect changes automatically?

No, you need to regenerate manually. Consider adding a git hook:
```bash
# .git/hooks/post-merge
#!/bin/bash
codenav map . -o .codenav.json
```

### Can I map only specific directories?

Yes:
```bash
codenav map src/ -o .codenav-src.json
codenav map tests/ -o .codenav-tests.json
```

---

## Language Support

### Which languages are fully supported?

**Full AST analysis (best accuracy):**
- Python

**Regex-based analysis (good accuracy):**
- JavaScript
- TypeScript
- Java
- Go
- Rust
- C/C++
- Ruby
- PHP

### Why is Python support better?

Python's AST module provides accurate parsing of all language constructs. Other languages use regex patterns that work well for common patterns but may miss edge cases.

### Can I add support for a new language?

Yes! Add patterns to `GenericAnalyzer.PATTERNS`:

```python
'kotlin': {
    'function': r'fun\s+(\w+)',
    'class': r'class\s+(\w+)',
}
```

### What about mixed-language projects?

All supported languages in a project are indexed together. Use `--file` to filter searches:
```bash
codenav search "handler" --file "\.py$"  # Python only
codenav search "handler" --file "\.ts$"  # TypeScript only
```

---

## Search

### How does fuzzy matching work?

The search uses multiple strategies:
1. Exact match (score: 1.0)
2. Query contained in name (score: 0.7-0.9)
3. Name contained in query (score: 0.5)
4. Similarity ratio (score: 0.3-0.6)

### Can I search for multiple terms?

Use separate searches or pipe:
```bash
codenav search "user" && codenav search "auth"
```

Or in Python:
```python
results = []
for term in ['user', 'auth', 'login']:
    results.extend(searcher.search_symbol(term))
```

### How do I find all methods of a class?

```bash
codenav search --structure path/to/file.py
```

Or:
```bash
codenav search "ClassName" --deps
```

### Can I search by signature?

Fuzzy search includes signatures:
```bash
codenav search "int, str"  # Finds functions with these parameter types
```

---

## Line Reader

### What's the difference between `--symbol` and regular read?

Regular read: Returns exact lines specified
Symbol read: Adds smart truncation for large functions (shows head + tail with ellipsis)

### How do I read multiple disconnected ranges?

```bash
codenav read file.py "10-20,50-60,100-110"
```

Ranges close together are merged automatically.

### Can I output in different formats?

Yes:
- `-o json` (default): Structured JSON
- `-o code`: Human-readable with line numbers

---

## Integration

### Can I use this as a Python library?

Yes:
```python
from codenav import CodeNavigator, CodeSearcher, LineReader

mapper = CodeNavigator('/my/project')
code_map = mapper.scan()

searcher = CodeSearcher('.codenav.json')
results = searcher.search_symbol('function_name')

reader = LineReader()
content = reader.read_lines('file.py', 10, 20)
```

### Is there an API server mode?

Not built-in, but easy to create with Flask:
```python
from flask import Flask, jsonify, request
from codenav import CodeSearcher

app = Flask(__name__)
searcher = CodeSearcher('.codenav.json')

@app.route('/search')
def search():
    query = request.args.get('q')
    results = searcher.search_symbol(query)
    return jsonify([r.to_dict() for r in results])
```

### Can I use it with VS Code?

Not directly (no extension yet), but you can use the CLI from the integrated terminal or create a custom task.

---

## Troubleshooting

### Why are some symbols missing?

Common causes:
1. File has syntax errors
2. File is in an ignored directory
3. Symbol type not recognized (non-standard pattern)

Check with:
```bash
codenav map . 2>&1 | grep -i error
```

### Why are line numbers wrong?

The code map was generated before recent changes. Regenerate:
```bash
codenav map .
```

### Why is search slow?

For very large codebases:
1. Use more specific queries
2. Add type/file filters
3. Consider mapping subdirectories separately

---

## Best Practices

### When should I regenerate the map?

- After pulling changes
- After merging branches
- After adding new files
- When search results seem stale

### What's the ideal workflow?

1. Generate map once at project start
2. Search before reading (don't browse)
3. Use exact line numbers from search
4. Read with `--symbol` for functions/classes
5. Regenerate when needed

### How can I maximize token savings?

1. Always search first, never browse
2. Read only the lines you need
3. Use `--symbol` with `--max-lines` for large functions
4. Combine multiple ranges in one read
5. Use `--deps` to understand relationships without reading code

---

## Contributing

### How can I contribute?

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Development setup
- Code style guidelines
- Pull request process

### What's on the roadmap?

Potential future features:
- Incremental map updates
- Language server protocol support
- IDE extensions
- Additional language support
- Web UI for browsing maps
