#!/usr/bin/env python3
"""Code Mapper - Generates a structural map/graph of a codebase for token-efficient navigation.

This module creates a lightweight index of functions, classes, methods, and their
relationships within a codebase. The generated index can be used for quick symbol
lookup without reading entire files.

Example:
    Command line usage:
        $ code-map /path/to/project -o .codemap.json

    Python API usage:
        >>> mapper = CodeMapper('/path/to/project')
        >>> code_map = mapper.scan()
        >>> print(code_map['stats'])
        {'files_processed': 142, 'symbols_found': 1847, 'errors': 0}

Attributes:
    LANGUAGE_EXTENSIONS: Dict mapping language names to file extensions.
    DEFAULT_IGNORE_PATTERNS: List of patterns to ignore when scanning.
"""

import ast
import json
import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import argparse
import fnmatch

__version__ = "1.0.1"

# Supported languages and their extensions
LANGUAGE_EXTENSIONS = {
    'python': ['.py'],
    'javascript': ['.js', '.jsx', '.mjs'],
    'typescript': ['.ts', '.tsx'],
    'java': ['.java'],
    'go': ['.go'],
    'rust': ['.rs'],
    'c': ['.c', '.h'],
    'cpp': ['.cpp', '.hpp', '.cc', '.hh', '.cxx'],
    'ruby': ['.rb'],
    'php': ['.php'],
}

DEFAULT_IGNORE_PATTERNS = [
    'node_modules', '__pycache__', '.git', '.svn', '.hg',
    'venv', 'env', '.env', 'dist', 'build', '.next',
    'coverage', '.nyc_output', '*.min.js', '*.bundle.js',
    '.tox', 'eggs', '*.egg-info', '.pytest_cache',
    'vendor', 'target', 'bin', 'obj', '.idea', '.vscode'
]


@dataclass
class Symbol:
    """Represents a code symbol (function, class, method, etc.).

    Attributes:
        name: The symbol's name (e.g., 'process_payment').
        type: The symbol type ('function', 'class', 'method', 'variable', 'import').
        file_path: Relative path to the file containing the symbol.
        line_start: Starting line number (1-indexed).
        line_end: Ending line number (1-indexed, inclusive).
        signature: Function/class signature (e.g., 'def foo(x: int) -> str').
        docstring: First few lines of docstring, if present.
        parent: For methods, the containing class name.
        dependencies: List of symbols this symbol calls/uses.
        decorators: List of decorator names applied to this symbol.

    Example:
        >>> symbol = Symbol(
        ...     name='process_payment',
        ...     type='function',
        ...     file_path='src/billing.py',
        ...     line_start=45,
        ...     line_end=89,
        ...     signature='def process_payment(user_id: int, amount: Decimal)'
        ... )
    """
    name: str
    type: str
    file_path: str
    line_start: int
    line_end: int
    signature: Optional[str] = None
    docstring: Optional[str] = None
    parent: Optional[str] = None
    dependencies: List[str] = None
    decorators: List[str] = None

    def __post_init__(self):
        """Initialize mutable default values."""
        if self.dependencies is None:
            self.dependencies = []
        if self.decorators is None:
            self.decorators = []


