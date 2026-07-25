"""Ruby language spec for the generic tree-sitter extractor.

Port of the historical ``RubyAnalyzer``: methods (parent from the enclosing
class/module), singleton methods (``def self.x``), classes with superclass,
modules, and ``require``/``require_relative`` imports. Method bodies are not
descended into (nested defs were never extracted), and dependencies come from
the ``body_statement`` subtree only — default values in parameters don't count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..call_extraction import collect_ruby_calls
from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


def _ruby_calls(node: Node, source_bytes: bytes) -> list[str]:
    body = next((c for c in node.children if c.type == "body_statement"), None)
    return collect_ruby_calls(body, source_bytes)


def _method_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""
    params_node = ctx.child_by_type(node, "method_parameters")
    params = ctx.text(params_node) if params_node else ""
    return f"def {name}{params}"


def _singleton_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "identifier")
    name = ctx.text(name_node) if name_node else ""
    params_node = ctx.child_by_type(node, "method_parameters")
    params = ctx.text(params_node) if params_node else ""
    return f"def self.{name}{params}"


def _class_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "constant", "scope_resolution")
    name = ctx.text(name_node) if name_node else ""
    superclass = ""
    sup_node = ctx.child_by_type(node, "superclass")
    if sup_node:
        for child in sup_node.children:
            if child.type in ("constant", "scope_resolution"):
                superclass = f" < {ctx.text(child)}"
                break
    return f"class {name}{superclass}"


_VISIBILITY_MODIFIERS = ("private", "protected", "public")


def _method_visibility(node: Node, ctx: TreeSitterExtractor) -> str | None:
    """Visibility from the closest preceding modifier in the class body.

    In the language-pack grammar a bare ``private`` is a plain ``identifier``
    statement; other grammar versions parse it as a ``call``. Both forms are
    supported; no modifier means public (returned as None).
    """
    sibling = node.prev_named_sibling
    while sibling is not None:
        text: str | None = None
        if sibling.type == "identifier":
            text = ctx.text(sibling)
        elif sibling.type in ("call", "command", "method_call"):
            method = sibling.child_by_field_name("method")
            if method is not None:
                text = ctx.text(method)
        if text in _VISIBILITY_MODIFIERS:
            return None if text == "public" else text
        sibling = sibling.prev_named_sibling
    return None


def _collect_mixins(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    """Module names mixed in via ``include``/``extend``/``prepend``.

    Only statement-level calls in the direct class/module body count; ``extend
    self`` and dynamic arguments (non-constant) are skipped, mirroring
    CodeGraph's ruby.ts.
    """
    body = ctx.child_by_type(node, "body_statement")
    if body is None:
        return []
    mixins: list[str] = []
    for child in body.children:
        if child.type not in ("call", "command", "method_call"):
            continue
        if child.child_by_field_name("receiver") is not None:
            continue
        method = child.child_by_field_name("method")
        if method is None or ctx.text(method) not in ("include", "extend", "prepend"):
            continue
        args = ctx.child_by_type(child, "argument_list")
        if args is None:
            continue
        for arg in args.children:
            if arg.type in ("constant", "scope_resolution"):
                mixins.append(ctx.text(arg))
    return mixins


def _extract_class(node: Node, ctx: TreeSitterExtractor) -> str | bool:
    name_node = ctx.child_by_type(node, "constant", "scope_resolution")
    if name_node is None:
        return True
    name = ctx.text(name_node)
    ctx.emit(
        name=name,
        kind="class",
        node=node,
        signature=_class_signature(node, ctx),
        docstring=ctx.doc(node),
        parent=ctx.parent,
        mixins=_collect_mixins(node, ctx),
    )
    return name


def _extract_module(node: Node, ctx: TreeSitterExtractor) -> str | bool:
    # ``module Sidekiq::Middleware::I18n`` names are scope_resolution nodes.
    name_node = ctx.child_by_type(node, "constant", "scope_resolution")
    if name_node is None:
        return True
    name = ctx.text(name_node)
    ctx.emit(
        name=name,
        kind="module",
        node=node,
        signature=f"module {name}",
        parent=ctx.parent,
        mixins=_collect_mixins(node, ctx),
    )
    return name


def _classify_constant(node: Node, ctx: TreeSitterExtractor) -> str | None:
    """Only ``CONST = value`` assignments become symbols; locals are skipped."""
    left = node.child_by_field_name("left") or (node.children[0] if node.children else None)
    if left is not None and left.type == "constant":
        return "constant"
    return None


def _extract_require(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    """Record ``require`` / ``require_relative`` string arguments as imports."""
    name_node = ctx.child_by_type(node, "identifier")
    if name_node is None or ctx.text(name_node) not in ("require", "require_relative"):
        return []
    args = ctx.child_by_type(node, "argument_list")
    # command-style ``require "x"`` has the string as a direct child.
    search = args if args is not None else node
    for child in search.children:
        if child.type == "string":
            content = ctx.child_by_type(child, "string_content")
            if content is not None:
                return [ctx.text(content)]
            break
    return []


# Rails/Ruby class-body macros that declare invocable surface. A static parser
# that only sees ``def`` misses almost all of a typical ActiveRecord model — the
# associations, accessors, delegations and scopes are generated at load time by
# these macro calls. Extracting them is the single biggest coverage win in Ruby.
_ASSOCIATION_MACROS = frozenset({"belongs_to", "has_one", "has_many", "has_and_belongs_to_many"})
_ATTR_MACROS = frozenset({"attr_accessor", "attr_reader", "attr_writer"})


def _symbol_arg_text(node: Node, ctx: TreeSitterExtractor) -> str | None:
    """A ``:name`` argument's bare name, or None if it isn't a simple symbol."""
    if node.type == "simple_symbol":
        return ctx.text(node).lstrip(":")
    if node.type == "string":
        content = ctx.child_by_type(node, "string_content")
        return ctx.text(content) if content is not None else None
    return None


def _macro_args(node: Node, ctx: TreeSitterExtractor):
    """Split a macro call's arguments into leading names and keyword pairs."""
    args = node.child_by_field_name("arguments") or ctx.child_by_type(node, "argument_list")
    names: list[str] = []
    pairs: dict[str, str] = {}
    if args is None:
        return names, pairs
    for child in args.children:
        if child.type == "pair":
            kids = [c for c in child.children if c.type not in (":", ",")]
            if len(kids) >= 2:
                key = ctx.text(kids[0]).rstrip(":").strip()
                pairs[key] = _symbol_arg_text(kids[1], ctx) or ctx.text(kids[1]).strip()
        elif not pairs:
            name = _symbol_arg_text(child, ctx)
            if name:
                names.append(name)
    return names, pairs


