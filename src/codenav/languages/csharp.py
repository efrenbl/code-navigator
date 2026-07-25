"""C# language spec for the generic tree-sitter extractor.

Classes, records (``record struct`` classifies as struct), structs,
interfaces, enums, delegates, namespaces, methods and constructors.
Preprocessor directives are blanked before parsing (byte-length preserved)
— the grammar chokes on ``#if``/``#endif`` inside declarations, notably
enums. Docs are ``///`` line comments; callees come from
``invocation_expression`` nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule, first_code_line_signature

if TYPE_CHECKING:
    from collections.abc import Callable

    from tree_sitter import Node

    from .extractor import TreeSitterExtractor

_signature = first_code_line_signature("[", "@")


def _blank_preprocessor_directives(source: str) -> str:
    """Blank out ``#...`` directive lines, preserving every byte offset."""
    lines = []
    for line in source.split("\n"):
        if line.lstrip().startswith("#"):
            lines.append("".join(" " * len(ch.encode("utf-8")) for ch in line))
        else:
            lines.append(line)
    return "\n".join(lines)


def _classify_record(node: Node, ctx: TreeSitterExtractor) -> str:
    return "struct" if any(c.type == "struct" for c in node.children) else "class"


def _using_directive(node: Node, ctx: TreeSitterExtractor) -> list[str]:
    child = ctx.child_by_type(node, "qualified_name", "identifier")
    if child is None:
        return []
    spec = ctx.text(child)
    return [spec] if spec else []


def _container_rule(
    kind: str,
    classify: Callable[[Node, TreeSitterExtractor], str | None] | None = None,
) -> SymbolRule:
    return SymbolRule(
        kind=kind,
        classify=classify,
        signature=_signature,
        is_container=True,
        visit_children=False,
        inherit_parent=False,
        collect_calls=False,
    )


SPEC = LanguageSpec(
    language="csharp",
    grammar="csharp",
    rules={
        "class_declaration": _container_rule("class"),
        "record_declaration": _container_rule("class", classify=_classify_record),
        "struct_declaration": _container_rule("struct"),
        "interface_declaration": _container_rule("interface"),
        "enum_declaration": SymbolRule(
            kind="enum",
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
        ),
        "delegate_declaration": SymbolRule(
            kind="type",
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "namespace_declaration": SymbolRule(
            kind="module",
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "file_scoped_namespace_declaration": SymbolRule(
            kind="module",
            signature=_signature,
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "method_declaration": SymbolRule(kind="method", signature=_signature),
        "constructor_declaration": SymbolRule(kind="constructor", signature=_signature),
    },
    import_rules={"using_directive": _using_directive},
    doc=DocStyle(comment_types=("comment",), require_prefix="///"),
    calls=CallStyle(call_types=("invocation_expression",)),
    preparse=_blank_preprocessor_directives,
)
