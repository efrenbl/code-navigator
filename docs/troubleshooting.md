# Troubleshooting Guide

This guide helps you resolve common issues with Claude Code Navigator.

## Table of Contents

- [Installation Issues](#installation-issues)
- [Code Map Generation Issues](#code-map-generation-issues)
- [Search Issues](#search-issues)
- [Line Reader Issues](#line-reader-issues)
- [Performance Issues](#performance-issues)
- [Common Error Messages](#common-error-messages)

---

## Installation Issues

### "command not found: code-map"

**Cause:** Package not installed correctly or not in PATH.

**Solutions:**

1. Verify installation:
   ```bash
   pip show claude-code-navigator
   ```

2. Try running with Python:
   ```bash
   python -m code_map_navigator.code_mapper --help
   ```

3. Check if scripts directory is in PATH:
   ```bash
   pip show -f claude-code-navigator | grep "Location"
   # Add the scripts directory to PATH
   ```

4. Reinstall:
   ```bash
   pip uninstall claude-code-navigator
   pip install claude-code-navigator
   ```

### Import errors after installation

**Cause:** Conflicting package or Python path issues.

**Solutions:**

1. Check for conflicts:
   ```bash
   pip list | grep code
   ```

2. Use a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install claude-code-navigator
   ```

---

## Code Map Generation Issues

### "Syntax error in file.py"

**Cause:** File has invalid Python syntax.

**What happens:** The file is skipped, other files continue processing.

**Solutions:**

1. Check the specific file:
   ```bash
   python -m py_compile path/to/file.py
   ```

2. Fix the syntax error or exclude the file:
   ```bash
   code-map . -i "broken_file.py"
   ```

### Map file is empty or very small

**Cause:** All files were ignored or no supported languages found.

**Solutions:**

1. Check ignore patterns:
   ```bash
   # Default patterns include node_modules, __pycache__, etc.
   # Make sure your source files aren't being ignored
   ```

2. Verify file extensions:
   ```bash
   # Supported: .py, .js, .jsx, .ts, .tsx, .java, .go, .rs, .c, .h, .cpp, .rb, .php
   ls -la *.py  # Check if files exist
   ```

3. Run with verbose output:
   ```bash
   code-map . 2>&1 | head -20
   ```

### "Permission denied" errors

**Cause:** No read access to some files.

**Solutions:**

1. Check file permissions:
   ```bash
   ls -la path/to/file
   ```

2. Run with appropriate permissions or exclude directories:
   ```bash
   code-map . -i "protected_dir/"
   ```

### Map generation is very slow

**Cause:** Large codebase or many files.

**Solutions:**

1. Use ignore patterns for unnecessary directories:
   ```bash
   code-map . -i "node_modules" "vendor" "dist" "build" ".git"
   ```

2. Map specific directories:
   ```bash
   code-map src/ -o .codemap-src.json
   ```

3. Check for large generated files:
   ```bash
   code-map . -i "*.min.js" "*.bundle.js"
   ```

---

## Search Issues

### "Code map not found"

**Cause:** .codemap.json doesn't exist or is in wrong location.

**Solutions:**

1. Generate the map first:
   ```bash
   code-map .
   ```

2. Specify the correct path:
   ```bash
   code-search "query" -m /path/to/.codemap.json
   ```

3. Check if file exists:
   ```bash
   ls -la .codemap.json
   ```

### Search returns no results

**Cause:** Symbol not found or filters too restrictive.

**Solutions:**

1. Try without type filter:
   ```bash
   code-search "payment"  # Instead of --type function
   ```

2. Check exact spelling:
   ```bash
   code-search --stats  # See what symbols exist
   ```

3. Disable fuzzy matching for exact search:
   ```bash
   code-search "process_payment" --no-fuzzy
   ```

4. Check if symbol is in ignored files:
   ```bash
   # Regenerate map without ignoring
   code-map . -o .codemap-full.json
   code-search "symbol" -m .codemap-full.json
   ```

### Search results are outdated

**Cause:** Code map is stale (code changed since generation).

**Solutions:**

1. Regenerate the map:
   ```bash
   code-map .
   ```

2. Check map generation time:
   ```bash
   code-search --stats | grep generated_at
   ```

### Wrong file in search results

**Cause:** Symbol exists in multiple files, wrong one ranked first.

**Solutions:**

1. Filter by file pattern:
   ```bash
   code-search "User" --file "models/"
   ```

2. Use exact search:
   ```bash
   code-search "UserModel" --no-fuzzy
   ```

---

## Line Reader Issues

### "File not found"

**Cause:** File path incorrect or file moved.

**Solutions:**

1. Use the path from search results:
   ```bash
   code-search "symbol"
   # Use the exact 'file' path from results
   code-read exact/path/from/results.py 10-20
   ```

2. Specify root directory:
   ```bash
   code-read src/file.py 10-20 -r /project/root
   ```

3. Use absolute path:
   ```bash
   code-read /full/path/to/file.py 10-20
   ```

### Line numbers don't match

**Cause:** File changed since map was generated.

**Solutions:**

1. Regenerate the map:
   ```bash
   code-map .
   ```

2. Check file hash:
   ```bash
   code-search --structure path/to/file.py
   # Compare hash with current file
   ```

### Truncation cutting off important code

**Cause:** max_lines setting too low.

**Solutions:**

1. Increase max_lines:
   ```bash
   code-read file.py 10-200 --symbol --max-lines 150
   ```

2. Read without truncation:
   ```bash
   code-read file.py 10-200  # Without --symbol flag
   ```

3. Read specific sections:
   ```bash
   code-read file.py "10-50,180-200"
   ```

---

## Performance Issues

### High memory usage during map generation

**Cause:** Very large files or many files.

**Solutions:**

1. Exclude large files:
   ```bash
   code-map . -i "*.min.js" "large_data.py"
   ```

2. Map in smaller chunks:
   ```bash
   code-map src/ -o .codemap-src.json
   code-map lib/ -o .codemap-lib.json
   ```

### Slow searches

**Cause:** Very large code map.

**Solutions:**

1. Use more specific queries:
   ```bash
   code-search "process_payment" --type function --file "billing/"
   ```

2. Limit results:
   ```bash
   code-search "handler" --limit 5
   ```

3. Disable fuzzy search for exact matches:
   ```bash
   code-search "exact_name" --no-fuzzy
   ```

---

## Common Error Messages

### "JSONDecodeError: Expecting value"

**Cause:** Corrupted or incomplete code map file.

**Solution:**
```bash
# Delete and regenerate
rm .codemap.json
code-map .
```

### "KeyError: 'files'" or "'index'"

**Cause:** Code map has wrong format or version.

**Solution:**
```bash
# Check version and regenerate if needed
code-search --stats
code-map . -o .codemap.json
```

### "UnicodeDecodeError"

**Cause:** File with unsupported encoding.

**Solutions:**

1. The tool handles this gracefully (uses 'replace' mode)
2. If persistent, identify and exclude problematic files:
   ```bash
   file path/to/file  # Check encoding
   code-map . -i "problematic_file.py"
   ```

### "RecursionError" during map generation

**Cause:** Circular imports or deeply nested structures.

**Solution:**
```bash
# Increase recursion limit (use with caution)
python -c "import sys; sys.setrecursionlimit(2000); from code_map_navigator import CodeMapper; CodeMapper('.').scan()"
```

---

## Getting Help

If you can't resolve an issue:

1. **Check existing issues:**
   https://github.com/efrenbl/claude-code-navigator/issues

2. **Create a new issue** with:
   - Python version (`python --version`)
   - Package version (`pip show claude-code-navigator`)
   - Operating system
   - Full error message
   - Steps to reproduce

3. **Include diagnostic info:**
   ```bash
   code-search --stats
   code-map --version
   python -c "import code_map_navigator; print(code_map_navigator.__version__)"
   ```
