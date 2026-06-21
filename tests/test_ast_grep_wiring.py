"""Tests for wiring AstGrepAnalyzer into the scan dispatch.

The regex-tier languages (Java, C, C++, PHP) use ast-grep when the optional
``[fast]`` extra is installed (real AST → parent linkage), and degrade to the
regex GenericAnalyzer otherwise. These tests cover both branches.
"""

import pytest

from codenav.ast_grep_analyzer import is_ast_grep_available
from codenav.code_navigator import CodeNavigator

JAVA_SRC = """\
package com.example;

public class Account {
    private double balance;

    public void deposit(double amount) {
        this.balance = this.balance + amount;
    }

    public double getBalance() {
        return this.balance;
    }
}

interface Ledger {
    void record(String entry);
}
"""


def _java_symbols(tmp_path):
    proj = tmp_path / "j"
    proj.mkdir()
    (proj / "Account.java").write_text(JAVA_SRC)
    result = CodeNavigator(str(proj)).scan()
    syms = []
    for info in result["files"].values():
        syms.extend(info["symbols"])
    return result["stats"], syms


def test_java_is_mapped_regardless_of_astgrep(tmp_path):
    """Java must produce symbols whether ast-grep is present or not."""
    stats, syms = _java_symbols(tmp_path)
    assert stats["errors"] == 0
    names = {s["name"] for s in syms}
    assert "Account" in names
    assert "deposit" in names


@pytest.mark.skipif(not is_ast_grep_available(), reason="ast-grep-py not installed")
def test_java_methods_have_parent_via_astgrep(tmp_path):
    """The AST path links methods to their enclosing type — something the
    regex fallback cannot do for Java."""
    _stats, syms = _java_symbols(tmp_path)
    methods = {s["name"]: s for s in syms if s["type"] == "method"}
    assert methods["deposit"]["parent"] == "Account"
    assert methods["getBalance"]["parent"] == "Account"
    assert methods["record"]["parent"] == "Ledger"


@pytest.mark.skipif(not is_ast_grep_available(), reason="ast-grep-py not installed")
def test_astgrep_analyzer_sets_parent_directly():
    from codenav.ast_grep_analyzer import AstGrepAnalyzer

    analyzer = AstGrepAnalyzer("Account.java", JAVA_SRC, "java")
    assert analyzer.available
    by_name = {s.name: s for s in analyzer.analyze()}
    assert by_name["deposit"].parent == "Account"
    assert by_name["record"].parent == "Ledger"


def test_fallback_to_regex_when_astgrep_absent(tmp_path, monkeypatch):
    """Force the no-ast-grep path and confirm Java still maps via regex."""
    import codenav.ast_grep_analyzer as ag

    monkeypatch.setattr(ag, "is_ast_grep_available", lambda: False)
    stats, syms = _java_symbols(tmp_path)
    assert stats["errors"] == 0
    names = {s["name"] for s in syms}
    assert "Account" in names  # regex GenericAnalyzer still finds the class
