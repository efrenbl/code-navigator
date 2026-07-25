"""Gitignore-semantics tests, validated against ``git check-ignore`` as oracle.

Every construct the matcher claims to support is checked against real git on a
synthetic repo: if codenav and git disagree on a single path, the test fails.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from codenav.gitignore import GitignoreMatcher

git = shutil.which("git")
pytestmark = pytest.mark.skipif(git is None, reason="git not available")


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def _git_ignores(repo, rel_path) -> bool:
    """Oracle: does git consider ``rel_path`` ignored? (exit 0 = ignored)."""
    result = _run([git, "check-ignore", "-q", "--", rel_path], repo)
    return result.returncode == 0


def _build_matcher(repo) -> GitignoreMatcher:
    """Collect .gitignore files top-down, scoping each to its directory."""
    matcher = GitignoreMatcher()
    info_exclude = os.path.join(repo, ".git", "info", "exclude")
    if os.path.exists(info_exclude):
        with open(info_exclude, encoding="utf-8") as f:
            matcher.add_patterns(f.read().splitlines(), "")
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d != ".git"]
        dirs.sort()
        if ".gitignore" in files:
            rel = os.path.relpath(root, repo).replace(os.sep, "/")
            base = "" if rel == "." else rel
            with open(os.path.join(root, ".gitignore"), encoding="utf-8") as f:
                matcher.add_patterns(f.read().splitlines(), base)
    return matcher


def _make_repo(tmp_path, tree: dict[str, str], paths: list[tuple[str, bool]]):
    """Create a git repo with the given files and .gitignore contents.

    ``tree`` maps rel path → content ("" makes a plain file; a key ending in
    ``/.gitignore`` writes an ignore file). ``paths`` are (rel, is_dir) probes;
    directories and files are materialized so git can judge them.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _run([git, "init", "-q"], str(repo))
    for rel, content in tree.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    for rel, is_dir in paths:
        p = repo / rel
        if is_dir:
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text("x")
    return repo


def _assert_agrees(repo, probes: list[tuple[str, bool]]):
    matcher = _build_matcher(str(repo))
    mismatches = []
    for rel, is_dir in probes:
        ours = matcher.is_ignored(rel, is_dir)
        theirs = _git_ignores(str(repo), rel)
        if ours != theirs:
            mismatches.append(f"{rel} (dir={is_dir}): codenav={ours} git={theirs}")
    assert not mismatches, "disagreements with git check-ignore:\n" + "\n".join(mismatches)


class TestGitignoreOracle:
    def test_the_main_substring_bug(self, tmp_path):
        """The canonical 0.a defect: `main` must not match `domain`/`main.go`."""
        repo = _make_repo(
            tmp_path,
            {".gitignore": "main\n"},
            [
                ("internal/domain/entity/thing.go", False),
                ("cmd/api/main.go", False),
                ("internal/svc/thing.go", False),
                ("main", True),  # a real directory named main IS ignored
            ],
        )
        _assert_agrees(
            repo,
            [
                ("internal/domain/entity/thing.go", False),
                ("cmd/api/main.go", False),
                ("internal/svc/thing.go", False),
                ("main", True),
            ],
        )

    def test_path_component_not_substring(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "node_modules\n.env\n"},
            [
                ("node_modules/pkg/index.js", False),
                ("node_modules_backup/x.js", False),
                (".env", False),
                (".environment", False),
                ("config.env.example", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("node_modules/pkg/index.js", False),
                ("node_modules_backup/x.js", False),
                (".env", False),
                (".environment", False),
                ("config.env.example", False),
            ],
        )

    def test_anchoring_and_dir_only(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "/build\nlogs/\n*.tmp\n"},
            [
                ("build/out.o", False),
                ("src/build/out.o", False),  # not anchored at root → not ignored
                ("logs/app.log", False),
                ("a/logs/app.log", False),
                ("cache.tmp", False),
                ("nested/cache.tmp", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("build/out.o", False),
                ("src/build/out.o", False),
                ("logs/app.log", False),
                ("a/logs/app.log", False),
                ("cache.tmp", False),
                ("nested/cache.tmp", False),
            ],
        )

    def test_double_star(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "**/generated\ndoc/**\na/**/z.txt\n"},
            [
                ("pkg/generated/x.go", False),
                ("generated/y.go", False),
                ("doc/api/index.html", False),
                ("a/b/c/z.txt", False),
                ("a/z.txt", False),
                ("other/z.txt", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("pkg/generated/x.go", False),
                ("generated/y.go", False),
                ("doc/api/index.html", False),
                ("a/b/c/z.txt", False),
                ("a/z.txt", False),
                ("other/z.txt", False),
            ],
        )

    def test_negation_reinclude(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "*.log\n!important.log\n"},
            [
                ("app.log", False),
                ("important.log", False),
                ("logs/important.log", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("app.log", False),
                ("important.log", False),
                ("logs/important.log", False),
            ],
        )

    def test_negation_cannot_reinclude_under_excluded_dir(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "build/\n!build/keep.txt\n"},
            [
                ("build/keep.txt", False),
                ("build/out.o", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("build/keep.txt", False),
                ("build/out.o", False),
            ],
        )

    def test_nested_gitignore_precedence(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {
                ".gitignore": "*.tmp\n",
                "sub/.gitignore": "!keep.tmp\nlocal.txt\n",
            },
            [
                ("root.tmp", False),
                ("sub/keep.tmp", False),  # re-included by nested rule
                ("sub/other.tmp", False),  # still ignored by root rule
                ("sub/local.txt", False),  # ignored only in sub
                ("local.txt", False),  # not ignored at root
            ],
        )
        _assert_agrees(
            repo,
            [
                ("root.tmp", False),
                ("sub/keep.tmp", False),
                ("sub/other.tmp", False),
                ("sub/local.txt", False),
                ("local.txt", False),
            ],
        )

    def test_char_class_and_question(self, tmp_path):
        repo = _make_repo(
            tmp_path,
            {".gitignore": "file?.txt\n*.[oa]\n"},
            [
                ("fileA.txt", False),
                ("file10.txt", False),  # ? matches one char only
                ("main.o", False),
                ("lib.a", False),
                ("lib.c", False),
            ],
        )
        _assert_agrees(
            repo,
            [
                ("fileA.txt", False),
                ("file10.txt", False),
                ("main.o", False),
                ("lib.a", False),
                ("lib.c", False),
            ],
        )

    def test_info_exclude(self, tmp_path):
        repo = _make_repo(tmp_path, {".gitignore": "\n"}, [("secret.key", False)])
        exclude = repo / ".git" / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        exclude.write_text("*.key\n")
        _assert_agrees(repo, [("secret.key", False), ("a/b.key", False)])


class TestSymlinkedRoot:
    """A caller may pass an unresolved path under a symlinked root (macOS /var)."""

    def test_should_ignore_with_symlinked_root(self, tmp_path):
        from pathlib import Path

        from codenav.code_navigator import CodeNavigator

        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        os.symlink(real, link)
        mapper = CodeNavigator(str(link))  # root_path resolves the symlink
        # Paths built from the unresolved link must still match ignore rules.
        assert mapper.should_ignore(Path(link) / "node_modules" / "test.js")
        assert mapper.should_ignore(Path(link) / ".git" / "config")
        assert not mapper.should_ignore(Path(link) / "src" / "main.py")
