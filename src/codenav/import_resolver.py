#!/usr/bin/env python3
"""Import Path Resolver - Intelligent multi-language import resolution.

This module provides a unified approach to resolving import paths across
multiple programming languages, supporting:
- Relative imports (./foo, ../bar)
- Path aliases (@/, ~/, #components)
- Implicit index files (index.js, __init__.py, mod.rs)
- Package/module resolution (node_modules, Python packages)

Key improvement over static approaches: accepts dynamic alias configuration
that can be loaded from tsconfig.json, jsconfig.json, pyproject.toml, etc.

Example:
    >>> resolver = ImportResolver('/my/project')
    >>> resolver.load_aliases_from_tsconfig()
    >>> result = resolver.resolve('src/api/routes.ts', '@/utils/helpers')
    >>> print(result)
    ResolveResult(path='src/utils/helpers.ts', strategy='alias')
"""

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class ResolveStrategy(Enum):
    """Enumeration of resolution strategies used."""

    EXACT = "exact"  # Direct path match
    RELATIVE = "relative"  # ./foo, ../bar
    ALIAS = "alias"  # @/foo, ~/bar, #components
    INDEX = "index"  # Implicit index file
    SUFFIX = "suffix"  # Partial path match
    MODULE = "module"  # Go/Python module prefix
    PACKAGE = "package"  # node_modules, Python package
    NOT_FOUND = "not_found"  # Resolution failed


@dataclass
class ResolveResult:
    """Result of an import resolution attempt.

    Attributes:
        path: Resolved file path (relative to root), or None if not found.
        strategy: Which strategy successfully resolved the import.
        candidates: All candidate paths that were tried.
        original_import: The original import string.
        confidence: 0.0-1.0 indicating resolution confidence.
    """

    path: Optional[str]
    strategy: ResolveStrategy
    candidates: List[str] = field(default_factory=list)
    original_import: str = ""
    confidence: float = 1.0

    @property
    def found(self) -> bool:
        """Whether the import was successfully resolved."""
        return self.path is not None and self.strategy != ResolveStrategy.NOT_FOUND


@dataclass
class AliasConfig:
    """Configuration for a single path alias.

    Attributes:
        pattern: The alias pattern (e.g., "@/*", "~/", "#components").
        targets: List of replacement paths (e.g., ["src/*"]).
        is_wildcard: Whether the pattern contains a wildcard.
        prefix: Part before the wildcard.
        suffix: Part after the wildcard.
    """

    pattern: str
    targets: List[str]
    is_wildcard: bool = False
    prefix: str = ""
    suffix: str = ""

    def __post_init__(self):
        """Parse pattern into prefix/suffix."""
        if "*" in self.pattern:
            self.is_wildcard = True
            idx = self.pattern.index("*")
            self.prefix = self.pattern[:idx]
            self.suffix = self.pattern[idx + 1 :]
        else:
            self.prefix = self.pattern

    def matches(self, import_path: str) -> Optional[str]:
        """Check if import matches this alias, return captured wildcard portion.

        Args:
            import_path: The import string to check.

        Returns:
            The wildcard portion if matched, None otherwise.
        """
        if not import_path.startswith(self.prefix):
            return None

        if not self.is_wildcard:
            # Exact match required
            return "" if import_path == self.pattern else None

        # Check suffix
        if self.suffix and not import_path.endswith(self.suffix):
            return None

        # Extract wildcard portion
        wildcard_part = import_path[len(self.prefix) :]
        if self.suffix:
            wildcard_part = wildcard_part[: -len(self.suffix)]

        return wildcard_part

    def apply(self, wildcard_part: str) -> List[str]:
        """Apply the alias transformation.

        Args:
            wildcard_part: The captured wildcard portion.

        Returns:
            List of resolved paths to try.
        """
        results = []
        for target in self.targets:
            if "*" in target:
                idx = target.index("*")
                resolved = target[:idx] + wildcard_part + target[idx + 1 :]
            else:
                resolved = target + wildcard_part if wildcard_part else target
            results.append(resolved)
        return results


