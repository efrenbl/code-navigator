# Examples

This directory contains practical examples of using Code Navigator.

## Files

- `sample_codenav.json` - Example output from code_navigator.py
- `workflow_demo.sh` - Shell script demonstrating typical workflow

## Quick Demo

### 1. Generate a Code Map

```bash
# Map this examples directory
cd examples
codenav scan . -o demo-map.json --pretty
```

### 2. Search for Symbols

```bash
# Find all functions
code-search "function" -m demo-map.json --pretty

# Find a specific symbol
code-search "process" -m demo-map.json --type function
```

### 3. Read Specific Lines

```bash
# Read a function (lines 10-25)
code-read sample_project/main.py 10-25 -o code

# Read with context
code-read sample_project/main.py 15-20 -c 3 -o code
```

## Real-World Workflow

Here's how you'd use this tool when fixing a bug:

```bash
# 1. User reports: "payment processing is broken"

# 2. Search for payment-related code
code-search "payment" --type function

# Output:
# [{"name": "process_payment", "file": "src/billing.py", "lines": [45, 89]}]

# 3. Read only the relevant function
code-read src/billing.py 45-89 --symbol -o code

# 4. Now you have the exact code to fix!
```

## Token Savings Calculation

For a project with 500 files averaging 200 lines each:

| Approach | Lines Read | Tokens (~15/line) |
|----------|-----------|-------------------|
| Read 5 full files | 1,000 lines | ~15,000 tokens |
| Search + targeted read | ~50 lines | ~750 tokens |
| **Savings** | | **95%** |

## Sample Code Map Structure

See `sample_codenav.json` for the JSON structure:

```json
{
  "version": "1.0",
  "root": "/path/to/project",
  "generated_at": "2024-01-15T10:30:00",
  "stats": {
    "files_processed": 142,
    "symbols_found": 1847,
    "errors": 0
  },
  "files": {
    "src/main.py": {
      "hash": "a1b2c3d4",
      "symbols": [...]
    }
  },
  "index": {
    "symbol_name": [...]
  }
}
```

## Integration Examples

### Python Script

```python
from codenav import CodeNavigator, CodeSearcher, LineReader

# Generate map
mapper = CodeNavigator('/my/project')
code_map = mapper.scan()

# Search
searcher = CodeSearcher('/my/project/.codenav.json')
results = searcher.search_symbol('authenticate')

# Read
reader = LineReader('/my/project')
for result in results[:3]:
    content = reader.read_symbol(result.file, result.lines[0], result.lines[1])
    print(f"=== {result.name} ===")
    for line in content['lines']:
        print(f"{line['num']}: {line['content']}")
```

### Bash Script

```bash
#!/bin/bash
# workflow_demo.sh

PROJECT_PATH="$1"
SEARCH_TERM="$2"

# Generate map if it doesn't exist
if [ ! -f "$PROJECT_PATH/.codenav.json" ]; then
    echo "Generating code map..."
    codenav scan "$PROJECT_PATH"
fi

# Search
echo "Searching for: $SEARCH_TERM"
RESULTS=$(code-search "$SEARCH_TERM" -m "$PROJECT_PATH/.codenav.json")
echo "$RESULTS" | python -m json.tool

# Read first result
FILE=$(echo "$RESULTS" | python -c "import sys,json; r=json.load(sys.stdin); print(r[0]['file'] if r else '')")
LINES=$(echo "$RESULTS" | python -c "import sys,json; r=json.load(sys.stdin); print(f\"{r[0]['lines'][0]}-{r[0]['lines'][1]}\" if r else '')")

if [ -n "$FILE" ]; then
    echo ""
    echo "Reading: $FILE:$LINES"
    code-read "$PROJECT_PATH/$FILE" "$LINES" -o code
fi
```

## Before/After Comparison

### Before (Traditional Approach)

```bash
# Read entire files to find the code
cat src/api/handlers.py    # 500 lines
cat src/models/user.py     # 300 lines
cat src/utils/auth.py      # 200 lines
# Total: 1000 lines = ~15,000 tokens
```

### After (With Code Navigator)

```bash
# Search for what you need
code-search "authenticate" --type function
# [{"file": "src/utils/auth.py", "lines": [45, 67]}]

# Read only those lines
code-read src/utils/auth.py 45-67
# Total: 23 lines = ~345 tokens
```

**Savings: 97%**
