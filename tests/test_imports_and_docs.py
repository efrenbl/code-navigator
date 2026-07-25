"""Tests for per-language import extraction, doc comments, and Python parity.

Covers the v0.2.0 additions: raw import specifiers on each tree-sitter analyzer,
Go/Rust/Ruby/Dart doc comments, and the Python enum/constant/nested-function
handling. Grammar-dependent assertions skip when the grammar is unavailable.
"""

import pytest

from codenav.code_navigator import PythonAnalyzer
from codenav.dart_analyzer import TREE_SITTER_AVAILABLE as DART_TS
from codenav.dart_analyzer import DartAnalyzer
from codenav.go_analyzer import TREE_SITTER_AVAILABLE as GO_TS
from codenav.go_analyzer import GoAnalyzer
from codenav.js_ts_analyzer import TREE_SITTER_AVAILABLE as JS_TS
from codenav.js_ts_analyzer import JavaScriptAnalyzer
from codenav.ruby_analyzer import TREE_SITTER_AVAILABLE as RUBY_TS
from codenav.ruby_analyzer import RubyAnalyzer
from codenav.rust_analyzer import TREE_SITTER_AVAILABLE as RUST_TS
from codenav.rust_analyzer import RustAnalyzer


def _sym(symbols, name):
    for s in symbols:
        if s.name == name:
            return s
    raise AssertionError(f"symbol {name!r} not found")


class TestImports:
    @pytest.mark.skipif(not JS_TS, reason="tree-sitter JS grammar not installed")
    def test_js_import_and_require(self):
        src = 'import {a} from "./mod";\nconst b = require("pkg");\n'
        an = JavaScriptAnalyzer("a.js", src)
        an.analyze()
        assert set(an.imports) == {"./mod", "pkg"}

    @pytest.mark.skipif(not GO_TS, reason="tree-sitter Go grammar not installed")
    def test_go_imports_single_and_block(self):
        src = 'package p\nimport "fmt"\nimport (\n  "os"\n  m "math"\n)\n'
        an = GoAnalyzer("a.go", src)
        an.analyze()
        assert set(an.imports) == {"fmt", "os", "math"}

    @pytest.mark.skipif(not RUST_TS, reason="tree-sitter Rust grammar not installed")
    def test_rust_use_declarations(self):
        src = "use std::collections::HashMap;\nuse crate::foo::Bar;\n"
        an = RustAnalyzer("a.rs", src)
        an.analyze()
        assert set(an.imports) == {"std::collections::HashMap", "crate::foo::Bar"}

    @pytest.mark.skipif(not RUBY_TS, reason="tree-sitter Ruby grammar not installed")
    def test_ruby_require(self):
        src = 'require "json"\nrequire_relative "./foo"\n'
        an = RubyAnalyzer("a.rb", src)
        an.analyze()
        assert set(an.imports) == {"json", "./foo"}

    @pytest.mark.skipif(not DART_TS, reason="tree-sitter Dart grammar not installed")
    def test_dart_imports(self):
        src = "import 'dart:async';\nimport './local.dart';\n"
        an = DartAnalyzer("a.dart", src)
        an.analyze()
        assert set(an.imports) == {"dart:async", "./local.dart"}


class TestImportResolution:
    def test_python_from_import_resolves_to_module_file(self, tmp_path):
        """``from models import User`` (recorded as ``models.User``) resolves to
        the module file via the dotted-prefix retry."""
        from codenav.code_navigator import CodeNavigator

        proj = tmp_path / "p"
        proj.mkdir()
        (proj / "models.py").write_text("class User:\n    pass\n")
        (proj / "service.py").write_text(
            "from models import User\n\n\ndef run():\n    return User\n"
        )
        code_map = CodeNavigator(str(proj)).scan()
        assert code_map["files"]["service.py"]["imports"] == ["models.py"]

    def test_external_import_is_omitted(self, tmp_path):
        """Third-party imports that resolve to no repo file are dropped."""
        from codenav.code_navigator import CodeNavigator

        proj = tmp_path / "p"
        proj.mkdir()
        (proj / "a.py").write_text("import os\nimport requests\n")
        code_map = CodeNavigator(str(proj)).scan()
        assert code_map["files"]["a.py"]["imports"] == []


class TestDocComments:
    @pytest.mark.skipif(not GO_TS, reason="tree-sitter Go grammar not installed")
    def test_go_doc_comment(self):
        src = "package p\n// Greet greets.\n// second line.\nfunc Greet() {}\n"
        syms = GoAnalyzer("a.go", src).analyze()
        assert _sym(syms, "Greet").docstring == "Greet greets.\nsecond line."

    @pytest.mark.skipif(not RUST_TS, reason="tree-sitter Rust grammar not installed")
    def test_rust_doc_comment_ignores_plain_and_inner(self):
        src = "//! inner\n// plain\n/// real doc\nstruct Point { x: i32 }\n"
        syms = RustAnalyzer("a.rs", src).analyze()
        assert _sym(syms, "Point").docstring == "real doc"

    @pytest.mark.skipif(not RUBY_TS, reason="tree-sitter Ruby grammar not installed")
    def test_ruby_doc_comment(self):
        src = "# Dog class doc\nclass Dog\n  # bark doc\n  def bark\n    x()\n  end\nend\n"
        syms = RubyAnalyzer("a.rb", src).analyze()
        assert _sym(syms, "Dog").docstring == "Dog class doc"
        assert _sym(syms, "bark").docstring == "bark doc"

    @pytest.mark.skipif(not DART_TS, reason="tree-sitter Dart grammar not installed")
    def test_dart_doc_comment(self):
        src = "/// A greeter.\nclass Greeter {\n  /// greet doc\n  void greet() { x(); }\n}\n"
        syms = DartAnalyzer("a.dart", src).analyze()
        assert _sym(syms, "Greeter").docstring == "A greeter."
        assert _sym(syms, "greet").docstring == "greet doc"


class TestPythonParity:
    def test_enum_detection(self):
        src = "from enum import Enum\nclass Color(Enum):\n    RED = 1\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        assert _sym(syms, "Color").type == "enum"

    def test_intenum_detection(self):
        src = "import enum\nclass Level(enum.IntEnum):\n    LOW = 1\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        assert _sym(syms, "Level").type == "enum"

    def test_plain_class_not_enum(self):
        src = "class Plain:\n    pass\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        assert _sym(syms, "Plain").type == "class"

    def test_module_constants(self):
        src = "MAX_SIZE = 100\nDEFAULT: int = 5\nlowercase = 3\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        constants = {s.name for s in syms if s.type == "constant"}
        assert constants == {"MAX_SIZE", "DEFAULT"}

    def test_constant_not_inside_function(self):
        src = "def f():\n    LOCAL = 1\n    return LOCAL\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        assert not any(s.type == "constant" for s in syms)

    def test_nested_function_parent_is_function(self):
        src = "def outer():\n    def inner():\n        pass\n    return inner\n"
        syms = PythonAnalyzer("a.py", src).analyze()
        assert _sym(syms, "inner").parent == "outer"
        assert _sym(syms, "outer").parent is None

    def test_method_parent_is_class_not_outer_function(self):
        src = (
            "def factory():\n"
            "    class Inner:\n"
            "        def method(self):\n"
            "            pass\n"
            "    return Inner\n"
        )
        syms = PythonAnalyzer("a.py", src).analyze()
        assert _sym(syms, "method").parent == "Inner"
