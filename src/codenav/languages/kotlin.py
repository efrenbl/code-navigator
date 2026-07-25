"""Kotlin language spec for the generic tree-sitter extractor.

The Kotlin grammar exposes no field names, so symbol names resolve by child
node type (``simple_identifier``/``type_identifier``). ``class_declaration``
covers regular, data, enum and ``fun interface`` classes — a classify hook
inspects the keyword tokens. Calls are positional (``call_expression`` with
the callee as first child); KDoc is a ``/** ... */`` multiline comment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..call_extraction import collect_positional_calls
from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule, first_code_line_signature

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

_signature = first_code_line_signature("@")


def _classify_class(node: Node, ctx: TreeSitterExtractor) -> str:
    kinds = {child.type for child in node.children}
    if "interface" in kinds:
        return "interface"
    if "enum" in kinds:
        return "enum"
    return "class"


def _import_header(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    child = ctx.child_by_type(node, "identifier")
    if child is None:
        return []
    spec = ctx.text(child)
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="kotlin",
    grammar="kotlin",
    rules={
        "class_declaration": SymbolRule(
            kind="class",
            name_child_types=("type_identifier",),
            classify=_classify_class,
            signature=_signature,
            is_container=True,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "object_declaration": SymbolRule(
            kind="class",
            name_child_types=("type_identifier",),
            signature=_signature,
            is_container=True,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "function_declaration": SymbolRule(
            kind="function",
            name_child_types=("simple_identifier",),
            classify=lambda node, ctx: "method" if ctx.parent else "function",
            signature=_signature,
        ),
        "type_alias": SymbolRule(
            kind="type",
            name_child_types=("type_identifier",),
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={"import_header": _import_header},
    doc=DocStyle(comment_types=("multiline_comment",), require_prefix="/**"),
    calls=CallStyle(collector=collect_positional_calls),
)