class ImportResolver:
    """Multi-language import path resolver with dynamic alias support.

    This class resolves import statements to actual file paths using multiple
    strategies in a prioritized order. Unlike static resolvers, it accepts
    dynamic alias configuration that can be loaded from various config files.

    Resolution Order:
        1. Relative paths (./foo, ../bar)
        2. Configured aliases (@/, ~/, etc.)
        3. Module prefixes (Go modules, Python packages)
        4. Exact path match
        5. Implicit index files
        6. Suffix/partial match

    Attributes:
        root: Absolute path to project root.
        aliases: List of configured AliasConfig objects.
        file_index: Cached file index for fast lookups.
        module_name: Detected module/package name.
        base_url: Base URL for relative alias resolution.

    Example:
        >>> resolver = ImportResolver('/my/project')
        >>>
        >>> # Add aliases manually
        >>> resolver.add_alias('@/*', ['src/*'])
        >>> resolver.add_alias('~/', ['src/'])
        >>>
        >>> # Or load from config
        >>> resolver.load_aliases_from_tsconfig()
        >>>
        >>> # Resolve imports
        >>> result = resolver.resolve('src/app.ts', '@/utils/helpers')
        >>> print(result.path)  # 'src/utils/helpers.ts'
    """

    # Default extensions by language (in priority order)
    EXTENSIONS = {
        "default": ["", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".rb", ".java"],
        "typescript": ["", ".ts", ".tsx", ".d.ts", ".js", ".jsx"],
        "javascript": ["", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"],
        "python": ["", ".py", ".pyi"],
        "go": ["", ".go"],
        "rust": ["", ".rs"],
    }

    # Implicit index files by language
    INDEX_FILES = {
        "default": ["index.ts", "index.tsx", "index.js", "index.jsx", "__init__.py", "mod.rs"],
        "typescript": ["index.ts", "index.tsx", "index.d.ts", "index.js"],
        "javascript": ["index.js", "index.jsx", "index.mjs", "index.ts"],
        "python": ["__init__.py", "__init__.pyi"],
        "go": [],  # Go doesn't have index files
        "rust": ["mod.rs"],
    }

    # Directories to skip
    IGNORED_DIRS = {
        "node_modules",
        "__pycache__",
        ".git",
        ".svn",
        "venv",
        "env",
        ".venv",
        "dist",
        "build",
        ".next",
        "coverage",
        "vendor",
        "target",
    }

    def __init__(
        self,
        root: str,
        aliases: Dict[str, List[str]] = None,
        base_url: str = "",
    ):
        """Initialize the import resolver.

        Args:
            root: Path to project root directory.
            aliases: Initial alias mappings {pattern: [targets]}.
            base_url: Base URL for non-absolute alias targets.

        Raises:
            ValueError: If root path doesn't exist.
        """
        self.root = Path(root).resolve()
        if not self.root.exists():
            raise ValueError(f"Root path does not exist: {self.root}")

        self.base_url = base_url
        self.aliases: List[AliasConfig] = []
        self.file_index: Dict[str, Set[str]] = {}
        self.module_name = ""
        self._index_built = False

        # Add initial aliases
        if aliases:
            for pattern, targets in aliases.items():
                self.add_alias(pattern, targets)

    def add_alias(self, pattern: str, targets: Union[str, List[str]]) -> "ImportResolver":
        """Add a path alias configuration.

        Args:
            pattern: Alias pattern (e.g., "@/*", "~/", "#components/*").
            targets: Target path(s) to resolve to.

        Returns:
            self, for method chaining.

        Example:
            >>> resolver.add_alias("@/*", ["src/*"])
            >>> resolver.add_alias("~/", "src/")
            >>> resolver.add_alias("#components/*", ["src/components/*", "shared/components/*"])
        """
        if isinstance(targets, str):
            targets = [targets]

        # Apply base_url to non-absolute targets
        resolved_targets = []
        for target in targets:
            if self.base_url and not os.path.isabs(target) and not target.startswith("."):
                target = os.path.join(self.base_url, target)
            resolved_targets.append(target)

        self.aliases.append(AliasConfig(pattern=pattern, targets=resolved_targets))
        return self

    def clear_aliases(self) -> "ImportResolver":
        """Remove all configured aliases."""
        self.aliases.clear()
        return self

    def load_aliases_from_tsconfig(self, config_path: str = None) -> "ImportResolver":
        """Load path aliases from tsconfig.json or jsconfig.json.

        Automatically detects and loads configuration, including handling
        the "extends" directive for inherited configs.

        Args:
            config_path: Explicit path to config file (auto-detected if None).

        Returns:
            self, for method chaining.
        """
        if config_path:
            config_paths = [Path(config_path)]
        else:
            config_paths = [
                self.root / "tsconfig.json",
                self.root / "jsconfig.json",
            ]

        for path in config_paths:
            if path.exists():
                aliases, base_url = self._parse_tsconfig(path)
                if base_url:
                    self.base_url = base_url
                for pattern, targets in aliases.items():
                    self.add_alias(pattern, targets)
                break

        return self

    def _parse_tsconfig(
        self, config_path: Path, seen: Set[str] = None
    ) -> Tuple[Dict[str, List[str]], str]:
        """Parse tsconfig.json, following extends directive.

        Args:
            config_path: Path to the config file.
            seen: Set of already-parsed paths (prevents cycles).

        Returns:
            Tuple of (paths dict, baseUrl string).
        """
        if seen is None:
            seen = set()

        config_str = str(config_path.resolve())
        if config_str in seen:
            return {}, ""
        seen.add(config_str)

        try:
            # Read and parse JSON (with comment stripping)
            content = config_path.read_text(encoding="utf-8")
            # Remove single-line comments
            content = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
            # Remove multi-line comments
            content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
            config = json.loads(content)
        except (json.JSONDecodeError, OSError):
            return {}, ""

        compiler_options = config.get("compilerOptions", {})
        paths = compiler_options.get("paths", {})
        base_url = compiler_options.get("baseUrl", "")

        # Handle extends
        extends = config.get("extends")
        if extends:
            parent_path = Path(extends)
            if not parent_path.is_absolute():
                parent_path = config_path.parent / extends
            if not parent_path.suffix:
                parent_path = parent_path.with_suffix(".json")

            parent_paths, parent_base = self._parse_tsconfig(parent_path, seen)

            # Merge: child overrides parent
            merged_paths = dict(parent_paths)
            merged_paths.update(paths)
            paths = merged_paths

            if not base_url:
                base_url = parent_base

        return paths, base_url

    def load_aliases_from_pyproject(self, config_path: str = None) -> "ImportResolver":
        """Load path aliases from pyproject.toml [tool.import_resolver] section.

        Expected format in pyproject.toml:
            [tool.import_resolver]
            aliases = { "@" = ["src"], "~" = ["lib"] }

        Args:
            config_path: Explicit path (defaults to root/pyproject.toml).

        Returns:
            self, for method chaining.
        """
        path = Path(config_path) if config_path else self.root / "pyproject.toml"

        if not path.exists():
            return self

        try:
            # Simple TOML parsing for the section we care about
            content = path.read_text(encoding="utf-8")

            # Try to import tomllib (Python 3.11+) or toml
            try:
                import tomllib

                data = tomllib.loads(content)
            except ImportError:
                try:
                    import toml

                    data = toml.loads(content)
                except ImportError:
                    # Fallback: regex parsing for simple cases
                    data = self._simple_toml_parse(content)

            resolver_config = data.get("tool", {}).get("import_resolver", {})
            aliases = resolver_config.get("aliases", {})

            for pattern, targets in aliases.items():
                if isinstance(targets, str):
                    targets = [targets]
                self.add_alias(pattern, targets)

            self.base_url = resolver_config.get("base_url", self.base_url)

        except Exception:
            pass

        return self

    def _simple_toml_parse(self, content: str) -> Dict[str, Any]:
        """Minimal TOML parser for import_resolver config."""
        # This is a very basic parser for the specific section we need
        result: Dict[str, Any] = {"tool": {"import_resolver": {"aliases": {}}}}

        in_section = False
        for line in content.split("\n"):
            line = line.strip()
            if line == "[tool.import_resolver]":
                in_section = True
            elif line.startswith("[") and in_section:
                break
            elif in_section and "=" in line:
                # Parse key = value
                key, value = line.split("=", 1)
                key = key.strip().strip('"')
                value = value.strip()
                # Very basic value parsing
                if value.startswith("["):
                    # Array
                    items = re.findall(r'"([^"]*)"', value)
                    result["tool"]["import_resolver"]["aliases"][key] = items
                elif value.startswith('"'):
                    result["tool"]["import_resolver"]["aliases"][key] = [value.strip('"')]

        return result

    def build_index(self, languages: List[str] = None) -> "ImportResolver":
        """Build file index for fast lookups.

        Args:
            languages: Languages to include (None = all).

        Returns:
            self, for method chaining.
        """
        self.file_index = {
            "exact": set(),  # All file paths
            "no_ext": {},  # path without extension -> paths
            "suffix": {},  # path suffix -> paths
            "dir": {},  # directory -> files
            "basename": {},  # filename without dir -> paths
        }

        # Determine extensions to look for
        if languages:
            extensions = set()
            for lang in languages:
                extensions.update(self.EXTENSIONS.get(lang, self.EXTENSIONS["default"]))
        else:
            extensions = set()
            for exts in self.EXTENSIONS.values():
                extensions.update(exts)
        extensions.discard("")

        # Detect module name
        self.module_name = self._detect_module_name()

        # Walk directory tree
        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter ignored directories
            dirnames[:] = [d for d in dirnames if d not in self.IGNORED_DIRS]

            for filename in filenames:
                ext = Path(filename).suffix
                if ext not in extensions:
                    continue

                full_path = Path(dirpath) / filename
                rel_path = str(full_path.relative_to(self.root))

                # Index by exact path
                self.file_index["exact"].add(rel_path)

                # Index by path without extension
                no_ext = str(Path(rel_path).with_suffix(""))
                if no_ext not in self.file_index["no_ext"]:
                    self.file_index["no_ext"][no_ext] = set()
                self.file_index["no_ext"][no_ext].add(rel_path)

                # Index by basename
                basename = Path(rel_path).stem
                if basename not in self.file_index["basename"]:
                    self.file_index["basename"][basename] = set()
                self.file_index["basename"][basename].add(rel_path)

                # Index by directory
                dir_path = str(Path(rel_path).parent)
                if dir_path not in self.file_index["dir"]:
                    self.file_index["dir"][dir_path] = set()
                self.file_index["dir"][dir_path].add(rel_path)

                # Index by all suffixes
                parts = Path(rel_path).parts
                for i in range(1, len(parts)):
                    suffix = str(Path(*parts[i:]))
                    if suffix not in self.file_index["suffix"]:
                        self.file_index["suffix"][suffix] = set()
                    self.file_index["suffix"][suffix].add(rel_path)

                    # Also without extension
                    suffix_no_ext = str(Path(*parts[i:]).with_suffix(""))
                    if suffix_no_ext not in self.file_index["suffix"]:
                        self.file_index["suffix"][suffix_no_ext] = set()
                    self.file_index["suffix"][suffix_no_ext].add(rel_path)

        self._index_built = True
        return self

    def _detect_module_name(self) -> str:
        """Detect project module/package name."""
        # Go module
        go_mod = self.root / "go.mod"
        if go_mod.exists():
            try:
                for line in go_mod.read_text().splitlines():
                    if line.startswith("module "):
                        return line.split()[1]
            except Exception:
                pass

        # Python package
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1).replace("-", "_")
            except Exception:
                pass

        # Node package
        package_json = self.root / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                return data.get("name", "")
            except Exception:
                pass

        return self.root.name

    def resolve(
        self,
        source_file: str,
        import_string: str,
        language: str = None,
    ) -> ResolveResult:
        """Resolve an import string to an actual file path.

        This is the main entry point for import resolution. It tries multiple
        strategies in order until one succeeds.

        Args:
            source_file: Path to the file containing the import (relative to root).
            import_string: The import string to resolve.
            language: Source language (auto-detected if None).

        Returns:
            ResolveResult with the resolved path and metadata.

        Example:
            >>> result = resolver.resolve('src/app.ts', '@/utils/helpers')
            >>> if result.found:
            ...     print(f"Resolved to: {result.path}")
            ...     print(f"Strategy: {result.strategy.value}")
        """
        if not self._index_built:
            self.build_index()

        # Detect language if not provided
        if language is None:
            language = self._detect_language(source_file)

        # Normalize the import
        normalized = self._normalize_import(import_string, language)
        source_dir = str(Path(source_file).parent)
        if source_dir == ".":
            source_dir = ""

        candidates = []

        # Strategy 1: Relative imports (./foo, ../bar)
        if import_string.startswith("."):
            result = self._resolve_relative(import_string, source_dir, language)
            if result.found:
                return result
            candidates.extend(result.candidates)

        # Strategy 2: Configured aliases
        for alias in self.aliases:
            wildcard = alias.matches(import_string)
            if wildcard is not None:
                for target in alias.apply(wildcard):
                    result = self._try_resolve_path(target, language)
                    if result.found:
                        result.strategy = ResolveStrategy.ALIAS
                        result.original_import = import_string
                        return result
                    candidates.extend(result.candidates)

        # Strategy 3: Module prefix (e.g., "mypackage/utils" for Go/Python)
        if self.module_name and import_string.startswith(self.module_name):
            rest = import_string[len(self.module_name) :].lstrip("/.")
            result = self._try_resolve_path(rest, language)
            if result.found:
                result.strategy = ResolveStrategy.MODULE
                result.original_import = import_string
                return result
            candidates.extend(result.candidates)

        # Strategy 4: Exact match
        result = self._try_resolve_path(normalized, language)
        if result.found:
            result.strategy = ResolveStrategy.EXACT
            result.original_import = import_string
            return result
        candidates.extend(result.candidates)

        # Strategy 5: Suffix match (for nested packages)
        result = self._resolve_suffix(normalized, language)
        if result.found:
            result.original_import = import_string
            return result
        candidates.extend(result.candidates)

        # Not found
        return ResolveResult(
            path=None,
            strategy=ResolveStrategy.NOT_FOUND,
            candidates=list(set(candidates)),
            original_import=import_string,
            confidence=0.0,
        )

    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = Path(file_path).suffix.lower()
        mapping = {
            ".ts": "typescript",
            ".tsx": "typescript",
            ".d.ts": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".mjs": "javascript",
            ".py": "python",
            ".pyi": "python",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".java": "java",
        }
        return mapping.get(ext, "default")

    def _normalize_import(self, import_string: str, language: str) -> str:
        """Convert import syntax to path-like format."""
        imp = import_string.strip("\"'`")

        # Python dots to slashes: app.core.config -> app/core/config
        if language == "python" and "." in imp and "/" not in imp:
            if not imp.startswith("."):
                imp = imp.replace(".", "/")

        # Rust :: to slashes
        if language == "rust":
            if imp.startswith("crate::"):
                imp = imp[7:].replace("::", "/")
            elif imp.startswith("super::"):
                imp = imp.replace("::", "/")
            elif "::" in imp:
                imp = imp.replace("::", "/")

        # Go: module/package/file -> package/file
        if language == "go" and self.module_name:
            if imp.startswith(self.module_name + "/"):
                imp = imp[len(self.module_name) + 1 :]

        return imp

    def _resolve_relative(
        self, import_string: str, source_dir: str, language: str
    ) -> ResolveResult:
        """Resolve relative imports (./foo, ../bar)."""
        # Count parent levels
        levels = 0
        rest = import_string
        while rest.startswith("../"):
            levels += 1
            rest = rest[3:]
        rest = rest.lstrip("./")

        # Navigate up
        target_dir = Path(source_dir)
        for _ in range(levels):
            target_dir = target_dir.parent

        # Build candidate path
        if str(target_dir) == ".":
            candidate = rest
        else:
            candidate = str(target_dir / rest)

        result = self._try_resolve_path(candidate, language)
        if result.found:
            result.strategy = ResolveStrategy.RELATIVE
        return result

    def _try_resolve_path(self, path: str, language: str) -> ResolveResult:
        """Try to resolve a path with extensions and index files."""
        candidates = []
        extensions = self.EXTENSIONS.get(language, self.EXTENSIONS["default"])
        index_files = self.INDEX_FILES.get(language, self.INDEX_FILES["default"])

        # Try exact match first
        if path in self.file_index["exact"]:
            return ResolveResult(
                path=path,
                strategy=ResolveStrategy.EXACT,
                candidates=[path],
            )

        # Try with extensions
        for ext in extensions:
            if not ext:
                continue
            candidate = path + ext
            candidates.append(candidate)
            if candidate in self.file_index["exact"]:
                return ResolveResult(
                    path=candidate,
                    strategy=ResolveStrategy.EXACT,
                    candidates=candidates,
                )

        # Try without extension lookup
        if path in self.file_index["no_ext"]:
            matches = self.file_index["no_ext"][path]
            if len(matches) == 1:
                return ResolveResult(
                    path=list(matches)[0],
                    strategy=ResolveStrategy.EXACT,
                    candidates=candidates,
                )

        # Try index files (path is a directory)
        for index_file in index_files:
            candidate = str(Path(path) / index_file)
            candidates.append(candidate)
            if candidate in self.file_index["exact"]:
                return ResolveResult(
                    path=candidate,
                    strategy=ResolveStrategy.INDEX,
                    candidates=candidates,
                )

        return ResolveResult(
            path=None,
            strategy=ResolveStrategy.NOT_FOUND,
            candidates=candidates,
        )

    def _resolve_suffix(self, normalized: str, language: str) -> ResolveResult:
        """Resolve by matching path suffix."""
        extensions = self.EXTENSIONS.get(language, self.EXTENSIONS["default"])
        candidates = []

        for ext in extensions:
            candidate = normalized + ext if ext else normalized
            candidates.append(candidate)

            if candidate in self.file_index["suffix"]:
                matches = self.file_index["suffix"][candidate]
                if len(matches) == 1:
                    return ResolveResult(
                        path=list(matches)[0],
                        strategy=ResolveStrategy.SUFFIX,
                        candidates=candidates,
                    )

        # Try __init__.py for Python packages
        if language == "python":
            init_candidate = str(Path(normalized) / "__init__.py")
            candidates.append(init_candidate)
            if init_candidate in self.file_index["suffix"]:
                matches = self.file_index["suffix"][init_candidate]
                if len(matches) == 1:
                    return ResolveResult(
                        path=list(matches)[0],
                        strategy=ResolveStrategy.SUFFIX,
                        candidates=candidates,
                    )

        return ResolveResult(
            path=None,
            strategy=ResolveStrategy.NOT_FOUND,
            candidates=candidates,
        )

    def resolve_all(
        self,
        source_file: str,
        imports: List[str],
        language: str = None,
    ) -> Dict[str, ResolveResult]:
        """Resolve multiple imports at once.

        Args:
            source_file: Source file path.
            imports: List of import strings.
            language: Source language.

        Returns:
            Dict mapping import strings to ResolveResults.
        """
        return {imp: self.resolve(source_file, imp, language) for imp in imports}


# Convenience function for simple use cases
def resolve_import_path(
    source_file: str,
    import_string: str,
    root_dir: str,
    aliases: Dict[str, List[str]] = None,
    base_url: str = "",
) -> Optional[str]:
    """Resolve an import path to an actual file.

    This is a convenience function for simple use cases. For repeated
    resolutions, use ImportResolver directly for better performance.

    Args:
        source_file: Path to file containing the import (relative to root).
        import_string: The import string to resolve.
        root_dir: Project root directory.
        aliases: Optional alias configuration {pattern: [targets]}.
        base_url: Base URL for alias resolution.

    Returns:
        Resolved file path (relative to root), or None if not found.

    Example:
        >>> path = resolve_import_path(
        ...     'src/app.ts',
        ...     '@/utils/helpers',
        ...     '/my/project',
        ...     aliases={'@/*': ['src/*']},
        ... )
        >>> print(path)
        'src/utils/helpers.ts'
    """
    resolver = ImportResolver(root_dir, aliases=aliases, base_url=base_url)
    resolver.build_index()
    result = resolver.resolve(source_file, import_string)
    return result.path if result.found else None
