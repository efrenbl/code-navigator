"""Tests for the MCP import guard's failure message.

A missing ``mcp`` and an installed-but-incompatible ``mcp`` both raise
ImportError. The guard must not report the second as the first: "install
codenav[mcp]" sends the user after a package that is already present, which is
how an unbounded ``mcp`` pin resolving to 2.x turns into a silent dead end.
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from pathlib import Path

from codenav.mcp import MCP_REQUIREMENT, _import_failure_message

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


class TestImportFailureMessage:
    def test_missing_mcp_says_not_installed(self, monkeypatch):
        def raise_not_found(_name):
            raise PackageNotFoundError("mcp")

        monkeypatch.setattr("codenav.mcp.version", raise_not_found)

        message = _import_failure_message(ImportError("No module named 'mcp'"))

        assert "not installed" in message
        assert "codenav[mcp]" in message
        assert MCP_REQUIREMENT in message

    def test_incompatible_mcp_reports_resolved_version(self, monkeypatch):
        monkeypatch.setattr("codenav.mcp.version", lambda _name: "2.0.0")

        message = _import_failure_message(ImportError("No module named 'mcp.server.fastmcp'"))

        assert "2.0.0" in message
        assert MCP_REQUIREMENT in message
        assert "mcp.server.fastmcp" in message
        # The point of the fix: do not tell the user to install what is installed.
        assert "not installed" not in message

    def test_incompatible_message_keeps_the_original_error(self, monkeypatch):
        monkeypatch.setattr("codenav.mcp.version", lambda _name: "2.1.3")

        message = _import_failure_message(ImportError("cannot import name 'FastMCP'"))

        assert "cannot import name 'FastMCP'" in message


class TestRequirementMatchesPackaging:
    def test_declared_requirement_matches_every_pyproject_pin(self):
        """The message quotes a range; drift would make it advise a bad fix."""
        pins = set(re.findall(r'"(mcp>=[^"]+)"', PYPROJECT.read_text()))

        assert pins == {MCP_REQUIREMENT}

    def test_pyproject_pins_have_an_upper_bound(self):
        pins = re.findall(r'"(mcp>=[^"]+)"', PYPROJECT.read_text())

        assert pins, "expected at least one mcp pin in pyproject.toml"
        for pin in pins:
            assert "<2" in pin, f"{pin} would resolve to mcp 2.x on a fresh install"
