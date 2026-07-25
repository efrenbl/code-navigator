"""Java language spec for the generic tree-sitter extractor.

Classes, records, interfaces, annotation types, enums, methods and
constructors (parent from the enclosing type), ``import`` declarations, and
Javadoc ``/** ... */`` blocks. Callees come from ``method_invocation`` nodes,
whose callee lives in the ``name`` field (not ``function``).
"""

from __future__ import annotations

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule, first_code_line_signature

_signature = first_code_line_signature("@")


def _type_rule(kind: str) -> SymbolRule:
    return SymbolRule(
        kind=kind,
        signature=_signature,
        is_container=True,
        visit_children=False,
        inherit_parent=False,
        collect_calls=False,
    )


def _import_declaration(node, ctx):
    child = ctx.child_by_type(node, "scoped_identifier", "identifier")
    if child is None:
        return []
    spec = ctx.text(child)
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="java",
    grammar="java",
    rules={
        "class_declaration": _type_rule("class"),
        "record_declaration": _type_rule("class"),
        "interface_declaration": _type_rule("interface"),
        "annotation_type_declaration": _type_rule("interface"),
        "enum_declaration": _type_rule("enum"),
        "method_declaration": SymbolRule(kind="method", signature=_signature),
        "constructor_declaration": SymbolRule(kind="constructor", signature=_signature),
    },
    import_rules={"import_declaration": _import_declaration},
    doc=DocStyle(comment_types=("block_comment", "comment"), require_prefix="/**"),
    calls=CallStyle(call_types=("method_invocation",), callee_field="name"),
)
