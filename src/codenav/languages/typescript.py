"""TypeScript language spec for the generic tree-sitter extractor.

Reuses every JavaScript rule and adds the TS-specific constructs: interfaces
(with extends clause), type aliases, and enums (including ``const enum``).
The ``.tsx`` dialect resolves to the separate ``tsx`` grammar per file path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .javascript import IMPORT_RULES, RULES
from .spec import LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


def _interface_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""

    extends = ""
    child = ctx.child_by_type(node, "extends_type_clause")
    if child:
        extends = f" {ctx.text(child)}"

    type_params = ""
    child = ctx.child_by_type(node, "type_parameters")
    if child:
        type_params = ctx.text(child)

    return f"interface {name}{type_params}{extends}"


def _type_alias_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""

    type_params = ""
    child = ctx.child_by_type(node, "type_parameters")
    if child:
        type_params = ctx.text(child)

    # The aliased type (simplified, first 50 chars).
    type_value = ""
    for i, child in enumerate(node.children):
        if child.type == "=":
            remaining = node.children[i + 1 :]
            if remaining:
                type_value = ctx.text(remaining[0])[:50]
            break

    return f"type {name}{type_params} = {type_value}"


def _enum_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""
    prefix = "const " if any(c.type == "const" for c in node.children) else ""
    return f"{prefix}enum {name}"


def _grammar_for_path(file_path: str) -> str:
    return "tsx" if file_path.lower().endswith(".tsx") else "typescript"


SPEC = LanguageSpec(
    language="typescript",
    grammar="typescript",
    grammar_for_path=_grammar_for_path,
    rules={
        **RULES,
        "interface_declaration": SymbolRule(
            kind="interface",
            name_child_types=("type_identifier",),
            signature=_interface_signature,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "type_alias_declaration": SymbolRule(
            kind="type",
            name_child_types=("type_identifier",),
            signature=_type_alias_signature,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
        "enum_declaration": SymbolRule(
            kind="enum",
            name_child_types=("identifier",),
            signature=_enum_signature,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
        ),
    },
    import_rules=IMPORT_RULES,
)
