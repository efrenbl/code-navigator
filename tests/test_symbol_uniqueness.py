"""Regression tests: no analyzer may emit duplicate symbols, and multi-byte
characters before a symbol must not corrupt extracted names/signatures.

Guards against the class-body double-visit bug (methods extracted twice in
JS/TS) and the UTF-8 byte-offset bug (slicing str with tree-sitter byte
offsets shifts everything after an emoji/accented character).
"""

import pytest

from codenav.code_navigator import PythonAnalyzer
from codenav.dart_analyzer import (
    TREE_SITTER_AVAILABLE as DART_AVAILABLE,
)
from codenav.dart_analyzer import (
    DartAnalyzer,
)
from codenav.go_analyzer import (
    TREE_SITTER_AVAILABLE as GO_AVAILABLE,
)
from codenav.go_analyzer import (
    GoAnalyzer,
)
from codenav.js_ts_analyzer import (
    TREE_SITTER_AVAILABLE as JS_AVAILABLE,
)
from codenav.js_ts_analyzer import (
    JavaScriptAnalyzer,
    TypeScriptAnalyzer,
)
from codenav.ruby_analyzer import (
    TREE_SITTER_AVAILABLE as RUBY_AVAILABLE,
)
from codenav.ruby_analyzer import (
    RubyAnalyzer,
)
from codenav.rust_analyzer import (
    TREE_SITTER_AVAILABLE as RUST_AVAILABLE,
)
from codenav.rust_analyzer import (
    RustAnalyzer,
)

# Every fixture starts with a multi-byte comment (emoji + accents) so that a
# byte-offset/char-offset mismatch shifts every extraction after it.

PY_SOURCE = """\
# café ☕ über naïve
class Calculadora:
    def sumar(self, a, b):
        return a + b

    def restar(self, a, b):
        return a - b


def saludar(nombre):
    return f"hola {nombre}"
"""

JS_SOURCE = """\
// café ☕ über naïve
class Calculator {
    getValue() {
        return this.value;
    }

    setValue(v) {
        this.value = v;
    }
}

function greet(name) {
    return `hi ${name}`;
}

const doubler = (x) => x * 2;
"""

TS_SOURCE = """\
// café ☕ über naïve
interface User {
    name: string;
}

type Status = 'active' | 'inactive';

enum Color {
    Red,
    Green,
}

class Repo {
    find(id: number): User | null {
        return null;
    }

    save(user: User): void {
    }
}

function main(): void {
}
"""

GO_SOURCE = """\
package main

// café ☕ über naïve
type User struct {
    Name string
}

func (u *User) Greet() string {
    return u.Name
}

func Add(a, b int) int {
    return a + b
}
"""

RUST_SOURCE = """\
// café ☕ über naïve
struct User {
    name: String,
}

impl User {
    pub fn new(name: String) -> Self {
        User { name }
    }

    pub fn greet(&self) -> &str {
        &self.name
    }
}

fn add(a: i32, b: i32) -> i32 {
    a + b
}
"""

RUBY_SOURCE = """\
# café ☕ über naïve
class User
  def initialize(name)
    @name = name
  end

  def greet
    'hola'
  end
end

def helper
  42
end
"""

DART_SOURCE = """\
// café ☕ über naïve
class Usuario {
  String nombre = '';

  String saludar() {
    return nombre;
  }

  void renombrar(String nuevo) {
    nombre = nuevo;
  }
}

String saludo(String n) {
  return 'hola';
}
"""

CASES = [
    pytest.param(
        PythonAnalyzer,
        "sample.py",
        PY_SOURCE,
        {"Calculadora", "sumar", "restar", "saludar"},
        id="python",
    ),
    pytest.param(
        JavaScriptAnalyzer,
        "sample.js",
        JS_SOURCE,
        {"Calculator", "getValue", "setValue", "greet", "doubler"},
        marks=pytest.mark.skipif(not JS_AVAILABLE, reason="tree-sitter JS not installed"),
        id="javascript",
    ),
    pytest.param(
        TypeScriptAnalyzer,
        "sample.ts",
        TS_SOURCE,
        {"User", "Status", "Color", "Repo", "find", "save", "main"},
        marks=pytest.mark.skipif(not JS_AVAILABLE, reason="tree-sitter TS not installed"),
        id="typescript",
    ),
    pytest.param(
        GoAnalyzer,
        "sample.go",
        GO_SOURCE,
        {"User", "Greet", "Add"},
        marks=pytest.mark.skipif(not GO_AVAILABLE, reason="tree-sitter Go not installed"),
        id="go",
    ),
    pytest.param(
        RustAnalyzer,
        "sample.rs",
        RUST_SOURCE,
        {"User", "new", "greet", "add"},
        marks=pytest.mark.skipif(not RUST_AVAILABLE, reason="tree-sitter Rust not installed"),
        id="rust",
    ),
    pytest.param(
        RubyAnalyzer,
        "sample.rb",
        RUBY_SOURCE,
        {"User", "initialize", "greet", "helper"},
        marks=pytest.mark.skipif(not RUBY_AVAILABLE, reason="tree-sitter Ruby not installed"),
        id="ruby",
    ),
    pytest.param(
        DartAnalyzer,
        "sample.dart",
        DART_SOURCE,
        {"Usuario", "saludar", "renombrar", "saludo"},
        marks=pytest.mark.skipif(not DART_AVAILABLE, reason="tree-sitter-dart not installed"),
        id="dart",
    ),
]


@pytest.mark.parametrize("analyzer_cls,file_path,source,expected_names", CASES)
def test_no_duplicate_symbols(analyzer_cls, file_path, source, expected_names):
    """Each (name, type, parent, line_start) tuple must appear exactly once."""
    symbols = analyzer_cls(file_path, source).analyze()
    keys = [(s.name, s.type, s.parent, s.line_start) for s in symbols]
    duplicates = {k for k in keys if keys.count(k) > 1}
    assert not duplicates, f"duplicate symbols emitted: {duplicates}"


@pytest.mark.parametrize("analyzer_cls,file_path,source,expected_names", CASES)
def test_names_intact_after_multibyte_chars(analyzer_cls, file_path, source, expected_names):
    """Symbol names must survive multi-byte characters earlier in the file."""
    symbols = analyzer_cls(file_path, source).analyze()
    names = {s.name for s in symbols}
    missing = expected_names - names
    assert not missing, f"expected symbols missing (offset corruption?): {missing}"
    for s in symbols:
        assert "�" not in s.name, f"replacement char in name: {s.name!r}"
        if s.signature:
            assert "�" not in s.signature, f"replacement char in signature of {s.name}"
