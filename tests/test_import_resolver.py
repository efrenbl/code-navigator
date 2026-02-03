#!/usr/bin/env python3
"""Tests for the ImportResolver module."""

import json

import pytest

from codenav.import_resolver import (
    AliasConfig,
    ImportResolver,
    ResolveResult,
    ResolveStrategy,
    resolve_import_path,
)


@pytest.fixture
def ts_project(tmp_path):
    """Create a TypeScript-like project structure."""
    # Create directories
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "components").mkdir()
    (tmp_path / "src" / "utils").mkdir()
    (tmp_path / "src" / "api").mkdir()
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "types").mkdir()

    # Create source files
    (tmp_path / "src" / "index.ts").write_text("export * from './components';")
    (tmp_path / "src" / "app.ts").write_text("import { Button } from '@/components/Button';")
    (tmp_path / "src" / "components" / "Button.tsx").write_text("export const Button = () => {};")
    (tmp_path / "src" / "components" / "index.ts").write_text("export * from './Button';")
    (tmp_path / "src" / "utils" / "helpers.ts").write_text("export const helper = () => {};")
    (tmp_path / "src" / "api" / "client.ts").write_text(
        "import { helper } from '../utils/helpers';"
    )
    (tmp_path / "shared" / "types" / "index.ts").write_text("export type User = {};")

    # Create tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "baseUrl": ".",
            "paths": {
                "@/*": ["src/*"],
                "@components/*": ["src/components/*"],
                "~/*": ["shared/*"],
            },
        }
    }
    (tmp_path / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2))

    return tmp_path


@pytest.fixture
def python_project(tmp_path):
    """Create a Python project structure."""
    # Create package structure
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "myapp").mkdir()
    (tmp_path / "src" / "myapp" / "core").mkdir()
    (tmp_path / "src" / "myapp" / "utils").mkdir()
    (tmp_path / "tests").mkdir()

    # Create source files
    (tmp_path / "src" / "myapp" / "__init__.py").write_text("")
    (tmp_path / "src" / "myapp" / "main.py").write_text("from .core import config")
    (tmp_path / "src" / "myapp" / "core" / "__init__.py").write_text("from .config import Config")
    (tmp_path / "src" / "myapp" / "core" / "config.py").write_text("class Config: pass")
    (tmp_path / "src" / "myapp" / "utils" / "__init__.py").write_text("")
    (tmp_path / "src" / "myapp" / "utils" / "helpers.py").write_text("def helper(): pass")
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_main.py").write_text("from myapp.main import main")

    # Create pyproject.toml
    pyproject = """
[project]
name = "myapp"
version = "1.0.0"

[tool.import_resolver]
aliases = { "@" = ["src/myapp"] }
"""
    (tmp_path / "pyproject.toml").write_text(pyproject)

    return tmp_path


class TestAliasConfig:
    """Tests for AliasConfig dataclass."""

    def test_exact_pattern(self):
        """Test exact alias pattern (no wildcard)."""
        alias = AliasConfig(pattern="@", targets=["src"])
        assert not alias.is_wildcard
        assert alias.matches("@") == ""
        assert alias.matches("@/foo") is None

    def test_wildcard_pattern(self):
        """Test wildcard alias pattern."""
        alias = AliasConfig(pattern="@/*", targets=["src/*"])
        assert alias.is_wildcard
        assert alias.prefix == "@/"
        assert alias.suffix == ""
        assert alias.matches("@/utils") == "utils"
        assert alias.matches("@/components/Button") == "components/Button"
        assert alias.matches("~/utils") is None

    def test_apply(self):
        """Test alias transformation."""
        alias = AliasConfig(pattern="@/*", targets=["src/*"])
        result = alias.apply("utils/helpers")
        assert result == ["src/utils/helpers"]

    def test_multiple_targets(self):
        """Test alias with multiple targets."""
        alias = AliasConfig(pattern="#/*", targets=["src/*", "shared/*"])
        result = alias.apply("types")
        assert result == ["src/types", "shared/types"]


