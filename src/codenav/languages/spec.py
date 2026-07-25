"""Declarative language specifications for the generic tree-sitter extractor.

A :class:`LanguageSpec` describes how to extract symbols from one language:
which AST node types are functions/classes/methods (:class:`SymbolRule`),
where imports live, how doc comments look (:class:`DocStyle`), and how call
sites are shaped (:class:`CallStyle`).

The guiding principle: **pure data for the tabular parts** (node types,
name fields, comment markers) and **hooks only where a language needs an
exact signature format or has anomalous AST structure** (Go receivers, Rust
``impl`` blocks, C declarator chains). A language without special cases
defines no hooks at all.

Hooks receive ``(node, ctx)`` where ``ctx`` is the running
:class:`~codenav.languages.extractor.TreeSitterExtractor`, exposing
``text(node)``, ``child_by_type(node, *types)``, ``emit(...)``, ``parent``,
``doc(node)``, ``calls(node)``, ``visit(node)`` and ``source_bytes``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node

    from .extractor import TreeSitterExtractor


@dataclass(frozen=True)
class DocStyle:
    """How doc comments look in this grammar.

    Attributes:
        comment_types: Node kinds that count as comments. A tuple so specs can
            list grammar variants (e.g. ``("block_comment", "comment")``).
        require_prefix: If set, only comments starting with this marker are
            collected (``"///"`` for Rust doc comments, ``"//"`` for Go).
    """

    comment_types: tuple[str, ...]
    require_prefix: str | None = None


@dataclass(frozen=True)
class CallStyle:
    """How call sites are shaped in this grammar.

    The defaults match the C-family grammars (a ``call_expression`` node with
    a ``function`` field). ``collector`` overrides the whole walk for
    grammars with non-standard invocations (Ruby, Dart).
    """

    call_types: tuple[str, ...] = ("call_expression",)
    callee_field: str = "function"
    macro_types: tuple[str, ...] = ()
    collector: Callable[[Node, bytes], list[str]] | None = None


@dataclass(frozen=True)
class SymbolRule:
    """How one AST node type maps to a symbol.

    Attributes:
        kind: Symbol type to emit ("function", "class", "method", ...).
        name_fields: Field names tried via ``child_by_field_name``.
        name_child_types: Child node types tried when no field matches
            (grammars without field names, e.g. Kotlin).
        signature: Hook returning the signature string; ``None`` uses the
            first source line of the node.
        classify: Hook reassigning ``kind`` per node (Go ``type_spec`` →
            struct/interface/type); returning ``None`` skips the node.
        handler: Full override. Runs instead of the generic emit; a truthy
            return means "handled" (a returned ``str`` is the symbol name,
            used as scope when ``is_container``). Child visiting is still
            governed by ``visit_children``/``is_container``.
        is_container: Push the symbol name as parent scope while visiting
            children (classes, impl blocks, namespaces).
        visit_children: Whether to descend into this node's children.
        inherit_parent: Emit with the enclosing scope as ``Symbol.parent``.
            ``False`` for symbol kinds that historically never carried a
            parent (Rust structs, JS functions) even when nested in a scope.
        collect_calls: Populate ``Symbol.dependencies`` from the node subtree.
        collect_doc: Populate ``Symbol.docstring`` from leading comments.
        doc_anchor: Node whose leading comments hold the doc (Go: the
            wrapping ``type_declaration``, not the ``type_spec``).
        visibility: Hook returning "private"/"protected" for the node, or
            ``None`` for public/unknown (public is never stored — it is the
            implied default and would bloat the map).
        modifiers: Hook returning qualifiers such as ``["static", "async"]``,
            or ``None``/empty when the node has none.
        return_type: Hook returning the normalized return type name, or
            ``None`` when the node has no resolvable return type.
    """

    kind: str
    name_fields: tuple[str, ...] = ("name",)
    name_child_types: tuple[str, ...] = ()
    signature: Callable[[Node, TreeSitterExtractor], str] | None = None
    classify: Callable[[Node, TreeSitterExtractor], str | None] | None = None
    handler: Callable[[Node, TreeSitterExtractor], str | bool | None] | None = None
    is_container: bool = False
    visit_children: bool = True
    inherit_parent: bool = True
    collect_calls: bool = True
    collect_doc: bool = True
    doc_anchor: Callable[[Node], Node] | None = None
    visibility: Callable[[Node, TreeSitterExtractor], str | None] | None = None
    modifiers: Callable[[Node, TreeSitterExtractor], list[str] | None] | None = None
    return_type: Callable[[Node, TreeSitterExtractor], str | None] | None = None


@dataclass(frozen=True)
class LanguageSpec:
    """Complete declarative description of one language.

    Attributes:
        language: Canonical id — key in ``LANGUAGE_EXTENSIONS``.
        grammar: Grammar name resolved by the registry.
        rules: ``node.type`` → :class:`SymbolRule`.
        import_rules: ``node.type`` → hook returning raw import specifiers.
        doc: Doc-comment style, or ``None`` when the language has none wired.
        calls: Call-site style for dependency extraction.
        grammar_for_path: Per-file dialect override (``.tsx`` → ``"tsx"``).
        fallback_language: Key into ``GenericAnalyzer.PATTERNS`` for the
            regex fallback (defaults to ``language``).
        preparse: Source transform applied before parsing; must preserve
            byte offsets (C#: blank out preprocessor directives).
    """

    language: str
    grammar: str
    rules: Mapping[str, SymbolRule] = field(default_factory=dict)
    import_rules: Mapping[str, Callable[[Node, TreeSitterExtractor], list[str]]] = field(
        default_factory=dict
    )
    doc: DocStyle | None = None
    calls: CallStyle = field(default_factory=CallStyle)
    grammar_for_path: Callable[[str], str] | None = None
    fallback_language: str | None = None
    preparse: Callable[[str], str] | None = None

    def grammar_for(self, file_path: str) -> str:
        """Grammar name for this file (dialect-aware)."""
        if self.grammar_for_path is not None:
            return self.grammar_for_path(file_path)
        return self.grammar


def first_code_line_signature(*skip_prefixes: str) -> Callable:
    """Signature hook: first node line that isn't an annotation/attribute.

    ``skip_prefixes`` are line starts to jump over (``"@"`` for Java/Kotlin
    annotations, ``"["`` for C# attributes); a trailing open brace is dropped.
    """

    def hook(node: Node, ctx: TreeSitterExtractor) -> str:
        for line in ctx.text(node).split("\n"):
            stripped = line.strip()
            if stripped and not any(stripped.startswith(p) for p in skip_prefixes):
                return stripped.rstrip("{;").rstrip()
        return ctx.text(node).split("\n", 1)[0].strip()

    return hook
