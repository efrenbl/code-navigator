"""Go language spec for the generic tree-sitter extractor.

Port of the historical ``GoAnalyzer`` symbol extraction: functions, methods
(with receiver-derived parent), struct/interface/type specs, consts, and
``import_spec`` package paths. Hooks preserve the exact signature formats the
old analyzer produced.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from collections.abc import Callable

    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


def _function_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""

    type_params = ""
    tp_node = ctx.child_by_type(node, "type_parameter_list")
    if tp_node:
        type_params = ctx.text(tp_node)

    params = ""
    for child in node.children:
        if child.type == "parameter_list":
            params = ctx.text(child)
            break

    result = ""
    for child in node.children:
        if child.type in (
            "type_identifier",
            "slice_type",
            "pointer_type",
            "qualified_type",
            "map_type",
            "parameter_list",
        ):
            # Skip the first parameter_list (that's the params)
            if child.type == "parameter_list" and child == node.children[2]:
                continue
            if child.start_byte > (node.children[2].end_byte if len(node.children) > 2 else 0):
                result = " " + ctx.text(child)
                break

    return f"func {name}{type_params}{params}{result}"


def _visibility_of(name: str) -> str | None:
    """Go convention: lowercase initial → unexported (private)."""
    return "private" if name and name[0].islower() else None


def _name_visibility(node: Node, ctx: TreeSitterExtractor) -> str | None:
    name_node = node.child_by_field_name("name") or ctx.child_by_type(node, "identifier")
    return _visibility_of(ctx.text(name_node)) if name_node else None


def _receiver_type_name(receiver: Node, ctx: TreeSitterExtractor) -> str | None:
    """Type name of a method receiver: ``(u *User)``, ``(s *Stack[T])`` → Stack."""
    for child in receiver.children:
        if child.type != "parameter_declaration":
            continue
        for rc in child.children:
            if rc.type == "type_identifier":
                return ctx.text(rc)
            if rc.type in ("pointer_type", "generic_type"):
                # *User → User; *Stack[T] / Stack[T] → Stack (#583-style fix:
                # generic receivers used to leave the method orphaned).
                inner: Node | None = rc
                while inner is not None and inner.type in ("pointer_type", "generic_type"):
                    inner = ctx.child_by_type(inner, "type_identifier", "generic_type")
                if inner is not None:
                    return ctx.text(inner)
    return None


def _return_type(node: Node, ctx: TreeSitterExtractor) -> str | None:
    """Normalized declared return type, per the CodeGraph #645/#608 mechanism.

    ``*Foo`` → ``Foo``; multi-return ``(*Foo, error)`` → first result;
    ``pkg.Foo`` → ``Foo``; generics stripped. Built-ins/unnamed shapes that
    don't reduce to a bare identifier return None.
    """
    result = node.child_by_field_name("result")
    if result is None:
        return None
    if result.type == "parameter_list":
        first = ctx.child_by_type(result, "parameter_declaration")
        if first is None:
            return None
        result = first.child_by_field_name("type") or first
    if result.type == "pointer_type":
        result = (
            ctx.child_by_type(result, "type_identifier", "qualified_type", "generic_type") or result
        )
    text = ctx.text(result).strip().lstrip("*")
    text = re.sub(r"\[[^\]]*\]", "", text)
    last = text.split(".")[-1].strip()
    return last if re.fullmatch(r"[A-Za-z_]\w*", last) else None


def _extract_method(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Extract a method declaration with its receiver type as parent."""
    name_node = ctx.child_by_type(node, "field_identifier")
    if not name_node:
        return True

    name = ctx.text(name_node)

    receiver = node.child_by_field_name("receiver")
    parent = _receiver_type_name(receiver, ctx) if receiver is not None else None

    params_node = node.child_by_field_name("parameters")
    params = ctx.text(params_node) if params_node is not None else ""

    receiver_str = f"{ctx.text(receiver)} " if receiver is not None else ""
    signature = f"func {receiver_str}{name}{params}"

    ctx.emit(
        name=name,
        kind="method",
        node=node,
        signature=signature,
        parent=parent,
        docstring=ctx.doc(node),
        dependencies=ctx.calls(node),
        visibility=_visibility_of(name),
        return_type=_return_type(node, ctx),
    )
    return True