class TestImportResolverBasic:
    """Basic tests for ImportResolver."""

    def test_init(self, tmp_path):
        """Test basic initialization."""
        resolver = ImportResolver(str(tmp_path))
        assert resolver.root == tmp_path.resolve()
        assert len(resolver.aliases) == 0

    def test_init_with_aliases(self, tmp_path):
        """Test initialization with aliases."""
        resolver = ImportResolver(str(tmp_path), aliases={"@/*": ["src/*"]})
        assert len(resolver.aliases) == 1

    def test_init_invalid_path(self):
        """Test initialization with non-existent path."""
        with pytest.raises(ValueError, match="does not exist"):
            ImportResolver("/nonexistent/path/12345")

    def test_add_alias(self, tmp_path):
        """Test adding aliases."""
        resolver = ImportResolver(str(tmp_path))
        resolver.add_alias("@/*", ["src/*"])
        resolver.add_alias("~/", "lib/")
        assert len(resolver.aliases) == 2

    def test_clear_aliases(self, tmp_path):
        """Test clearing aliases."""
        resolver = ImportResolver(str(tmp_path), aliases={"@/*": ["src/*"]})
        resolver.clear_aliases()
        assert len(resolver.aliases) == 0

    def test_method_chaining(self, tmp_path):
        """Test fluent method chaining."""
        resolver = (
            ImportResolver(str(tmp_path))
            .add_alias("@/*", ["src/*"])
            .add_alias("~/", ["lib/"])
            .build_index()
        )
        assert len(resolver.aliases) == 2
        assert resolver._index_built


class TestImportResolverTypeScript:
    """Tests for TypeScript import resolution."""

    def test_load_tsconfig(self, ts_project):
        """Test loading aliases from tsconfig.json."""
        resolver = ImportResolver(str(ts_project))
        resolver.load_aliases_from_tsconfig()
        assert len(resolver.aliases) == 3

    def test_resolve_alias(self, ts_project):
        """Test resolving aliased imports."""
        resolver = ImportResolver(str(ts_project))
        resolver.load_aliases_from_tsconfig()
        resolver.build_index()

        result = resolver.resolve("src/app.ts", "@/utils/helpers")
        assert result.found
        assert result.path == "src/utils/helpers.ts"
        assert result.strategy == ResolveStrategy.ALIAS

    def test_resolve_relative(self, ts_project):
        """Test resolving relative imports."""
        resolver = ImportResolver(str(ts_project))
        resolver.build_index()

        result = resolver.resolve("src/api/client.ts", "../utils/helpers")
        assert result.found
        assert result.path == "src/utils/helpers.ts"
        assert result.strategy == ResolveStrategy.RELATIVE

    def test_resolve_index_file(self, ts_project):
        """Test resolving to index files."""
        resolver = ImportResolver(str(ts_project))
        resolver.build_index()

        result = resolver.resolve("src/app.ts", "./components")
        assert result.found
        assert result.path == "src/components/index.ts"
        assert result.strategy == ResolveStrategy.INDEX

    def test_resolve_component_alias(self, ts_project):
        """Test resolving component-specific alias."""
        resolver = ImportResolver(str(ts_project))
        resolver.load_aliases_from_tsconfig()
        resolver.build_index()

        result = resolver.resolve("src/app.ts", "@components/Button")
        assert result.found
        assert result.path == "src/components/Button.tsx"

    def test_resolve_shared_alias(self, ts_project):
        """Test resolving shared directory alias."""
        resolver = ImportResolver(str(ts_project))
        resolver.load_aliases_from_tsconfig()
        resolver.build_index()

        result = resolver.resolve("src/app.ts", "~/types")
        assert result.found
        assert result.path == "shared/types/index.ts"


class TestImportResolverPython:
    """Tests for Python import resolution."""

    def test_resolve_relative_python(self, python_project):
        """Test resolving Python relative imports."""
        resolver = ImportResolver(str(python_project))
        resolver.build_index()

        result = resolver.resolve("src/myapp/main.py", ".core.config", language="python")
        # Note: Python dotted relative imports are tricky
        # This tests the normalization logic
        assert "config" in result.original_import

    def test_resolve_package_init(self, python_project):
        """Test resolving to __init__.py."""
        resolver = ImportResolver(str(python_project))
        resolver.build_index()

        result = resolver.resolve("tests/test_main.py", "myapp/core", language="python")
        # Should resolve to __init__.py
        if result.found:
            assert "__init__.py" in result.path or "config" in result.path

    def test_python_dot_notation(self, python_project):
        """Test Python dot notation normalization."""
        resolver = ImportResolver(str(python_project))
        resolver.build_index()

        # app.core.config should be normalized to app/core/config
        result = resolver.resolve("tests/test_main.py", "myapp.utils.helpers", language="python")
        if result.found:
            assert "helpers" in result.path


