"""Declarative language specs + generic tree-sitter extractor.

Each supported language is a small module exporting ``SPEC``
(a :class:`~codenav.languages.spec.LanguageSpec`); one
:class:`~codenav.languages.extractor.TreeSitterExtractor` consumes any
spec. Grammars resolve through :mod:`~codenav.languages.registry`
(language pack → individual wheel → regex fallback).

Adding a language = writing one spec module + registering it here.
"""

from importlib import import_module
from typing import TYPE_CHECKING, cast

from . import registry

if TYPE_CHECKING:
    from .spec import LanguageSpec

# Language id (LANGUAGE_EXTENSIONS key) -> spec module, imported lazily so
# ``import codenav`` never loads tree-sitter machinery.
_SPEC_MODULES: dict[str, str] = {
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".csharp",
    "dart": ".dart",
    "go": ".go",
    "java": ".java",
    "javascript": ".javascript",
    "kotlin": ".kotlin",
    "php": ".php",
    "ruby": ".ruby",
    "rust": ".rust",
    "swift": ".swift",
    "typescript": ".typescript",
}


def get_spec(language: str) -> "LanguageSpec | None":
    """Return the :class:`LanguageSpec` for ``language``, or ``None``."""
    module_name = _SPEC_MODULES.get(language)
    if module_name is None:
        return None
    return cast("LanguageSpec", import_module(module_name, __name__).SPEC)


__all__ = ["get_spec", "registry"]
