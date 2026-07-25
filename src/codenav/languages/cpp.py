"""C++ language spec for the generic tree-sitter extractor.

Everything from C plus: classes and structs as method containers,
namespaces, and out-of-line members (``User::greet``) whose parent comes
from the ``qualified_identifier`` scope. Prototypes inside class bodies
(``declaration``/``field_declaration`` with a function declarator) are
extracted so header files surface their API. Template declarations are
transparent — the inner definition is visited normally.
"""

from __future__ import annotations

from .c import (
    extract_function_declaration,
    extract_function_definition,
    extract_include,
    specifier_classify,
)
from .spec import CallStyle, DocStyle, LanguageSpec, SymbolRule


def _container(kind: str) -> SymbolRule:
    return SymbolRule(
        kind=kind,
        name_fields=("name",),
        classify=specifier_classify(kind),
        is_container=True,
        inherit_parent=False,
        collect_calls=False,
    )


SPEC = LanguageSpec(
    language="cpp",
    grammar="cpp",
    rules={
        "function_definition": SymbolRule(kind="function", handler=extract_function_definition),
        "declaration": SymbolRule(kind="function", handler=extract_function_declaration),
        "field_declaration": SymbolRule(kind="method", handler=extract_function_declaration),
        "class_specifier": _container("class"),
        "struct_specifier": _container("struct"),
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
        "namespace_definition": SymbolRule(
            kind="module",
            name_fields=("name",),
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
        "alias_declaration": SymbolRule(
            kind="type",
            name_fields=("name",),
            inherit_parent=False,
            collect_calls=False,
            collect_doc=False,
        ),
    },
    import_rules={"preproc_include": extract_include},
    doc=DocStyle(comment_types=("comment",)),
    calls=CallStyle(),
)