def _extract_type_spec(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Extract a type specification (struct, interface, or alias)."""
    name_node = ctx.child_by_type(node, "type_identifier")
    if not name_node:
        return True

    name = ctx.text(name_node)

    struct_node = ctx.child_by_type(node, "struct_type")
    iface_node = ctx.child_by_type(node, "interface_type")

    if struct_node:
        symbol_type = "struct"
        signature = f"type {name} struct"
    elif iface_node:
        symbol_type = "interface"
        signature = f"type {name} interface"
    else:
        symbol_type = "type"
        for child in node.children:
            if child.type == "type_identifier" and child != name_node:
                signature = f"type {name} {ctx.text(child)}"
                break
        else:
            signature = f"type {name}"

    # The doc comment sits above the wrapping ``type_declaration``.
    doc_node = node.parent if node.parent is not None else node
    ctx.emit(
        name=name,
        kind=symbol_type,
        node=node,
        signature=signature,
        docstring=ctx.doc(doc_node),
        visibility=_visibility_of(name),
    )

    # Interface method set: each method_elem is a method parented to the
    # interface (embedded interfaces — type_elem — are not symbols).
    if iface_node is not None:
        for child in iface_node.children:
            if child.type != "method_elem":
                continue
            m_name_node = ctx.child_by_type(child, "field_identifier")
            if m_name_node is None:
                continue
            m_name = ctx.text(m_name_node)
            ctx.emit(
                name=m_name,
                kind="method",
                node=child,
                signature=ctx.text(child).split("\n", 1)[0].strip(),
                parent=name,
                docstring=ctx.doc(child),
                visibility=_visibility_of(m_name),
                return_type=_return_type(child, ctx),
            )
    return True


def _extract_value_spec(kind: str) -> Callable[[Node, TreeSitterExtractor], bool]:
    """Handler for ``var_spec``/``const_spec`` — one symbol per declared name.

    A spec can declare several names (``var a, b = 1, 2``). Vars are only
    emitted at package level (function locals would flood the map); consts
    keep their historical any-level behavior. The doc comment lives above the
    wrapping declaration for single specs, above the spec inside ``var (...)``
    blocks.
    """

    def handler(node: Node, ctx: TreeSitterExtractor) -> bool:
        decl = node.parent
        if kind == "variable":
            if decl is None or decl.parent is None or decl.parent.type != "source_file":
                return True
        signature = ctx.text(node).split("\n", 1)[0].strip()
        specs_in_decl = (
            sum(1 for c in decl.children if c.type == node.type) if decl is not None else 1
        )
        doc_node = decl if (decl is not None and specs_in_decl == 1) else node
        for child in node.children:
            if child.type != "identifier":
                continue
            name = ctx.text(child)
            ctx.emit(
                name=name,
                kind=kind,
                node=node,
                signature=signature,
                docstring=ctx.doc(doc_node),
                visibility=_visibility_of(name),
            )
        return True

    return handler


def _import_spec(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    child = ctx.child_by_type(node, "interpreted_string_literal")
    if child is None:
        return []
    spec = ctx.text(child).strip('"')
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="go",
    grammar="go",
    rules={
        "function_declaration": SymbolRule(
            kind="function",
            name_child_types=("identifier",),
            signature=_function_signature,
            visibility=_name_visibility,
            return_type=_return_type,
        ),
        "method_declaration": SymbolRule(kind="method", handler=_extract_method),
        "type_spec": SymbolRule(kind="type", handler=_extract_type_spec),
        "const_spec": SymbolRule(kind="const", handler=_extract_value_spec("const")),
        "var_spec": SymbolRule(kind="variable", handler=_extract_value_spec("variable")),
    },
    import_rules={"import_spec": _import_spec},
    doc=DocStyle(comment_types=("comment",), require_prefix="//"),
    calls=CallStyle(),
)
