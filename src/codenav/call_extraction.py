"""Shared call-site extraction for the tree-sitter analyzers.

Populates ``Symbol.dependencies`` (the names a function/method calls) so the
dependency lookups work for every AST language, not just Python. This mirrors
the Python analyzer, which collects call targets via ``ast.walk`` and dedups
them.

Two entry points:

- :func:`collect_calls` for the C-family / curly-brace grammars (JavaScript,
  TypeScript, Go, Rust), where a call is a ``call_expression`` node with a
  ``function`` field (plus Rust ``macro_invocation``).
- :func:`collect_dart_calls` for Dart, whose grammar represents an invocation
  as ``<callee> selector(argument_part)`` rather than a single call node.

Both return a sorted, de-duplicated, length-capped list of callee names.
"""

# Node kinds that are (or end in) a plain name we can read directly.
_NAME_TYPES = frozenset(
    {"identifier", "field_identifier", "property_identifier", "type_identifier"}
)

# Member/qualified access kinds — the callee is the last name child
# (``obj.method`` -> ``method``, ``mod::func`` -> ``func``).
_ACCESS_TYPES = frozenset(
    {
        "member_expression",  # JS/TS
        "selector_expression",  # Go
        "field_expression",  # Rust
        "scoped_identifier",  # Rust
        "navigation_expression",
    }
)

# Keep maps compact: cap callees recorded per symbol.
MAX_CALLS = 50


def _text(node, source_bytes: bytes) -> str:
    # tree-sitter offsets are UTF-8 byte offsets; slice the encoded bytes and
    # decode so multi-byte characters earlier in the file don't misalign names.
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _callee_name(fn, source_bytes: bytes) -> str | None:
    """Resolve the callee name from a call's ``function`` node."""
    if fn is None:
        return None
    if fn.type in _NAME_TYPES:
        return _text(fn, source_bytes)
    if fn.type in _ACCESS_TYPES:
        for child in reversed(fn.children):
            if child.type in _NAME_TYPES:
                return _text(child, source_bytes)
    return None


def collect_calls(node, source_bytes: bytes, *, macro_types: tuple[str, ...] = ()) -> list[str]:
    """Return sorted unique callee names within a function/method subtree.

    Args:
        node: The function/method AST node to walk (its whole subtree).
        source_bytes: The full source as UTF-8 bytes (tree-sitter offsets are
            byte offsets).
        macro_types: Extra node kinds whose ``macro`` field is a callee
            (e.g. Rust ``macro_invocation``).
    """
    if node is None:
        return []
    calls: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type == "call_expression":
            name = _callee_name(n.child_by_field_name("function"), source_bytes)
            if name:
                calls.add(name)
        elif macro_types and n.type in macro_types:
            name = _callee_name(n.child_by_field_name("macro"), source_bytes)
            if name:
                calls.add(name)
        stack.extend(n.children)
    return sorted(calls)[:MAX_CALLS]


def _dart_callee(prev, source_bytes: bytes) -> str | None:
    """The callee for a Dart ``argument_part`` selector is the node before it:
    a bare ``identifier`` (``foo()``) or a ``.name`` selector (``obj.bar()``)."""
    if prev is None:
        return None
    if prev.type == "identifier":
        return _text(prev, source_bytes)
    if prev.type == "selector":
        for gc in prev.children:
            if gc.type == "unconditional_assignable_selector":
                for ggc in gc.children:
                    if ggc.type == "identifier":
                        return _text(ggc, source_bytes)
    return None


def collect_dart_calls(body, source_bytes: bytes) -> list[str]:
    """Return sorted unique callee names within a Dart ``function_body``."""
    if body is None:
        return []
    calls: set[str] = set()
    stack = [body]
    while stack:
        n = stack.pop()
        children = n.children
        for i, child in enumerate(children):
            if child.type == "selector" and any(
                gc.type == "argument_part" for gc in child.children
            ):
                name = _dart_callee(children[i - 1] if i > 0 else None, source_bytes)
                if name:
                    calls.add(name)
        stack.extend(children)
    return sorted(calls)[:MAX_CALLS]
