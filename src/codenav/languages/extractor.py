"""Generic tree-sitter extractor driven by a declarative :class:`LanguageSpec`.

One extractor serves every tree-sitter language: it walks the AST once,
dispatching each node type through the spec's :class:`SymbolRule` and import
rules. Language-specific behavior lives in the spec (data first, hooks only
for the hard parts) — see :mod:`codenav.languages.spec`.

Fallback behavior (mirrors the historical per-language analyzers):

- No grammar installed → regex :class:`~codenav.code_navigator.GenericAnalyzer`
  (or the injected ``fallback`` callable, e.g. ast-grep for Java/C/C++/PHP).
- Parse raises on one file → only that file falls back (per-file, not global).

The extractor keeps the attribute contract of the old analyzers
(``symbols``, ``imports``, ``source_bytes``, ``lines``) and doubles as the
``ctx`` object passed to spec hooks.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..call_extraction import collect_calls, collect_doc_comment
from ..code_navigator import GenericAnalyzer, Symbol
from . import registry
from .spec import LanguageSpec, SymbolRule

if TYPE_CHECKING:
    from tree_sitter import Node


class TreeSitterExtractor:
    """Spec-driven analyzer with the same interface as the old per-language classes.

    Example:
        >>> from codenav.languages import get_spec
        >>> extractor = TreeSitterExtractor("main.go", source, get_spec("go"))
        >>> symbols = extractor.analyze()
    """

    def __init__(
        self,
        file_path: str,
        source: str,
        spec: LanguageSpec,
        *,
        fallback: Callable[[], list[Symbol]] | None = None,
    ):
        self.file_path = file_path
        self.source = source
        self.source_bytes = source.encode("utf-8")
        self.lines = source.split("\n")
        self.symbols: list[Symbol] = []
        self.imports: list[str] = []
        self.spec = spec
        self._fallback = fallback
        self._scope: list[str] = []

    def analyze(self) -> list[Symbol]:
        """Parse the file and return its symbols (falling back per-file on failure)."""
        language = registry.get_language(self.spec.grammar_for(self.file_path))
        if language is None:
            return self._run_fallback()

        try:
            from tree_sitter import Parser

            source = self.spec.preparse(self.source) if self.spec.preparse else self.source
            tree = Parser(language).parse(source.encode("utf-8"))
            self._visit(tree.root_node)
        except Exception as e:
            print(f"tree-sitter error in {self.file_path}: {e}", file=sys.stderr)
            return self._run_fallback()

        return self.symbols

    def _run_fallback(self) -> list[Symbol]:
        if self._fallback is not None:
            return self._fallback()
        generic = GenericAnalyzer(
            self.file_path, self.source, self.spec.fallback_language or self.spec.language
        )
        return generic.analyze()

    # ------------------------------------------------------------------
    # Context helpers — hooks receive this extractor as ``ctx``.
    # ------------------------------------------------------------------

    def text(self, node: Node) -> str:
        # tree-sitter offsets are byte offsets; slice bytes, not str.
        return self.source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    def child_by_type(self, node: Node, *type_names: str) -> Node | None:
        for child in node.children:
            if child.type in type_names:
                return child
        return None

    @property
    def parent(self) -> str | None:
        """Name of the enclosing container scope, if any."""
        return self._scope[-1] if self._scope else None

    def doc(self, node: Node) -> str | None:
        """Doc comment directly above ``node`` per the spec's :class:`DocStyle`."""
        style = self.spec.doc
        if style is None:
            return None
        return collect_doc_comment(
            node,
            self.source_bytes,
            comment_types=style.comment_types,
            require_prefix=style.require_prefix,
        )

    def calls(self, node: Node) -> list[str]:
        """Callee names within ``node``'s subtree per the spec's :class:`CallStyle`."""
        style = self.spec.calls
        if style.collector is not None:
            return style.collector(node, self.source_bytes)
        return collect_calls(
            node,
            self.source_bytes,
            call_types=style.call_types,
            callee_field=style.callee_field,
            macro_types=style.macro_types,
        )

    def emit(
        self,
        *,
        name: str,
        kind: str,
        node: Node,
        signature: str | None = None,
        docstring: str | None = None,
        parent: str | None = None,
        dependencies: list[str] | None = None,
        decorators: list[str] | None = None,
        visibility: str | None = None,
        modifiers: list[str] | None = None,
        mixins: list[str] | None = None,
        return_type: str | None = None,
    ) -> None:
        """Append a :class:`Symbol` located at ``node`` (signature capped at 100 chars)."""
        self.symbols.append(
            Symbol(
                name=name,
                type=kind,
                file_path=self.file_path,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=signature[:100] if signature else None,
                docstring=docstring,
                parent=parent,
                dependencies=dependencies,
                decorators=decorators,
                source="ast",
                visibility=visibility if visibility != "public" else None,
                modifiers=modifiers or None,
                mixins=mixins or None,
                return_type=return_type,
            )
        )

    def visit(self, node: Node) -> None:
        """Re-enter the dispatch loop (for handlers that walk bodies themselves)."""
        self._visit(node)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _visit(self, node: Node) -> None:
        rule = self.spec.rules.get(node.type)
        import_rule = self.spec.import_rules.get(node.type)
        if import_rule is not None:
            self.imports.extend(import_rule(node, self))

        emitted_name: str | None = None
        if rule is not None:
            handled = rule.handler(node, self) if rule.handler is not None else None
            if handled:
                emitted_name = handled if isinstance(handled, str) else None
            else:
                emitted_name = self._apply(rule, node)
            if rule.is_container and emitted_name:
                self._scope.append(emitted_name)
                for child in node.children:
                    self._visit(child)
                self._scope.pop()
                return
            if not rule.visit_children:
                return

        for child in node.children:
            self._visit(child)

    def _node_name(self, node: Node, rule: SymbolRule) -> str | None:
        for field_name in rule.name_fields:
            child = node.child_by_field_name(field_name)
            if child is not None:
                return self.text(child)
        for type_name in rule.name_child_types:
            child = self.child_by_type(node, type_name)
            if child is not None:
                return self.text(child)
        return None

    def _default_signature(self, node: Node) -> str:
        # First source line of the node, without a trailing open brace.
        return self.text(node).split("\n", 1)[0].strip().rstrip("{").rstrip()

    def _apply(self, rule: SymbolRule, node: Node) -> str | None:
        name = self._node_name(node, rule)
        if not name:
            return None

        kind: str = rule.kind
        if rule.classify is not None:
            classified = rule.classify(node, self)
            if classified is None:
                return None
            kind = classified

        signature = rule.signature(node, self) if rule.signature else self._default_signature(node)

        docstring = None
        if rule.collect_doc and self.spec.doc is not None:
            anchor = rule.doc_anchor(node) if rule.doc_anchor is not None else node
            docstring = self.doc(anchor)

        dependencies = self.calls(node) if rule.collect_calls else None

        self.emit(
            name=name,
            kind=kind,
            node=node,
            signature=signature,
            docstring=docstring,
            parent=self.parent if rule.inherit_parent else None,
            dependencies=dependencies,
            visibility=rule.visibility(node, self) if rule.visibility else None,
            modifiers=rule.modifiers(node, self) if rule.modifiers else None,
            return_type=rule.return_type(node, self) if rule.return_type else None,
        )
        return name
