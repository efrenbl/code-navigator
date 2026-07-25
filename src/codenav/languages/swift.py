"""Swift language spec for the generic tree-sitter extractor.

The Swift grammar (alex-pinkus) folds class/struct/enum/extension into one
``class_declaration`` node — a classify hook reads the keyword token.
Protocols are containers whose ``protocol_function_declaration`` members
become methods; ``init_declaration`` becomes a constructor. Calls are
positional like Kotlin; docs are ``///`` line comments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..call_extraction import collect_positional_calls
from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule, first_code_line_signature

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

_signature = first_code_line_signature("@")

_KEYWORD_KINDS = {"class": "class", "struct": "struct", "enum": "enum", "extension": "extension"}


def _classify_class(node: Node, ctx: TreeSitterExtractor) -> str:
    for child in node.children:
        kind = _KEYWORD_KINDS.get(child.type)
        if kind:
            return kind
    return "class"


def _import_declaration(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    child = ctx.child_by_type(node, "identifier")
    if child is None:
        return []
    spec = ctx.text(child)
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="swift",
    grammar="swift",
    rules={
        "class_declaration": SymbolRule(
            kind="class",
            name_fields=("name",),
            name_child_types=("type_identifier", "user_type"),
            classify=_classify_class,
            signature=_signature,
            is_container=True,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "protocol_declaration": SymbolRule(
            kind="protocol",
            name_child_types=("type_identifier",),
            signature=_signature,
            is_container=True,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "function_declaration": SymbolRule(
            kind="function",
            name_fields=("name",),
            name_child_types=("simple_identifier",),
            classify=lambda node, ctx: "method" if ctx.parent else "function",
            signature=_signature,
        ),
        "protocol_function_declaration": SymbolRule(
            kind="method",
            name_fields=("name",),
            name_child_types=("simple_identifier",),
            signature=_signature,
            collect_calls=False,
        ),
        "init_declaration": SymbolRule(
            kind="constructor",
            name_fields=("name",),
            signature=_signature,
        ),
        "typealias_declaration": SymbolRule(
            kind="type",
            name_fields=("name",),
            name_child_types=("type_identifier",),
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={"import_declaration": _import_declaration},
    doc=DocStyle(comment_types=("comment", "multiline_comment"), require_prefix="///"),
    calls=CallStyle(collector=collect_positional_calls),
)
