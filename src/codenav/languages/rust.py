"""Rust language spec for the generic tree-sitter extractor.

Port of the historical ``RustAnalyzer``: functions/methods (parent from the
enclosing ``impl`` block), structs, enums, traits, impl blocks, type aliases,
consts, modules, and ``use`` declarations. Only functions inherit the impl
scope as parent — other kinds never carried one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


def _pub(node: Node, ctx: TreeSitterExtractor) -> str:
    return "pub " if ctx.child_by_type(node, "visibility_modifier") else ""


def _type_params(node: Node, ctx: TreeSitterExtractor) -> str:
    tp = ctx.child_by_type(node, "type_parameters")
    return ctx.text(tp) if tp else ""


def _is_async(node: Node, ctx: TreeSitterExtractor) -> bool:
    mods = ctx.child_by_type(node, "function_modifiers")
    if mods:
        for child in mods.children:
            if child.type == "async":
                return True
    return False


def _function_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""

    async_prefix = "async " if _is_async(node, ctx) else ""

    params = ""
    params_node = ctx.child_by_type(node, "parameters")
    if params_node:
        params = ctx.text(params_node)

    ret = ""
    for i, child in enumerate(node.children):
        if child.type == "->":
            remaining = [c for c in node.children[i + 1 :] if c.type != "block"]
            if remaining:
                ret = " -> " + ctx.text(remaining[0])
            break

    return f"{_pub(node, ctx)}{async_prefix}fn {name}{_type_params(node, ctx)}{params}{ret}"


def _struct_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""
    return f"{_pub(node, ctx)}struct {name}{_type_params(node, ctx)}"


def _enum_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""
    return f"{_pub(node, ctx)}enum {name}"


def _trait_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""
    return f"{_pub(node, ctx)}trait {name}{_type_params(node, ctx)}"


def _type_alias_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "type_identifier")
    name = ctx.text(name_node) if name_node else ""
    return f"{_pub(node, ctx)}type {name}{_type_params(node, ctx)}"


def _const_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""
    return f"{_pub(node, ctx)}const {name}"


def _extract_impl(node: Node, ctx: TreeSitterExtractor) -> str | bool:
    """Emit the impl symbol; the returned type name becomes the method scope."""
    # For "impl Type", the scope is Type; for "impl Trait for Type", the target Type.
    impl_type = None
    trait_name = None

    type_ids = [c for c in node.children if c.type == "type_identifier"]
    scoped_ids = [c for c in node.children if c.type == "scoped_type_identifier"]
    has_for = any(c.type == "for" for c in node.children)

    if has_for:
        if len(type_ids) >= 1:
            impl_type = ctx.text(type_ids[-1])
        if scoped_ids:
            trait_name = ctx.text(scoped_ids[0])
        elif len(type_ids) >= 2:
            trait_name = ctx.text(type_ids[0])
    else:
        if type_ids:
            impl_type = ctx.text(type_ids[0])

    if not impl_type:
        return True  # Anonymous impl: no symbol, body visited without scope.

    type_params = _type_params(node, ctx)
    if trait_name:
        signature = f"impl {trait_name} for {impl_type}{type_params}"
    else:
        signature = f"impl {impl_type}{type_params}"

    ctx.emit(name=impl_type, kind="impl", node=node, signature=signature)
    return impl_type


def _use_declaration(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    for child in node.children:
        if child.type in (
            "scoped_identifier",
            "identifier",
            "use_wildcard",
            "scoped_use_list",
            "use_list",
            "use_as_clause",
        ):
            spec = ctx.text(child)
            return [spec] if spec else []
    return []


SPEC = LanguageSpec(
    language="rust",
    grammar="rust",
    rules={
        "function_item": SymbolRule(
            kind="function",
            name_child_types=("identifier",),
            classify=lambda node, ctx: "method" if ctx.parent else "function",
            signature=_function_signature,
        ),
        "struct_item": SymbolRule(
            kind="struct",
            name_child_types=("type_identifier",),
            signature=_struct_signature,
            inherit_parent=False,
            collect_calls=False,
        ),
        "enum_item": SymbolRule(
            kind="enum",
            name_child_types=("type_identifier",),
            signature=_enum_signature,
            inherit_parent=False,
            collect_calls=False,
        ),
        "trait_item": SymbolRule(
            kind="trait",
            name_child_types=("type_identifier",),
            signature=_trait_signature,
            inherit_parent=False,
            collect_calls=False,
        ),
        "impl_item": SymbolRule(kind="impl", handler=_extract_impl, is_container=True),
        "type_item": SymbolRule(
            kind="type",
            name_child_types=("type_identifier",),
            signature=_type_alias_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "const_item": SymbolRule(
            kind="const",
            name_child_types=("identifier",),
            signature=_const_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "mod_item": SymbolRule(
            kind="module",
            name_child_types=("identifier",),
            signature=lambda node, ctx: "mod "
            + ctx.text(ctx.child_by_type(node, "identifier") or node),
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={"use_declaration": _use_declaration},
    doc=DocStyle(comment_types=("line_comment",), require_prefix="///"),
    calls=CallStyle(macro_types=("macro_invocation",)),
)
