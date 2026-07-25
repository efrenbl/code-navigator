"""C language spec for the generic tree-sitter extractor.

Function definitions and prototypes (the name sits at the bottom of a
declarator chain — ``pointer_declarator`` → ``function_declarator`` →
``identifier``), structs/enums/unions (skipping bodyless forward
declarations and type references), typedefs, and ``#include`` directives.
Any adjacent ``//`` or ``/* */`` comment counts as documentation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

_DECLARATOR_NAME_TYPES = ("identifier", "field_identifier", "type_identifier")


def unwrap_declarator(node: Node) -> Node | None:
    """Follow the ``declarator`` field chain down to the name node.

    Returns the ``identifier``/``field_identifier`` (or, in C++, the
    ``qualified_identifier`` for out-of-line members), unwrapping pointer,
    reference and function declarators along the way.
    """
    current = node.child_by_field_name("declarator")
    while current is not None:
        if current.type in _DECLARATOR_NAME_TYPES or current.type == "qualified_identifier":
            return current
        nxt = current.child_by_field_name("declarator")
        if nxt is None:
            nxt = next(
                (c for c in current.children if c.type in _DECLARATOR_NAME_TYPES),
                None,
            )
        current = nxt
    return None


def has_function_declarator(node: Node) -> bool:
    """Whether the ``declarator`` chain of ``node`` contains a function declarator."""
    current = node.child_by_field_name("declarator")
    while current is not None:
        if current.type == "function_declarator":
            return True
        current = current.child_by_field_name("declarator")
    return False


def _name_and_parent(node: Node, ctx: TreeSitterExtractor) -> tuple[str | None, str | None]:
    name_node = unwrap_declarator(node)
    if name_node is None:
        return None, None
    if name_node.type == "qualified_identifier":
        # C++ out-of-line member: ``User::greet`` → name greet, parent User.
        inner = name_node.child_by_field_name("name")
        scope = name_node.child_by_field_name("scope")
        return (
            ctx.text(inner) if inner is not None else None,
            ctx.text(scope) if scope is not None else None,
        )
    return ctx.text(name_node), ctx.parent


def _function_kind(name: str, parent: str | None) -> str:
    if parent is None:
        return "function"
    return "constructor" if name == parent else "method"


def extract_function_definition(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Shared C/C++ handler for ``function_definition`` nodes."""
    name, parent = _name_and_parent(node, ctx)
    if not name:
        return True
    ctx.emit(
        name=name,
        kind=_function_kind(name, parent),
        node=node,
        signature=ctx._default_signature(node),
        parent=parent,
        docstring=ctx.doc(node),
        dependencies=ctx.calls(node),
    )
    return True


def extract_function_declaration(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Shared C/C++ handler for prototypes (``declaration``/``field_declaration``).

    Only declarations whose declarator chain contains a function declarator
    count — plain variables and data members are skipped.
    """
    if not has_function_declarator(node):
        return True
    name, parent = _name_and_parent(node, ctx)
    if not name:
        return True
    ctx.emit(
        name=name,
        kind=_function_kind(name, parent),
        node=node,
        signature=ctx._default_signature(node).rstrip(";"),
        parent=parent,
        docstring=ctx.doc(node),
    )
    return True


def specifier_classify(kind: str):
    """Emit ``kind`` only for definitions with a body — reference uses of
    ``struct foo`` and forward declarations produce no symbol."""

    def classify(node: Node, ctx: TreeSitterExtractor) -> str | None:
        return kind if node.child_by_field_name("body") is not None else None

    return classify


def extract_include(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    child = ctx.child_by_type(node, "string_literal", "system_lib_string")
    if child is None:
        return []
    spec = ctx.text(child).strip('"<>')
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="c",
    grammar="c",
    rules={
        "function_definition": SymbolRule(kind="function", handler=extract_function_definition),
        "declaration": SymbolRule(kind="function", handler=extract_function_declaration),
        "struct_specifier": SymbolRule(
            kind="struct",
            classify=specifier_classify("struct"),
            inherit_parent=False,
            collect_calls=False,
        ),
        "enum_specifier": SymbolRule(
            kind="enum",
            classify=specifier_classify("enum"),
            inherit_parent=False,
            collect_calls=False,
        ),
        "union_specifier": SymbolRule(
            kind="union",
            classify=specifier_classify("union"),
            inherit_parent=False,
            collect_calls=False,
        ),
        "type_definition": SymbolRule(
            kind="type",
            name_fields=("declarator",),
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={"preproc_include": extract_include},
    doc=DocStyle(comment_types=("comment",)),
    calls=CallStyle(),
)