def _extract_class_macro(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Emit the invocable methods a Rails/Ruby class-body macro generates.

    Runs on every class/module-body call (method bodies are never descended
    into, so this never fires on an ordinary in-method call). Non-macro calls
    fall through emitting nothing; children are still visited so DSL blocks that
    wrap real classes/modules keep working.
    """
    method_node = node.child_by_field_name("method")
    if method_node is None or ctx.parent is None:
        return True  # handled: suppress the generic emit, keep traversing children
    macro = ctx.text(method_node)
    signature = ctx.text(node).split("\n", 1)[0].strip()

    def emit(name: str, modifier: str) -> None:
        ctx.emit(
            name=name,
            kind="method",
            node=node,
            signature=signature,
            parent=ctx.parent,
            modifiers=[modifier],
        )

    if macro in _ASSOCIATION_MACROS:
        names, _ = _macro_args(node, ctx)
        if names:
            emit(names[0], f"association:{macro}")
    elif macro in _ATTR_MACROS:
        names, _ = _macro_args(node, ctx)
        for name in names:
            emit(name, "attr")
    elif macro == "scope":
        names, _ = _macro_args(node, ctx)
        if names:
            emit(names[0], "scope")
    elif macro == "delegate":
        names, pairs = _macro_args(node, ctx)
        prefix = ""
        raw_prefix = pairs.get("prefix")
        if raw_prefix == "true":
            prefix = f"{pairs.get('to', '')}_"
        elif raw_prefix:
            prefix = f"{raw_prefix}_"
        for name in names:
            emit(f"{prefix}{name}", "delegated")
    elif macro == "define_method":
        names, _ = _macro_args(node, ctx)
        if names:
            emit(names[0], "dynamic")
    # method_missing needs no handling here: it is a plain `def`, already
    # captured, and its dynamic targets are deliberately not invented.
    return True


SPEC = LanguageSpec(
    language="ruby",
    grammar="ruby",
    rules={
        "call": SymbolRule(kind="method", handler=_extract_class_macro),
        "command": SymbolRule(kind="method", handler=_extract_class_macro),
        "method_call": SymbolRule(kind="method", handler=_extract_class_macro),
        "method": SymbolRule(
            kind="method",
            name_child_types=("identifier",),
            classify=lambda node, ctx: "method" if ctx.parent else "function",
            signature=_method_signature,
            visit_children=False,
            visibility=_method_visibility,
        ),
        "singleton_method": SymbolRule(
            kind="method",
            name_child_types=("identifier",),
            signature=_singleton_signature,
            visit_children=False,
            visibility=_method_visibility,
        ),
        "class": SymbolRule(
            kind="class",
            handler=_extract_class,
            is_container=True,
            visit_children=False,
        ),
        "module": SymbolRule(
            kind="module",
            handler=_extract_module,
            is_container=True,
            visit_children=False,
        ),
        "assignment": SymbolRule(
            kind="constant",
            name_child_types=("constant",),
            classify=_classify_constant,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={
        "call": _extract_require,
        "command": _extract_require,
        "method_call": _extract_require,
    },
    doc=DocStyle(comment_types=("comment",), require_prefix="#"),
    calls=CallStyle(collector=_ruby_calls),
)
