"""Centralized regex-safety helpers.

Single entry point for compiling *user-supplied* regex patterns so every code
path applies the same ReDoS guard instead of calling ``re.compile`` directly.
Both the symbol search (``code_search``) and the file grep (``line_reader``)
route through :func:`safe_compile`.

Threat model: patterns come from the same person running the CLI (or the agent
driving the MCP server), so a catastrophic pattern is at worst a local
CPU-spin, not a remote DoS. The guard is a conservative heuristic that rejects
the common nested-quantifier constructs before they reach the backtracking
engine; it is intentionally dependency-free (no third-party regex engine or
platform-specific matching timeout) to preserve the zero-dependency core.
"""

import re

# Heuristic detector for catastrophic-backtracking constructs: a group whose
# body already contains an unbounded quantifier (``+``, ``*`` or ``{n,}``) and
# which is itself quantified — e.g. (a+)+, (a*)*, (a+)*, (.*)+, (\w+){2,}.
# A group with no inner unbounded quantifier (e.g. (foo)+, (a|b)*) is allowed.
_CATASTROPHIC_RE = re.compile(
    r"\("  # opening group
    r"[^)]*"  # ... any group content ...
    r"(?:[+*]|\{\d+,\d*\})"  # ... containing an unbounded quantifier ...
    r"[^)]*"  # ... more group content ...
    r"\)"  # closing group
    r"\s*"
    r"(?:[+*]|\{\d+,\d*\})"  # ... and the group itself is quantified
)


def safe_compile(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    """Compile a user-supplied regex with a guard against ReDoS constructs.

    Args:
        pattern: The regex pattern to compile.
        flags: Flags passed to :func:`re.compile` (defaults to IGNORECASE, the
            behaviour every current caller relies on).

    Returns:
        The compiled pattern.

    Raises:
        ValueError: If the pattern contains a catastrophic construct or is not
            a valid regular expression.
    """
    if _CATASTROPHIC_RE.search(pattern):
        raise ValueError(
            f"Regex pattern rejected: contains nested quantifiers "
            f"that could cause ReDoS: {pattern!r}"
        )
    try:
        return re.compile(pattern, flags)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}") from None
