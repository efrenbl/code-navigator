"""PHP language spec for the generic tree-sitter extractor.

Functions, classes/interfaces/traits/enums (containers for their methods),
namespaces, ``use`` imports plus ``require``/``include`` expressions, and
``/** ... */`` docblocks. Callees come from three call node shapes:
``function_call_expression`` (callee field ``function``) and
``member_call_expression``/``scoped_call_expression`` (callee field ``name``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule, first_code_line_signature

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

_signature = first_code_line_signature("#[")

_CALL_FIELDS = {
    "function_call_expression": "function",
    "member_call_expression": "name",
    "scoped_call_expression": "name",
}

_MAX_CALLS = 50


def _php_calls(node: Node, source_bytes: bytes) -> list[str]:
    calls: set[str] = set()
    stack = [node]
    while stack:
        n = stack.pop()
        field = _CALL_FIELDS.get(n.type)
        if field:
            callee = n.child_by_field_name(field)
            if callee is not None:
                if callee.type == "qualified_name":
                    callee = next(
                        (c for c in reversed(callee.children) if c.type == "name"), callee
                    )
                if callee.type in ("name", "identifier"):
                    calls.add(
                        source_bytes[callee.start_byte : callee.end_byte].decode("utf-8", "replace")
                    )
        stack.extend(n.children)
    return sorted(calls)[:_MAX_CALLS]


def _use_declaration(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    specs = []
    for child in node.children:
        if child.type == "namespace_use_clause" and child.children:
            spec = ctx.text(child.children[0])
            if spec:
                specs.append(spec)
    return specs


def _require_expression(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    string = ctx.child_by_type(node, "string", "encapsed_string")
    if string is None:
        return []
    content = ctx.child_by_type(string, "string_content")
    if content is None:
        return []
    spec = ctx.text(content)
    return [spec] if spec else []


def _container_rule(kind: str) -> SymbolRule:
    return SymbolRule(
        kind=kind,
        name_fields=("name",),
        signature=_signature,
        is_container=True,
        visit_children=False,
        inherit_parent=False,
        collect_calls=False,
    )


SPEC = LanguageSpec(
    language="php",
    grammar="php",
    rules={
        "class_declaration": _container_rule("class"),
        "interface_declaration": _container_rule("interface"),
        "trait_declaration": _container_rule("trait"),
        "enum_declaration": _container_rule("enum"),
        "function_definition": SymbolRule(
            kind="function", signature=_signature, inherit_parent=False
        ),
        "method_declaration": SymbolRule(kind="method", signature=_signature),
        "namespace_definition": SymbolRule(
            kind="module",
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={
        "namespace_use_declaration": _use_declaration,
        "require_expression": _require_expression,
        "require_once_expression": _require_expression,
        "include_expression": _require_expression,
        "include_once_expression": _require_expression,
    },
    doc=DocStyle(comment_types=("comment",), require_prefix="/**"),
    calls=CallStyle(collector=_php_calls),
)
