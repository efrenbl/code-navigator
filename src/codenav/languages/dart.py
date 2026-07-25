"""Dart/Flutter language spec for the generic tree-sitter extractor.

Port of the historical ``DartAnalyzer``: classes (with abstract/superclass),
mixins, enums, extensions (named or ``<anonymous>``), top-level functions,
methods, constructors, and import URIs. The Dart grammar splits a function
into a signature node and a sibling body, so the call collector walks
``node.next_sibling``; top-level functions are ``function_signature`` nodes
that only count when no class scope is active.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..call_extraction import collect_dart_calls
from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


def _dart_calls(node: Node, source_bytes: bytes) -> list[str]:
    # The body is the signature node's sibling (``function_body``).
    return collect_dart_calls(node.next_sibling, source_bytes)


def _return_type(target: Node, ctx: TreeSitterExtractor) -> str:
    for child in target.children:
        if child.type in ("type_identifier", "void_type", "nullable_type"):
            return ctx.text(child) + " "
    return ""


def _visibility_of(name: str) -> str | None:
    """Dart convention: a leading underscore makes a name library-private."""
    return "private" if name.startswith("_") else None


def _name_visibility(node: Node, ctx: TreeSitterExtractor) -> str | None:
    name_node = ctx.child_by_type(node, "identifier", "type_identifier")
    return _visibility_of(ctx.text(name_node)) if name_node is not None else None


def _signature_return_type(sig: Node, ctx: TreeSitterExtractor) -> str | None:
    """Declared return type, reduced to the container type name.

    ``Future<String>`` → ``Future`` (type_arguments are sibling nodes in this
    grammar, so the ``type_identifier`` text is already bare); ``p.Bar`` → last
    segment.
    """
    for child in sig.children:
        if child.type == "type_identifier":
            return ctx.text(child).split(".")[-1] or None
    return None


def _extract_class(node: Node, ctx: TreeSitterExtractor) -> str | bool:
    name_node = ctx.child_by_type(node, "identifier")
    if not name_node:
        return True  # Unnamed class: skip the whole subtree (historical behavior).
    name = ctx.text(name_node)

    is_abstract = any(c.type == "abstract" for c in node.children)
    prefix = "abstract " if is_abstract else ""
    signature = f"{prefix}class {name}"
    supertype = ctx.child_by_type(node, "superclass", "supertype")
    if supertype:
        signature += f" {ctx.text(supertype)}"

    ctx.emit(
        name=name,
        kind="class",
        node=node,
        signature=signature,
        docstring=ctx.doc(node),
        visibility=_visibility_of(name),
        modifiers=["abstract"] if is_abstract else None,
    )
    return name


def _extract_extension(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else "<anonymous>"

    on_type = ""
    for i, child in enumerate(node.children):
        if child.type == "on":
            rest = node.children[i + 1 :]
            if rest:
                on_type = f" on {ctx.text(rest[0])}"
            break

    ctx.emit(name=name, kind="extension", node=node, signature=f"extension {name}{on_type}")
    return name


def _body_is_async(node: Node) -> bool:
    """The ``async``/``async*``/``sync*`` marker lives on the sibling body node."""
    body = node.next_sibling
    if body is None or body.type != "function_body":
        return False
    return any(c.type in ("async", "async*", "sync*") for c in body.children)


def _emit_constructor(ctor: Node, emit_node: Node, ctx: TreeSitterExtractor) -> bool:
    """Emit a (factory/named/plain) constructor found at ``ctor``.

    ``Foo.create`` names the symbol ``create`` (so lookups hit the named
    constructor, not the class); a plain ``Foo()`` keeps the class name. The
    first identifier must match the enclosing class — CodeGraph's guard
    against tree-sitter misparsing ``@override (T) m()`` as a constructor.
    """
    ids = [c for c in ctor.children if c.type == "identifier"]
    if not ids:
        return True
    class_name = ctx.text(ids[0])
    if ctx.parent is None or class_name != ctx.parent:
        return True
    is_factory = any(c.type == "factory" for c in ctor.children)
    name = ctx.text(ids[1]) if len(ids) > 1 else class_name
    modifiers = ["factory"] if is_factory else []
    if _body_is_async(emit_node):
        modifiers.append("async")
    ctx.emit(
        name=name,
        kind="constructor",
        node=emit_node,
        signature=ctx.text(ctor).split("\n", 1)[0].strip(),
        parent=ctx.parent,
        docstring=ctx.doc(emit_node),
        dependencies=ctx.calls(emit_node) if is_factory else None,
        visibility=_visibility_of(name),
        modifiers=modifiers,
        return_type=class_name,
    )
    return True


def _extract_constructor(node: Node, ctx: TreeSitterExtractor) -> bool:
    return _emit_constructor(node, node, ctx)


def _extract_method(node: Node, ctx: TreeSitterExtractor) -> bool:
    ctor = ctx.child_by_type(
        node,
        "factory_constructor_signature",
        "constructor_signature",
        "constant_constructor_signature",
    )
    if ctor is not None:
        return _emit_constructor(ctor, node, ctx)

    getter = ctx.child_by_type(node, "getter_signature")
    setter = ctx.child_by_type(node, "setter_signature")
    func_sig = ctx.child_by_type(node, "function_signature")
    target = getter or setter or func_sig or node
    name_node = ctx.child_by_type(target, "identifier")
    if not name_node:
        return True

    name = ctx.text(name_node)
    modifiers = []
    if any(c.type == "static" for c in node.children):
        modifiers.append("static")
    if _body_is_async(node):
        modifiers.append("async")
    if getter is not None:
        modifiers.append("getter")
        signature = ctx.text(node).split("\n", 1)[0].strip()
    elif setter is not None:
        modifiers.append("setter")
        signature = ctx.text(node).split("\n", 1)[0].strip()
    else:
        signature = f"{_return_type(target, ctx)}{name}()"
    ctx.emit(
        name=name,
        kind="method",
        node=node,
        signature=signature,
        parent=ctx.parent,
        docstring=ctx.doc(node),
        dependencies=ctx.calls(node),
        visibility=_visibility_of(name),
        modifiers=modifiers,
        return_type=_signature_return_type(target, ctx),
    )
    return True


def _extract_import(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    """Record the URI of an ``import`` directive (quotes stripped)."""
    uri = ctx.child_by_type(node, "configurable_uri")
    if uri is None:
        return []
    inner = ctx.child_by_type(uri, "uri")
    target = inner if inner is not None else uri
    spec = ctx.text(target).strip("'\"")
    return [spec] if spec else []


SPEC = LanguageSpec(
    language="dart",
    grammar="dart",
    rules={
        "class_definition": SymbolRule(
            kind="class", handler=_extract_class, is_container=True, visit_children=False
        ),
        "mixin_declaration": SymbolRule(
            kind="mixin",
            name_child_types=("identifier",),
            signature=lambda node, ctx: "mixin "
            + ctx.text(ctx.child_by_type(node, "identifier") or node),
            is_container=True,
            visit_children=False,
            inherit_parent=False,
            collect_calls=False,
            visibility=_name_visibility,
        ),
        "enum_declaration": SymbolRule(
            kind="enum",
            name_child_types=("identifier",),
            signature=lambda node, ctx: "enum "
            + ctx.text(ctx.child_by_type(node, "identifier") or node),
            is_container=True,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
            visibility=_name_visibility,
        ),
        "enum_constant": SymbolRule(
            kind="enum_member",
            name_child_types=("identifier",),
            collect_calls=False,
        ),
        "extension_declaration": SymbolRule(
            kind="extension", handler=_extract_extension, is_container=True, visit_children=False
        ),
        "type_alias": SymbolRule(
            kind="type",
            name_child_types=("type_identifier",),
            collect_calls=False,
            visibility=_name_visibility,
        ),
        "static_final_declaration": SymbolRule(
            kind="const",
            name_child_types=("identifier",),
            collect_calls=False,
            collect_doc=False,
            visibility=_name_visibility,
        ),
        "function_signature": SymbolRule(
            kind="function",
            name_child_types=("identifier",),
            # Wrapped in a method_signature → already emitted by its handler.
            # Bare inside a class body (abstract/interface method declaration,
            # e.g. ``void save(Book book);``) → method. Top level → function.
            classify=lambda node, ctx: (
                None
                if node.parent is not None and node.parent.type == "method_signature"
                else ("method" if ctx.parent else "function")
            ),
            signature=lambda node, ctx: _return_type(node, ctx)
            + ctx.text(ctx.child_by_type(node, "identifier") or node)
            + "()",
            visibility=_name_visibility,
            modifiers=lambda node, ctx: ["async"] if _body_is_async(node) else None,
            return_type=_signature_return_type,
        ),
        "method_signature": SymbolRule(kind="method", handler=_extract_method),
        "constant_constructor_signature": SymbolRule(
            kind="constructor", handler=_extract_constructor
        ),
        "constructor_signature": SymbolRule(kind="constructor", handler=_extract_constructor),
    },
    import_rules={
        "import_specification": _extract_import,
        "library_export": _extract_import,
    },
    doc=DocStyle(comment_types=("documentation_comment",), require_prefix="///"),
    calls=CallStyle(collector=_dart_calls),
)
