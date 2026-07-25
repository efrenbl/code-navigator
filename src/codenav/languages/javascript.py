"""JavaScript language spec for the generic tree-sitter extractor.

Port of the historical ``JavaScriptAnalyzer``: functions, classes (with
heritage), methods (parent from the enclosing class), arrow functions and
function expressions bound to ``const``/``let``/``var``, ES imports, and
CommonJS ``require`` calls. JSX parses with the same grammar. The JS
analyzers never collected doc comments, so this spec defines no ``doc``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

# JavaScript names are `identifier`; TypeScript class/interface names are
# `type_identifier`. Accept both so the shared rules work for TS too.
_NAME_TYPES = ("identifier", "type_identifier")


def _name(node: Node, ctx: TreeSitterExtractor) -> str:
    child = ctx.child_by_type(node, *_NAME_TYPES)
    return ctx.text(child) if child else ""


def _params(node: Node, ctx: TreeSitterExtractor) -> str:
    child = ctx.child_by_type(node, "formal_parameters")
    return ctx.text(child) if child else ""


def _function_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    prefix = "async " if any(c.type == "async" for c in node.children) else ""
    return f"{prefix}function {_name(node, ctx)}{_params(node, ctx)}"


def _class_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    heritage = ""
    child = ctx.child_by_type(node, "class_heritage")
    if child:
        heritage = f" {ctx.text(child)}"
    return f"class {_name(node, ctx)}{heritage}"


def _method_signature(node: Node, ctx: TreeSitterExtractor) -> str:
    name_node = ctx.child_by_type(node, "property_identifier")
    name = ctx.text(name_node) if name_node else ""
    prefix = ""
    if any(c.type == "static" for c in node.children):
        prefix += "static "
    if any(c.type == "async" for c in node.children):
        prefix += "async "
    return f"{prefix}{name}{_params(node, ctx)}"


def _extract_variable_declaration(node: Node, ctx: TreeSitterExtractor) -> bool:
    """Extract arrow functions / function expressions from variable declarations."""
    for child in node.children:
        if child.type == "variable_declarator":
            _extract_variable_declarator(child, ctx)
    return True


def _extract_variable_declarator(node: Node, ctx: TreeSitterExtractor) -> None:
    name = None
    value = None
    for child in node.children:
        if child.type == "identifier":
            name = ctx.text(child)
        elif child.type in ("arrow_function", "function_expression"):
            value = child

    if not name or not value:
        return

    is_async = any(c.type == "async" for c in value.children)
    params = ""
    for child in value.children:
        if child.type == "formal_parameters":
            params = ctx.text(child)
            break
        elif child.type == "identifier":
            # Single param arrow function: x => x + 1
            params = f"({ctx.text(child)})"
            break

    prefix = "async " if is_async else ""
    ctx.emit(
        name=name,
        kind="function",
        node=node,
        signature=f"const {name} = {prefix}{params} =>",
        dependencies=ctx.calls(value),
    )


def _extract_import(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    """Record the raw module specifier from an ``import`` statement."""
    source = node.child_by_field_name("source")
    if source is not None:
        spec = ctx.text(source).strip("'\"`")
        if spec:
            return [spec]
    return []


def _extract_require(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    """Record ``require("mod")`` call specifiers (CommonJS imports)."""
    fn = node.child_by_field_name("function")
    if fn is None or ctx.text(fn) != "require":
        return []
    args = node.child_by_field_name("arguments")
    if args is None:
        return []
    for child in args.children:
        if child.type == "string":
            spec = ctx.text(child).strip("'\"`")
            if spec:
                return [spec]
            break
    return []


_CLASS_RULE = SymbolRule(
    kind="class",
    name_child_types=_NAME_TYPES,
    signature=_class_signature,
    is_container=True,
    visit_children=False,
    inherit_parent=False,
    collect_calls=False,
)

RULES: dict[str, SymbolRule] = {
    "function_declaration": SymbolRule(
        kind="function",
        name_child_types=_NAME_TYPES,
        signature=_function_signature,
        inherit_parent=False,
    ),
    "class_declaration": _CLASS_RULE,
    "abstract_class_declaration": _CLASS_RULE,
    "method_definition": SymbolRule(
        kind="method",
        name_child_types=("property_identifier",),
        signature=_method_signature,
    ),
    "variable_declaration": SymbolRule(kind="function", handler=_extract_variable_declaration),
    "lexical_declaration": SymbolRule(kind="function", handler=_extract_variable_declaration),
}

IMPORT_RULES = {
    "import_statement": _extract_import,
    "call_expression": _extract_require,
    "require_call": _extract_require,
}

SPEC = LanguageSpec(
    language="javascript",
    grammar="javascript",
    rules=RULES,
    import_rules=IMPORT_RULES,
)
