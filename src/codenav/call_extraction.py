"""Shared call-site and doc-comment extraction for the tree-sitter analyzers.

Populates ``Symbol.dependencies`` (the names a function/method calls) so the
dependency lookups work for every AST language, not just Python. This mirrors
the Python analyzer, which collects call targets via ``ast.walk`` and dedups
them.

Call-site entry points:

- :func:`collect_calls` for the C-family / curly-brace grammars (JavaScript,
  TypeScript, Go, Rust), where a call is a ``call_expression`` node with a
  ``function`` field (plus Rust ``macro_invocation``).
- :func:`collect_dart_calls` for Dart, whose grammar represents an invocation
  as ``<callee> selector(argument_part)`` rather than a single call node.
- :func:`collect_ruby_calls` for Ruby, whose grammar wraps every invocation in
  a ``call`` / ``command`` / ``method_call`` node with a ``method`` field.

All three return a sorted, de-duplicated, length-capped list of callee names.

Doc-comment entry point:

- :func:`collect_doc_comment` walks the contiguous comment siblings directly
  above a declaration node and returns the first few cleaned lines. Used by the
  Go/Rust/Ruby/Dart analyzers to populate ``Symbol.docstring``.
"""

# Node kinds that are (or end in) a plain name we can read directly.
_NAME_TYPES = frozenset(
    {
        "identifier",
        "field_identifier",
        "property_identifier",
        "type_identifier",
        "constant",
        "name",  # PHP
        "simple_identifier",  # Kotlin/Swift
    }
)

# Member/qualified access kinds — the callee is the last name child
# (``obj.method`` -> ``method``, ``mod::func`` -> ``func``).
_ACCESS_TYPES = frozenset(
    {
        "member_expression",  # JS/TS
        "selector_expression",  # Go
        "field_expression",  # Rust
        "scoped_identifier",  # Rust
        "navigation_expression",  # Kotlin/Swift
        "qualified_identifier",  # C++
        "member_access_expression",  # C#
    }
)

# Ruby wraps every invocation in one of these node kinds (``method`` field).
_RUBY_CALL_TYPES = frozenset({"call", "command", "method_call"})

# Ruby bare calls (``reset`` with no parens/receiver) parse as plain
# identifiers; only statement-level ones — direct children of these — count.
_RUBY_BLOCK_PARENTS = frozenset(
    {"body_statement", "then", "else", "do", "begin", "rescue", "ensure", "when"}
)

