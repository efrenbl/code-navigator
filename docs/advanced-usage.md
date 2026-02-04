# Advanced Usage Guide

This guide covers advanced patterns and techniques for getting the most out of Code Navigator.

## Table of Contents

- [Multi-File Workflows](#multi-file-workflows)
- [Refactoring Patterns](#refactoring-patterns)
- [Debugging Workflows](#debugging-workflows)
- [Integration Patterns](#integration-patterns)
- [Performance Optimization](#performance-optimization)
- [Map Maintenance](#map-maintenance)

---

## Multi-File Workflows

When changes span multiple files, use a systematic approach:

### 1. Find All Related Symbols

```bash
# Find the main class
code-search "UserService" --type class

# Find related models
code-search "User" --file "models/"

# Find all handlers
code-search "handler" --type function --file "api/"
```

### 2. Get Dependency Graph

```bash
# See what UserService calls
code-search --deps "UserService"

# Output:
# {
#   "calls": ["Database", "validate", "send_email"],
#   "called_by": ["api_handler", "admin_controller"]
# }
```

### 3. Read Each Location

```bash
# Read with minimal context
code-read src/services/user.py 12-45 --symbol
code-read src/models/user.py 5-30 --symbol
code-read src/api/handlers.py 50-75 --symbol
```

### 4. Batch Reading (Python)

```python
from codenav import CodeSearcher, LineReader

searcher = CodeSearcher('.codenav.json')
reader = LineReader()

# Find all related symbols
results = searcher.search_symbol('User', limit=20)

# Group by file
by_file = {}
for r in results:
    by_file.setdefault(r.file, []).append(r)

# Read each file's relevant sections
for file_path, symbols in by_file.items():
    ranges = [(s.lines[0], s.lines[1]) for s in symbols]
    content = reader.read_ranges(file_path, ranges, context=1)
    print(f"\n=== {file_path} ===")
    for section in content['sections']:
        for line in section['lines']:
            print(f"{line['num']}: {line['content']}")
```

---

## Refactoring Patterns

### Rename Symbol Across Codebase

```bash
# 1. Find all usages
code-search --deps "old_function_name"

# Output shows:
# - Where it's defined
# - All places that call it

# 2. Read each location
# Result: {"called_by": [
#   {"name": "caller1", "file": "a.py", "lines": [10, 20]},
#   {"name": "caller2", "file": "b.py", "lines": [30, 40]}
# ]}

# 3. Read and update each caller
for each caller:
    code-read $file $lines -o code
    # Make the rename with exact line numbers
```

### Extract Method

```bash
# 1. Find the function to refactor
code-search "large_function" --type function

# 2. Read with smart truncation to see structure
code-read src/utils.py 100-300 --symbol --max-lines 80

# 3. Identify extraction points from the truncated view
# The ellipsis shows where to look for breakpoints

# 4. Read specific sections you need to move
code-read src/utils.py 150-180  # The code to extract
```

### Move Method to Another Class

```bash
# 1. Get file structures for both classes
code-search --structure src/old_class.py
code-search --structure src/new_class.py

# 2. Read the method to move
code-read src/old_class.py 45-67 --symbol

# 3. Check dependencies
code-search --deps "method_to_move"

# 4. Read all dependencies to understand what needs to change
```

---

## Debugging Workflows

### Error Trace Investigation

```bash
# 1. Error mentions specific function
code-search "calculate_tax"

# 2. Check what it depends on
code-search --deps "calculate_tax"

# 3. Read the function
code-read src/tax.py 45-67 --symbol

# 4. Read its dependencies
code-read src/rates.py 12-30 --symbol
```

### Finding Where an Error Could Originate

```bash
# Search for exception raising
code-read src/payments.py --search "raise.*Error"

# Search for specific error message
code-read src/payments.py --search "Invalid amount"
```

### Tracing Call Chains

```python
from codenav import CodeSearcher

searcher = CodeSearcher('.codenav.json')

def trace_calls(symbol, depth=0, max_depth=3, seen=None):
    """Recursively trace what a symbol calls."""
    if seen is None:
        seen = set()
    if depth > max_depth or symbol in seen:
        return
    seen.add(symbol)

    deps = searcher.find_dependencies(symbol)
    indent = "  " * depth

    print(f"{indent}{symbol}")
    if deps['file']:
        print(f"{indent}  @ {deps['file']}:{deps['lines']}")

    for call in deps.get('calls', []):
        trace_calls(call, depth + 1, max_depth, seen)

# Usage
trace_calls('process_order')
```

---

## Integration Patterns

### Pre-Commit Hook

```bash
#!/bin/bash
# .git/hooks/pre-commit

# Regenerate code map if Python files changed
if git diff --cached --name-only | grep -q '\.py$'; then
    echo "Regenerating code map..."
    codenav scan . -o .codenav.json
    git add .codenav.json
fi
```

### CI/CD Integration

```yaml
# .github/workflows/codenav.yml
name: Update Code Map

on:
  push:
    branches: [main]
    paths:
      - '**.py'
      - '**.js'
      - '**.ts'

jobs:
  update-map:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install code-navigator
        run: pip install code-navigator

      - name: Generate code map
        run: codenav scan . -o .codenav.json

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: codenav
          path: .codenav.json
```

### IDE Extension Helper

```python
# vscode_helper.py
import json
import sys
from codenav import CodeSearcher

def goto_symbol(query):
    """Return VSCode-compatible location for a symbol."""
    searcher = CodeSearcher('.codenav.json')
    results = searcher.search_symbol(query, limit=1)

    if results:
        r = results[0]
        return {
            "path": r.file,
            "line": r.lines[0],
            "column": 0
        }
    return None

if __name__ == '__main__':
    result = goto_symbol(sys.argv[1])
    print(json.dumps(result))
```

---

## Performance Optimization

### Large Codebases (10,000+ files)

```bash
# Map specific directories instead of entire codebase
codenav scan src/ -o .codenav-src.json
codenav scan lib/ -o .codenav-lib.json

# Search with specific map
code-search "handler" -m .codenav-src.json

# Combine maps programmatically if needed
```

### Incremental Updates

```python
import json
from pathlib import Path
from codenav import CodeNavigator

def get_changed_files(since_hash):
    """Get files changed since a git commit."""
    import subprocess
    result = subprocess.run(
        ['git', 'diff', '--name-only', since_hash],
        capture_output=True, text=True
    )
    return result.stdout.strip().split('\n')

def update_map_incrementally(map_path, root_path, changed_files):
    """Update only changed files in the map."""
    with open(map_path) as f:
        code_map = json.load(f)

    mapper = CodeNavigator(root_path)

    for file_path in changed_files:
        full_path = Path(root_path) / file_path

        # Remove old entry
        if file_path in code_map['files']:
            del code_map['files'][file_path]

        # Add new entry if file exists
        if full_path.exists() and mapper.get_language(full_path):
            symbols = mapper.analyze_file(full_path)
            # ... add to code_map

    # Update index
    # ... rebuild index from files

    with open(map_path, 'w') as f:
        json.dump(code_map, f)
```

### Memory-Efficient Scanning

```bash
# Exclude test files and generated code
codenav scan . -i "test_*.py" "*_test.py" "*_generated.py" "migrations/"

# Exclude large auto-generated files
codenav scan . -i "*.min.js" "*.bundle.js" "vendor/"
```

---

## Map Maintenance

### When to Regenerate

Regenerate the code map when:

1. **New files added**: New code won't be in the index
2. **Files deleted**: Old entries will cause errors
3. **Major refactoring**: Symbol locations changed
4. **After merging branches**: Code may have shifted

### Automated Regeneration

```bash
# Makefile target
.PHONY: codenav
codenav:
    @echo "Generating code map..."
    @codenav scan . -o .codenav.json
    @echo "Done. Stats:"
    @code-search --stats | python -m json.tool

# Run after common operations
git-pull:
    git pull
    make codenav

git-merge:
    git merge $(BRANCH)
    make codenav
```

### Validating Maps

```python
from codenav import CodeSearcher
from pathlib import Path

def validate_codenav(map_path, root_path):
    """Check if code map is still valid."""
    searcher = CodeSearcher(map_path)
    stats = searcher.get_stats()

    issues = []

    for file_path in searcher.code_map['files']:
        full_path = Path(root_path) / file_path
        if not full_path.exists():
            issues.append(f"Missing file: {file_path}")

    if issues:
        print("Code map is stale:")
        for issue in issues[:10]:
            print(f"  - {issue}")
        return False

    print(f"Code map valid: {stats['files']} files, {stats['total_symbols']} symbols")
    return True
```

### Comparing Maps

```python
import json

def compare_maps(old_path, new_path):
    """Compare two code maps to see what changed."""
    with open(old_path) as f:
        old = json.load(f)
    with open(new_path) as f:
        new = json.load(f)

    old_files = set(old['files'].keys())
    new_files = set(new['files'].keys())

    added = new_files - old_files
    removed = old_files - new_files
    common = old_files & new_files

    changed = []
    for f in common:
        if old['files'][f]['hash'] != new['files'][f]['hash']:
            changed.append(f)

    return {
        'added': list(added),
        'removed': list(removed),
        'changed': changed
    }
```

---

## Token Budget Estimation

Use these estimates when planning your workflow:

| Content | Approximate Tokens |
|---------|-------------------|
| Average line of code | ~15 tokens |
| Small function (10 lines) | ~150 tokens |
| Medium function (30 lines) | ~450 tokens |
| Large function (100 lines) | ~1,500 tokens |
| Small class (50 lines) | ~750 tokens |
| Large class (200 lines) | ~3,000 tokens |
| Code map search result | ~50 tokens |
| File structure query | ~100 tokens |

### Budget Planning

```bash
# Check codebase size
code-search --stats

# Output:
# {
#   "files": 142,
#   "total_symbols": 1847,
#   "by_type": {"function": 892, "class": 156, "method": 799}
# }

# Estimate:
# - Full codebase read: 142 files * 200 lines * 15 tokens = 426,000 tokens
# - Targeted approach: 5 functions * 30 lines * 15 tokens = 2,250 tokens
# - Savings: 99.5%
```
