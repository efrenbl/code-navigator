"""Self-contained gitignore-semantics matcher (zero external dependencies).

The historical ``should_ignore`` matched patterns as a raw substring against the
full path (``"main" in "internal/domain/entity/x.go"`` → ignored), which silently
dropped whole subtrees whose names merely *contained* a pattern. This module
replaces that with the real gitignore semantics, validated in tests against
``git check-ignore`` as the oracle:

- patterns match on **path components**, never as substrings;
- a slash anywhere but the end **anchors** the pattern to the base directory;
- a trailing ``/`` matches directories only;
- ``*``/``?``/``[...]`` do not cross ``/``; ``**`` does;
- ``!`` negates (last matching rule wins);
- nested ``.gitignore`` files are scoped to their directory, deeper files
  overriding shallower ones (achieved by rule order + last-match-wins).

The core stays dependency-free by design (codenav ships with ``dependencies =
[]``). ``pathspec.GitIgnoreSpec`` would be the drop-in replacement if that
constraint is ever relaxed; it is deliberately not adopted for the core.
"""

from __future__ import annotations

import re


def _translate_segment(seg: str) -> str:
    """Translate one gitignore path segment (no ``/``) to a regex fragment."""
    out: list[str] = []
    i = 0
    while i < len(seg):
        c = seg[i]
        if c == "*":
            # Collapse consecutive '*' within a segment (git treats a non
            # slash-adjacent '**' as a plain '*').
            while i + 1 < len(seg) and seg[i + 1] == "*":
                i += 1
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = i + 1
            if j < len(seg) and seg[j] in ("!", "^"):
                j += 1
            if j < len(seg) and seg[j] == "]":
                j += 1
            while j < len(seg) and seg[j] != "]":
                j += 1
            if j >= len(seg):
                out.append(r"\[")
            else:
                inner = seg[i + 1 : j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append("[" + inner + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _build_body(pattern: str, anchored: bool) -> str:
    """Build the regex body (no trailing anchor) matching a relative path."""
    if not anchored:
        # A floating pattern has no internal slash: a single segment that may
        # appear at any depth.
        return "(?:^|.*/)" + _translate_segment(pattern)

    chunks = ["^"]
    parts = pattern.split("/")
    n = len(parts)
    for i, seg in enumerate(parts):
        last = i == n - 1
        if seg == "**":
            chunks.append(".*" if last else "(?:.*/)?")
            continue
        chunks.append(_translate_segment(seg))
        if not last:
            chunks.append("/")
    return "".join(chunks)


class _Rule:
    """One compiled gitignore pattern, scoped to a base directory."""

    __slots__ = ("negation", "dir_only", "base_dir", "_under", "_exact", "_any")

    def __init__(self, negation: bool, dir_only: bool, body: str, base_dir: str):
        self.negation = negation
        self.dir_only = dir_only
        self.base_dir = base_dir
        # A dir-only pattern matches the directory itself (exact, only when the
        # path is a directory) or anything under it (tail). A normal pattern
        # matches the item or anything under it.
        self._exact = re.compile(body + "$")
        self._under = re.compile(body + "/.*$")
        self._any = re.compile(body + "(?:/.*)?$")

    def matches(self, rel: str, is_dir: bool) -> bool:
        if self.dir_only:
            return bool(self._under.match(rel)) or (is_dir and bool(self._exact.match(rel)))
        return bool(self._any.match(rel))


def parse_pattern(line: str) -> tuple[bool, bool, str] | None:
    """Parse one gitignore line → ``(negation, dir_only, body)`` or ``None``.

    ``None`` means the line is blank or a comment and contributes no rule.
    """
    if not line or line.startswith("#"):
        return None
    # Strip trailing whitespace unless escaped ("foo\ " keeps one space).
    stripped = line
    if not stripped.endswith("\\ "):
        stripped = stripped.rstrip()
    if not stripped:
        return None

    negation = False
    if stripped.startswith("!"):
        negation = True
        stripped = stripped[1:]
    elif stripped.startswith("\\#") or stripped.startswith("\\!"):
        stripped = stripped[1:]

    dir_only = stripped.endswith("/")
    if dir_only:
        stripped = stripped[:-1]
    if not stripped:
        return None

    anchored = "/" in stripped
    if stripped.startswith("/"):
        stripped = stripped.lstrip("/")
        anchored = True
    if not stripped:
        return None

    body = _build_body(stripped, anchored)
    return negation, dir_only, body


class GitignoreMatcher:
    """Ordered set of gitignore rules with last-match-wins evaluation.

    Rules carry a ``base_dir`` (POSIX, relative to the scan root, ``""`` for the
    root). A rule only applies to paths under its base dir; the path is matched
    against the portion below that base. Add root-level sources (codenav
    defaults, user ``-i`` patterns, the root ``.gitignore``, ``.git/info/exclude``,
    ``core.excludesfile``) at ``base_dir=""``; add nested ``.gitignore`` files at
    their directory so deeper rules, appended later, win.
    """

    def __init__(self) -> None:
        self._rules: list[_Rule] = []

    def add_patterns(self, lines: list[str], base_dir: str = "") -> None:
        for line in lines:
            parsed = parse_pattern(line)
            if parsed is None:
                continue
            negation, dir_only, body = parsed
            self._rules.append(_Rule(negation, dir_only, body, base_dir))

    def _eval(self, rel_path: str, is_dir: bool) -> bool | None:
        """Last-match-wins decision for one path, or ``None`` if no rule matches."""
        decision: bool | None = None
        for rule in self._rules:
            if rule.base_dir:
                prefix = rule.base_dir + "/"
                if not rel_path.startswith(prefix):
                    continue
                local = rel_path[len(prefix) :]
            else:
                local = rel_path
            if rule.matches(local, is_dir):
                decision = not rule.negation
        return decision

    def is_ignored(self, rel_path: str, is_dir: bool) -> bool:
        """Return whether a POSIX path relative to the scan root is ignored.

        Walks the path's ancestors top-down like git: once a parent directory is
        excluded, nothing under it can be re-included by a later negation (git's
        "cannot re-include a file if a parent directory is excluded" rule).
        """
        parts = rel_path.split("/")
        for i in range(len(parts)):
            sub = "/".join(parts[: i + 1])
            is_ancestor = i < len(parts) - 1
            decision = self._eval(sub, True if is_ancestor else is_dir)
            if is_ancestor:
                if decision is True:
                    return True
            else:
                return bool(decision)
        return False