class PythonAnalyzer(ast.NodeVisitor):
    """Analyzes Python files using AST for accurate symbol extraction.

    This analyzer provides the most accurate symbol detection for Python files,
    using Python's built-in AST module to parse the code structure.

    Attributes:
        file_path: Path to the file being analyzed.
        source: Source code content.
        lines: List of source lines.
        symbols: Extracted symbols.
        current_class: Name of class currently being visited (for method detection).
        imports: List of imported modules/names.

    Example:
        >>> source = '''
        ... def greet(name: str) -> str:
        ...     \"\"\"Say hello.\"\"\"
        ...     return f"Hello, {name}"
        ... '''
        >>> analyzer = PythonAnalyzer('example.py', source)
        >>> symbols = analyzer.analyze()
        >>> print(symbols[0].name)
        'greet'
    """

    def __init__(self, file_path: str, source: str):
        """Initialize the Python analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
        """
        self.file_path = file_path
        self.source = source
        self.lines = source.split('\n')
        self.symbols: List[Symbol] = []
        self.current_class: Optional[str] = None
        self.imports: List[str] = []

    def get_line_end(self, node) -> int:
        """Get the end line of an AST node.

        Args:
            node: An AST node.

        Returns:
            The ending line number of the node.
        """
        if hasattr(node, 'end_lineno') and node.end_lineno:
            return node.end_lineno
        if hasattr(node, 'body') and node.body:
            last_node = node.body[-1]
            return self.get_line_end(last_node)
        return node.lineno

    def get_signature(self, node) -> str:
        """Extract function/method signature from an AST node.

        Args:
            node: A FunctionDef or AsyncFunctionDef AST node.

        Returns:
            String representation of the function signature.

        Example:
            >>> # For 'async def foo(x: int) -> str:'
            >>> signature = analyzer.get_signature(node)
            >>> print(signature)
            'async def foo(x: int) -> str'
        """
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    try:
                        arg_str += f": {ast.unparse(arg.annotation)}"
                    except:
                        pass
                args.append(arg_str)

            returns = ""
            if node.returns:
                try:
                    returns = f" -> {ast.unparse(node.returns)}"
                except:
                    pass

            prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return f"{prefix}def {node.name}({', '.join(args)}){returns}"
        return ""

    def get_decorators(self, node) -> List[str]:
        """Extract decorator names from an AST node.

        Args:
            node: An AST node with decorator_list attribute.

        Returns:
            List of decorator name strings.
        """
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except:
                if isinstance(dec, ast.Name):
                    decorators.append(dec.id)
        return decorators

    def get_docstring(self, node) -> Optional[str]:
        """Extract docstring from an AST node, truncated for efficiency.

        Args:
            node: An AST node that may have a docstring.

        Returns:
            First 3 lines of the docstring, or None if no docstring.
        """
        doc = ast.get_docstring(node)
        if doc:
            lines = doc.split('\n')
            if len(lines) > 3:
                return '\n'.join(lines[:3]) + '...'
            return doc
        return None

    def visit_Import(self, node):
        """Visit an import statement."""
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Visit a from...import statement."""
        module = node.module or ''
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        """Visit a class definition."""
        bases = []
        for base in node.bases:
            try:
                bases.append(ast.unparse(base))
            except:
                pass

        signature = f"class {node.name}"
        if bases:
            signature += f"({', '.join(bases)})"

        symbol = Symbol(
            name=node.name,
            type='class',
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=self.get_line_end(node),
            signature=signature,
            docstring=self.get_docstring(node),
            decorators=self.get_decorators(node)
        )
        self.symbols.append(symbol)

        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        """Visit a function definition."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node):
        """Visit an async function definition."""
        self._visit_function(node)

    def _visit_function(self, node):
        """Process a function or async function definition.

        Args:
            node: A FunctionDef or AsyncFunctionDef AST node.
        """
        symbol_type = 'method' if self.current_class else 'function'

        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)

        symbol = Symbol(
            name=node.name,
            type=symbol_type,
            file_path=self.file_path,
            line_start=node.lineno,
            line_end=self.get_line_end(node),
            signature=self.get_signature(node),
            docstring=self.get_docstring(node),
            parent=self.current_class,
            dependencies=list(set(calls)),
            decorators=self.get_decorators(node)
        )
        self.symbols.append(symbol)
        self.generic_visit(node)

    def analyze(self) -> List[Symbol]:
        """Parse and analyze the file.

        Returns:
            List of Symbol objects found in the file.

        Raises:
            SyntaxError: If the file has invalid Python syntax (caught and logged).
        """
        try:
            tree = ast.parse(self.source)
            self.visit(tree)
        except SyntaxError as e:
            print(f"Syntax error in {self.file_path}: {e}", file=sys.stderr)
        return self.symbols


