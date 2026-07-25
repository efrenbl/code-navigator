#!/usr/bin/env python3
"""Reproduce the pre-2.2.9 gitignore substring bug (0.a) and show it is fixed.

Builds the canonical 10-line synthetic repo, then prints three counts:
  - files the OLD substring predicate would have swallowed,
  - files the NEW matcher indexes,
  - files git check-ignore actually considers ignored.

Run: python scripts/repro_gitignore_bug.py
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import subprocess
import tempfile

from codenav.code_navigator import DEFAULT_IGNORE_PATTERNS, CodeNavigator

PROBES = [
    "internal/domain/entity/thing.go",  # "domain" contains "main"
    "cmd/api/main.go",  # basename contains "main"
    "internal/svc/thing.go",  # control: no "main"
]


def build_repo(root: str) -> None:
    for d in ("internal/domain/entity", "internal/svc", "cmd/api"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    files = {
        ".gitignore": "main\n",
        "internal/domain/entity/thing.go": "package entity\nfunc Foo() {}\n",
        "internal/svc/thing.go": "package svc\nfunc Bar() {}\n",
        "cmd/api/main.go": "package main\nfunc main() {}\n",
    }
    for rel, content in files.items():
        with open(os.path.join(root, rel), "w") as f:
            f.write(content)


def old_swallowed(rel: str) -> bool:
    """The historical predicate: basename fnmatch OR raw substring in the path."""
    name = rel.rsplit("/", 1)[-1]
    for pattern in list(DEFAULT_IGNORE_PATTERNS) + ["main"]:
        if fnmatch.fnmatch(name, pattern) or pattern in rel:
            return True
    return False


def main() -> None:
    root = tempfile.mkdtemp(prefix="cnv-repro-")
    try:
        build_repo(root)
        indexed = {
            f for f in CodeNavigator(root, use_gitignore=True).scan()["files"] if f.endswith(".go")
        }
        git_ignored = [
            p
            for p in PROBES
            if subprocess.run(["git", "check-ignore", "-q", "--", p], cwd=root).returncode == 0
        ]
        old = [p for p in PROBES if old_swallowed(p)]
        new = [p for p in PROBES if p in indexed]
        print("=== The three counts (0.a) ===")
        print(f"  OLD substring logic swallowed : {len(old)}/3  {old}")
        print(f"  NEW matcher indexed (present) : {len(new)}/3  {new}")
        print(f"  git check-ignore says ignored : {len(git_ignored)}/3  {git_ignored}")
        assert len(new) == 3 and len(git_ignored) == 0, "fix regressed!"
        print("\nOK: new matcher agrees with git (0/3 ignored); old logic lost 2/3.")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