# Not bare calls: keywords/literals, plus visibility modifiers, which the
# language-pack grammar parses as statement-level identifiers.
_RUBY_BARE_SKIP = frozenset(
    {
        "true",
        "false",
        "nil",
        "self",
        "super",
        "__FILE__",
        "__LINE__",
        "__dir__",
        "private",
        "protected",
        "public",
        "module_function",
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


def collect_calls(
    node,
    source_bytes: bytes,
    *,
    call_types: tuple[str, ...] = ("call_expression",),
    callee_field: str = "function",
    macro_types: tuple[str, ...] = (),
) -> list[str]:
    """Return sorted unique callee names within a function/method subtree.

    Args:
        node: The function/method AST node to walk (its whole subtree).
        source_bytes: The full source as UTF-8 bytes (tree-sitter offsets are
            byte offsets).
        call_types: Node kinds that represent an invocation (default matches
            the C-family grammars; e.g. Java uses ``method_invocation``, PHP
            ``function_call_expression``/``member_call_expression``).
        callee_field: Field on a call node holding the callee (``"function"``
            in most grammars, ``"name"`` in Java's ``method_invocation``).
        macro_types: Extra node kinds whose ``macro`` field is a callee
            (e.g. Rust ``macro_invocation``).
    """
    if node is None:
        return []
    calls: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in call_types:
            name = _callee_name(n.child_by_field_name(callee_field), source_bytes)
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
    # ``super.dispose()`` / ``this.m()``: the ``.name`` selector precedes the
    # argument part directly, without a wrapping ``selector`` node.
    inner = prev if prev.type == "unconditional_assignable_selector" else None
    if prev.type == "selector":
        for gc in prev.children:
            if gc.type == "unconditional_assignable_selector":
                inner = gc
                break
    if inner is not None:
        for gc in inner.children:
            if gc.type == "identifier":
                return _text(gc, source_bytes)
    return None


def collect_dart_calls(body, source_bytes: bytes) -> list[str]:
    """Return sorted unique callee names within a Dart ``function_body``."""
    if body is None:
        return []
    calls: set[str] = set()
    stack = [body]
    while stack:
        n = stack.pop()
        if n.type == "new_expression":
            # ``new Widget()`` — explicit constructor invocation.
            type_id = next((c for c in n.children if c.type == "type_identifier"), None)
            if type_id is not None:
                calls.add(_text(type_id, source_bytes))
        elif n.type == "const_object_expression":
            # ``const EdgeInsets.all(8)`` → ``all``; ``const Foo()`` → ``Foo``.
            named = next((c for c in n.children if c.type == "identifier"), None)
            type_id = named or next((c for c in n.children if c.type == "type_identifier"), None)
            if type_id is not None:
                calls.add(_text(type_id, source_bytes))
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


def collect_ruby_calls(body, source_bytes: bytes) -> list[str]:
    """Return sorted unique callee names within a Ruby method/body subtree.

    tree-sitter-ruby models every invocation — ``foo()``, ``puts "x"``,
    ``obj.bar`` — as a ``call`` / ``command`` / ``method_call`` node whose
    ``method`` field is the callee name (an ``identifier`` or ``constant``).
    """
    if body is None:
        return []
    calls: set[str] = set()
    stack = [body]
    while stack:
        n = stack.pop()
        if n.type in _RUBY_CALL_TYPES:
            method = n.child_by_field_name("method")
            if method is not None and method.type in ("identifier", "constant"):
                calls.add(_text(method, source_bytes))
        elif (
            n.type == "identifier" and n.parent is not None and n.parent.type in _RUBY_BLOCK_PARENTS
        ):
            # Bare call: `reset` as a statement. Capitalized names are
            # constant refs, not calls.
            name = _text(n, source_bytes)
            if name not in _RUBY_BARE_SKIP and name[:1].islower():
                calls.add(name)
        stack.extend(n.children)
    return sorted(calls)[:MAX_CALLS]


def collect_positional_calls(
    node,
    source_bytes: bytes,
    *,
    call_types: tuple[str, ...] = ("call_expression",),
) -> list[str]:
    """Callee names for grammars whose call node has no ``function`` field.

    Kotlin and Swift model an invocation as ``call_expression(callee,
    call_suffix)``: the callee is the first child — a ``simple_identifier``
    (``foo()``) or a ``navigation_expression`` whose ``navigation_suffix``
    holds the member name (``obj.bar()``).
    """
    if node is None:
        return []
    calls: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in call_types and n.children:
            callee = n.children[0]
            name = None
            if callee.type in _NAME_TYPES:
                name = _text(callee, source_bytes)
            elif callee.type == "navigation_expression":
                suffix = next(
                    (c for c in reversed(callee.children) if c.type == "navigation_suffix"),
                    None,
                )
                if suffix is not None:
                    ident = next((c for c in suffix.children if c.type in _NAME_TYPES), None)
                    if ident is not None:
                        name = _text(ident, source_bytes)
            if name:
                calls.add(name)
        stack.extend(n.children)
    return sorted(calls)[:MAX_CALLS]


def _clean_comment_line(text: str) -> str:
    """Strip comment markers (``///``, ``//!``, ``//``, ``#``, ``*``) from a line."""
    text = text.strip()
    for marker in ("///", "//!", "//", "#"):
        if text.startswith(marker):
            text = text[len(marker) :]
            break
    return text.strip().lstrip("*").strip()


def _clean_block_lines(raw: str) -> list[str]:
    """Clean a ``/* ... */`` block comment into its non-empty content lines."""
    text = raw.strip()
    for opener in ("/**", "/*"):
        if text.startswith(opener):
            text = text[len(opener) :]
            break
    text = text.removesuffix("*/")
    lines = [line.strip().lstrip("*").strip() for line in text.split("\n")]
    return [line for line in lines if line]


def collect_doc_comment(
    node,
    source_bytes: bytes,
    *,
    comment_types: tuple[str, ...],
    require_prefix: str | None = None,
    max_lines: int = 3,
) -> str | None:
    """Return the doc comment directly above ``node`` (first ``max_lines`` lines).

    Walks ``node.prev_sibling`` upward over contiguous comment nodes and returns
    the cleaned text, or ``None`` when there is no leading comment.

    Args:
        node: The declaration node (function/class/struct/...).
        source_bytes: Full source as UTF-8 bytes.
        comment_types: Node kinds that count as comments for this grammar
            (e.g. ``("comment",)`` for Go/Ruby, ``("line_comment",)`` for Rust,
            ``("documentation_comment",)`` for Dart).
        require_prefix: If set, a comment is only collected when its stripped
            text starts with this marker (``"///"`` for Rust/Dart doc comments,
            ``"#"`` for Ruby); the walk stops at the first non-matching line.
        max_lines: Maximum number of comment lines to keep.
    """
    collected: list[str] = []
    cur = node
    prev = cur.prev_sibling
    # Climb through wrapper nodes that start at the same byte as the node (e.g.
    # Ruby's ``body_statement`` wrapping its first ``method``) so the leading
    # comment sibling is reachable.
    while prev is None and cur.parent is not None and cur.parent.start_byte == cur.start_byte:
        cur = cur.parent
        prev = cur.prev_sibling

    target_row = cur.start_point[0] - 1
    while (
        prev is not None
        and prev.type in comment_types
        and prev.start_point[0] <= target_row <= prev.end_point[0]
    ):
        raw = _text(prev, source_bytes).strip()
        if require_prefix is not None and not raw.startswith(require_prefix):
            break
        if raw.startswith("/*"):
            # One multi-line block (``/** ... */``): append its lines in
            # reverse so the final list reversal restores document order.
            collected.extend(reversed(_clean_block_lines(raw)))
        else:
            cleaned = _clean_comment_line(raw)
            if cleaned:
                collected.append(cleaned)
        target_row = prev.start_point[0] - 1
        prev = prev.prev_sibling

    if not collected:
        return None
    collected.reverse()
    return "\n".join(collected[:max_lines])