class GenericAnalyzer:
    """Regex-based analyzer for non-Python languages.

    Provides symbol detection for JavaScript, TypeScript, Java, Go, Rust, and C/C++
    using regular expression patterns. Less accurate than AST analysis but works
    across multiple languages.

    Attributes:
        PATTERNS: Dict of regex patterns for each supported language.
        file_path: Path to the file being analyzed.
        source: Source code content.
        language: The programming language of the file.

    Example:
        >>> source = 'function greet(name) { return "Hello, " + name; }'
        >>> analyzer = GenericAnalyzer('example.js', source, 'javascript')
        >>> symbols = analyzer.analyze()
    """

    PATTERNS = {
        'javascript': {
            'function': r'(?:async\s+)?function\s+(\w+)\s*\([^)]*\)',
            'arrow': r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            'class': r'class\s+(\w+)(?:\s+extends\s+\w+)?',
            'method': r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*{',
        },
        'typescript': {
            'function': r'(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)',
            'interface': r'interface\s+(\w+)',
            'type': r'type\s+(\w+)\s*=',
            'class': r'class\s+(\w+)(?:\s+extends\s+\w+)?(?:\s+implements\s+\w+)?',
        },
        'java': {
            'class': r'(?:public|private|protected)?\s*class\s+(\w+)',
            'interface': r'interface\s+(\w+)',
            'method': r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+(?:<[^>]*>)?)\s+(\w+)\s*\([^)]*\)',
        },
        'go': {
            'function': r'func\s+(\w+)\s*\([^)]*\)',
            'method': r'func\s+\([^)]+\)\s+(\w+)\s*\([^)]*\)',
            'struct': r'type\s+(\w+)\s+struct',
            'interface': r'type\s+(\w+)\s+interface',
        },
        'rust': {
            'function': r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)',
            'struct': r'(?:pub\s+)?struct\s+(\w+)',
            'impl': r'impl(?:<[^>]*>)?\s+(\w+)',
            'trait': r'(?:pub\s+)?trait\s+(\w+)',
            'enum': r'(?:pub\s+)?enum\s+(\w+)',
        },
    }

    def __init__(self, file_path: str, source: str, language: str):
        """Initialize the generic analyzer.

        Args:
            file_path: Relative path to the file.
            source: Source code content.
            language: Programming language identifier.
        """
        self.file_path = file_path
        self.source = source
        self.language = language
        self.lines = source.split('\n')

    def analyze(self) -> List[Symbol]:
        """Analyze the file using regex patterns.

        Returns:
            List of Symbol objects found in the file.
        """
        import re
        symbols = []
        patterns = self.PATTERNS.get(self.language, {})

        for symbol_type, pattern in patterns.items():
            for match in re.finditer(pattern, self.source, re.MULTILINE):
                name = match.group(1)
                line_num = self.source[:match.start()].count('\n') + 1

                line_end = line_num
                brace_count = 0
                started = False
                for i, line in enumerate(self.lines[line_num-1:], start=line_num):
                    brace_count += line.count('{') - line.count('}')
                    if '{' in line:
                        started = True
                    if started and brace_count <= 0:
                        line_end = i
                        break
                    if i > line_num + 500:
                        line_end = i
                        break

                symbols.append(Symbol(
                    name=name,
                    type=symbol_type,
                    file_path=self.file_path,
                    line_start=line_num,
                    line_end=line_end,
                    signature=match.group(0).strip()[:100]
                ))

        return symbols


