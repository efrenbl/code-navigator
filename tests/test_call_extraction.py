"""Tests for call/dependency extraction in the tree-sitter analyzers.

Each analyzer populates Symbol.dependencies with the callee names found in a
function/method body (mirroring the Python analyzer). These assertions need the
relevant grammar; they skip when it is not installed.
"""

import pytest

from codenav.dart_analyzer import TREE_SITTER_AVAILABLE as DART_TS
from codenav.dart_analyzer import DartAnalyzer
from codenav.go_analyzer import TREE_SITTER_AVAILABLE as GO_TS
from codenav.go_analyzer import GoAnalyzer
from codenav.js_ts_analyzer import TREE_SITTER_AVAILABLE as JS_TS
from codenav.js_ts_analyzer import JavaScriptAnalyzer, TypeScriptAnalyzer
from codenav.rust_analyzer import TREE_SITTER_AVAILABLE as RUST_TS
from codenav.rust_analyzer import RustAnalyzer


def _deps(symbols, name):
    for s in symbols:
        if s.name == name:
            return set(s.dependencies or [])
    raise AssertionError(f"symbol {name!r} not found")


@pytest.mark.skipif(not JS_TS, reason="tree-sitter JS grammar not installed")
class TestJavaScriptCalls:
    def test_function_calls(self):
        src = "function f() { foo(); obj.bar(1); }"
        syms = JavaScriptAnalyzer("a.js", src).analyze()
        assert _deps(syms, "f") == {"foo", "bar"}

    def test_arrow_function_calls(self):
        src = "const g = () => { baz(); qux(); };"
        syms = JavaScriptAnalyzer("a.js", src).analyze()
        assert _deps(syms, "g") == {"baz", "qux"}

    def test_method_calls_member_access(self):
        src = "class C { m() { this.helper(); compute(2); } }"
        syms = TypeScriptAnalyzer("a.ts", src).analyze()
        assert _deps(syms, "m") == {"helper", "compute"}

    def test_no_calls_is_empty(self):
        syms = JavaScriptAnalyzer("a.js", "function f() { return 1; }").analyze()
        assert _deps(syms, "f") == set()


@pytest.mark.skipif(not GO_TS, reason="tree-sitter Go grammar not installed")
class TestGoCalls:
    def test_function_and_package_calls(self):
        src = "package p\nfunc f() { foo(); pkg.Bar() }\n"
        syms = GoAnalyzer("a.go", src).analyze()
        assert _deps(syms, "f") == {"foo", "Bar"}

    def test_method_receiver_calls(self):
        src = "package p\nfunc (u *User) M() { u.save(); log.Print() }\n"
        syms = GoAnalyzer("a.go", src).analyze()
        assert _deps(syms, "M") == {"save", "Print"}


@pytest.mark.skipif(not RUST_TS, reason="tree-sitter Rust grammar not installed")
class TestRustCalls:
    def test_function_calls_including_macro(self):
        src = 'fn f() { foo(); m::bar(); x.run(); println!("hi"); }\n'
        syms = RustAnalyzer("a.rs", src).analyze()
        assert _deps(syms, "f") == {"foo", "bar", "run", "println"}

    def test_impl_method_calls(self):
        src = "struct S;\nimpl S { fn g(&self) { self.h(); } }\n"
        syms = RustAnalyzer("a.rs", src).analyze()
        assert _deps(syms, "g") == {"h"}


@pytest.mark.skipif(not DART_TS, reason="tree-sitter Dart grammar not installed")
class TestDartCalls:
    def test_method_and_member_calls(self):
        src = "class A { void build() { helper(); ctx.draw(2); } }"
        syms = DartAnalyzer("a.dart", src).analyze()
        assert _deps(syms, "build") == {"helper", "draw"}

    def test_arrow_body_function_calls(self):
        src = "int top() => compute();"
        syms = DartAnalyzer("a.dart", src).analyze()
        assert _deps(syms, "top") == {"compute"}


@pytest.mark.skipif(not JS_TS, reason="tree-sitter JS grammar not installed")
def test_dependencies_surface_in_code_map(tmp_path):
    """End-to-end: deps reach the generated .codenav.json (deps field)."""
    from codenav.code_navigator import CodeNavigator

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "a.js").write_text("function caller() { callee(); }\nfunction callee() {}\n")
    result = CodeNavigator(str(proj)).scan()
    syms = result["files"]["a.js"]["symbols"]
    caller = next(s for s in syms if s["name"] == "caller")
    assert "callee" in (caller["deps"] or [])