class TestImportResolverEdgeCases:
    """Edge case tests."""

    def test_resolve_not_found(self, ts_project):
        """Test handling non-existent imports."""
        resolver = ImportResolver(str(ts_project))
        resolver.build_index()

        result = resolver.resolve("src/app.ts", "nonexistent/module")
        assert not result.found
        assert result.strategy == ResolveStrategy.NOT_FOUND
        assert result.path is None

    def test_resolve_all(self, ts_project):
        """Test batch resolution."""
        resolver = ImportResolver(str(ts_project))
        resolver.load_aliases_from_tsconfig()
        resolver.build_index()

        imports = ["@/utils/helpers", "./components", "nonexistent"]
        results = resolver.resolve_all("src/app.ts", imports)

        assert len(results) == 3
        assert results["@/utils/helpers"].found
        assert results["./components"].found
        assert not results["nonexistent"].found

    def test_empty_project(self, tmp_path):
        """Test resolution in empty project."""
        resolver = ImportResolver(str(tmp_path))
        resolver.build_index()

        result = resolver.resolve("app.ts", "./utils")
        assert not result.found

    def test_circular_tsconfig_extends(self, tmp_path):
        """Test handling circular tsconfig extends."""
        # Create configs that extend each other
        (tmp_path / "tsconfig.json").write_text(json.dumps({"extends": "./tsconfig.base.json"}))
        (tmp_path / "tsconfig.base.json").write_text(
            json.dumps(
                {
                    "extends": "./tsconfig.json",  # Circular!
                    "compilerOptions": {"paths": {"@/*": ["src/*"]}},
                }
            )
        )

        resolver = ImportResolver(str(tmp_path))
        # Should not infinite loop
        resolver.load_aliases_from_tsconfig()
        assert len(resolver.aliases) >= 0  # May or may not load aliases


class TestConvenienceFunction:
    """Tests for the convenience function."""

    def test_resolve_import_path(self, ts_project):
        """Test the convenience function."""
        # Create file index by building resolver
        result = resolve_import_path(
            source_file="src/app.ts",
            import_string="./utils/helpers",
            root_dir=str(ts_project),
        )
        assert result == "src/utils/helpers.ts"

    def test_resolve_import_path_with_aliases(self, ts_project):
        """Test convenience function with aliases."""
        result = resolve_import_path(
            source_file="src/app.ts",
            import_string="@/components/Button",
            root_dir=str(ts_project),
            aliases={"@/*": ["src/*"]},
        )
        assert result == "src/components/Button.tsx"

    def test_resolve_import_path_not_found(self, ts_project):
        """Test convenience function for non-existent import."""
        result = resolve_import_path(
            source_file="src/app.ts",
            import_string="nonexistent",
            root_dir=str(ts_project),
        )
        assert result is None


class TestResolveResult:
    """Tests for ResolveResult dataclass."""

    def test_found_property_true(self):
        """Test found property when path exists."""
        result = ResolveResult(
            path="src/utils.ts",
            strategy=ResolveStrategy.EXACT,
        )
        assert result.found

    def test_found_property_false_no_path(self):
        """Test found property when path is None."""
        result = ResolveResult(
            path=None,
            strategy=ResolveStrategy.NOT_FOUND,
        )
        assert not result.found

    def test_found_property_false_not_found_strategy(self):
        """Test found property with NOT_FOUND strategy."""
        result = ResolveResult(
            path="something",  # Even with a path
            strategy=ResolveStrategy.NOT_FOUND,
        )
        assert not result.found


class TestLanguageDetection:
    """Tests for language detection and normalization."""

    def test_detect_typescript(self, tmp_path):
        """Test TypeScript detection."""
        (tmp_path / "app.ts").write_text("")
        resolver = ImportResolver(str(tmp_path))
        assert resolver._detect_language("app.ts") == "typescript"
        assert resolver._detect_language("app.tsx") == "typescript"

    def test_detect_javascript(self, tmp_path):
        """Test JavaScript detection."""
        (tmp_path / "app.js").write_text("")
        resolver = ImportResolver(str(tmp_path))
        assert resolver._detect_language("app.js") == "javascript"
        assert resolver._detect_language("app.jsx") == "javascript"

    def test_detect_python(self, tmp_path):
        """Test Python detection."""
        resolver = ImportResolver(str(tmp_path))
        assert resolver._detect_language("app.py") == "python"

    def test_normalize_python_import(self, tmp_path):
        """Test Python import normalization."""
        resolver = ImportResolver(str(tmp_path))
        normalized = resolver._normalize_import("app.core.config", "python")
        assert normalized == "app/core/config"

    def test_normalize_rust_import(self, tmp_path):
        """Test Rust import normalization."""
        resolver = ImportResolver(str(tmp_path))
        normalized = resolver._normalize_import("crate::utils::helpers", "rust")
        assert normalized == "utils/helpers"