class CodeMapper:
    """Main class for mapping a codebase to create a searchable index.

    Scans a directory tree, analyzes source files, and generates a JSON index
    containing all symbols, their locations, signatures, and dependencies.

    Attributes:
        root_path: Absolute path to the codebase root.
        ignore_patterns: List of patterns to skip during scanning.
        symbols: List of all discovered symbols.
        file_hashes: Dict mapping file paths to content hashes.
        stats: Dict with processing statistics.

    Example:
        >>> mapper = CodeMapper('/path/to/project')
        >>> code_map = mapper.scan()
        >>> print(f"Found {code_map['stats']['symbols_found']} symbols")
        Found 1847 symbols

        >>> # Save to file
        >>> import json
        >>> with open('.codemap.json', 'w') as f:
        ...     json.dump(code_map, f)
    """

    def __init__(self, root_path: str, ignore_patterns: List[str] = None):
        """Initialize the code mapper.

        Args:
            root_path: Path to the root directory to scan.
            ignore_patterns: Additional patterns to ignore. Merged with defaults.
        """
        self.root_path = Path(root_path).resolve()
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS
        self.symbols: List[Symbol] = []
        self.file_hashes: Dict[str, str] = {}
        self.stats = {
            'files_processed': 0,
            'symbols_found': 0,
            'errors': 0
        }

    def should_ignore(self, path: Path) -> bool:
        """Check if a path should be ignored during scanning.

        Args:
            path: Path to check.

        Returns:
            True if the path matches any ignore pattern.
        """
        path_str = str(path)
        name = path.name

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
            if pattern in path_str:
                return True
        return False

    def get_language(self, file_path: Path) -> Optional[str]:
        """Determine the programming language from file extension.

        Args:
            file_path: Path to the file.

        Returns:
            Language identifier string, or None if not recognized.
        """
        ext = file_path.suffix.lower()
        for lang, extensions in LANGUAGE_EXTENSIONS.items():
            if ext in extensions:
                return lang
        return None

    def hash_file(self, content: str) -> str:
        """Generate a hash for file content.

        Args:
            content: File content string.

        Returns:
            12-character MD5 hash of the content.
        """
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def analyze_file(self, file_path: Path) -> List[Symbol]:
        """Analyze a single file and extract its symbols.

        Args:
            file_path: Path to the file to analyze.

        Returns:
            List of Symbol objects found in the file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            rel_path = str(file_path.relative_to(self.root_path))
            self.file_hashes[rel_path] = self.hash_file(content)

            language = self.get_language(file_path)
            if language == 'python':
                analyzer = PythonAnalyzer(rel_path, content)
            elif language:
                analyzer = GenericAnalyzer(rel_path, content, language)
            else:
                return []

            return analyzer.analyze()

        except Exception as e:
            self.stats['errors'] += 1
            print(f"Error analyzing {file_path}: {e}", file=sys.stderr)
            return []

    def scan(self) -> Dict[str, Any]:
        """Scan the entire codebase and generate a code map.

        Returns:
            Dict containing the complete code map with files, index, and stats.

        Example:
            >>> mapper = CodeMapper('/my/project')
            >>> result = mapper.scan()
            >>> print(result.keys())
            dict_keys(['version', 'root', 'generated_at', 'stats', 'files', 'index'])
        """
        print(f"Scanning codebase at: {self.root_path}", file=sys.stderr)

        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if not self.should_ignore(Path(root) / d)]

            for file in files:
                file_path = Path(root) / file
                if self.should_ignore(file_path):
                    continue

                language = self.get_language(file_path)
                if language:
                    symbols = self.analyze_file(file_path)
                    self.symbols.extend(symbols)
                    self.stats['files_processed'] += 1

        self.stats['symbols_found'] = len(self.symbols)
        return self.generate_map()

    def generate_map(self) -> Dict[str, Any]:
        """Generate the code map structure from collected symbols.

        Returns:
            Dict with version, root, timestamp, stats, files map, and symbol index.
        """
        files_map = {}
        for symbol in self.symbols:
            if symbol.file_path not in files_map:
                files_map[symbol.file_path] = {
                    'hash': self.file_hashes.get(symbol.file_path, ''),
                    'symbols': []
                }
            files_map[symbol.file_path]['symbols'].append({
                'name': symbol.name,
                'type': symbol.type,
                'lines': [symbol.line_start, symbol.line_end],
                'signature': symbol.signature,
                'docstring': symbol.docstring,
                'parent': symbol.parent,
                'deps': symbol.dependencies[:10] if symbol.dependencies else None,
                'decorators': symbol.decorators if symbol.decorators else None
            })

        symbol_index = {}
        for symbol in self.symbols:
            key = symbol.name.lower()
            if key not in symbol_index:
                symbol_index[key] = []
            symbol_index[key].append({
                'file': symbol.file_path,
                'type': symbol.type,
                'lines': [symbol.line_start, symbol.line_end],
                'parent': symbol.parent
            })

        return {
            'version': '1.0',
            'root': str(self.root_path),
            'generated_at': datetime.now().isoformat(),
            'stats': self.stats,
            'files': files_map,
            'index': symbol_index
        }


def main():
    """Command-line interface for the code mapper.

    Usage:
        code-map /path/to/project [-o OUTPUT] [-i IGNORE...] [--pretty]

    Example:
        $ code-map /my/project -o .codemap.json --pretty
    """
    parser = argparse.ArgumentParser(
        description='Generate a code map for token-efficient navigation',
        epilog='Example: code-map /my/project -o .codemap.json --pretty'
    )
    parser.add_argument(
        'path',
        help='Path to the codebase root directory'
    )
    parser.add_argument(
        '-o', '--output',
        default='.codemap.json',
        help='Output file path (default: .codemap.json)'
    )
    parser.add_argument(
        '-i', '--ignore',
        nargs='*',
        help='Additional patterns to ignore'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        help='Pretty-print JSON output'
    )
    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    args = parser.parse_args()

    ignore_patterns = DEFAULT_IGNORE_PATTERNS.copy()
    if args.ignore:
        ignore_patterns.extend(args.ignore)

    mapper = CodeMapper(args.path, ignore_patterns)
    code_map = mapper.scan()

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.join(args.path, output_path)

    with open(output_path, 'w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(code_map, f, indent=2)
        else:
            json.dump(code_map, f, separators=(',', ':'))

    print(f"\n✓ Code map generated: {output_path}", file=sys.stderr)
    print(f"  Files processed: {code_map['stats']['files_processed']}", file=sys.stderr)
    print(f"  Symbols found: {code_map['stats']['symbols_found']}", file=sys.stderr)

    print(json.dumps({
        'output': output_path,
        'stats': code_map['stats']
    }))


if __name__ == '__main__':
    main()
