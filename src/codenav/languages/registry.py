"""Central tree-sitter grammar registry.

Resolves a grammar name (``"go"``, ``"typescript"``, ...) to a loaded
``tree_sitter.Language`` object, trying the available backends in order:

1. ``tree-sitter-language-pack`` — one dependency bundling 160+ grammars.
2. Individual grammar wheels (``tree-sitter-go``, ``tree-sitter-ruby``, ...),
   kept working so installations that predate the language pack keep their
   AST support without reinstalling extras.

When neither backend provides the grammar, :func:`get_language` returns
``None`` and callers degrade to the regex fallback. Results (including
misses) are cached per grammar name; all imports happen lazily inside the
loaders so ``import codenav`` never pays for tree-sitter.

Example:
    >>> from codenav.languages import registry
    >>> language = registry.get_language("go")
    >>> registry.backend("go")  # "pack", "wheel", or None
    'wheel'
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Language

# Grammar name -> (module, callable) for wheels whose layout differs from the
# default ``tree_sitter_<name>.language`` convention.
_WHEEL_MODULES: dict[str, tuple[str, str]] = {
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
}

_languages: dict[str, Language | None] = {}
_backends: dict[str, str | None] = {}


def _load_from_pack(name: str) -> Language | None:
    try:
        from tree_sitter_language_pack import get_language as pack_get_language
    except ImportError:
        return None
    try:
        return pack_get_language(name)
    except Exception:
        # Unknown grammar name for this pack version.
        return None


def _load_from_wheel(name: str) -> Language | None:
    try:
        from tree_sitter import Language
    except ImportError:
        return None
    module_name, attribute = _WHEEL_MODULES.get(name, (f"tree_sitter_{name}", "language"))
    try:
        module = importlib.import_module(module_name)
        return Language(getattr(module, attribute)())
    except Exception:
        return None


def get_language(name: str) -> Language | None:
    """Return the tree-sitter ``Language`` for ``name``, or ``None``.

    Tries the language pack first, then the individual grammar wheel, and
    caches the result (hit or miss) for subsequent calls.
    """
    if name in _languages:
        return _languages[name]
    language = _load_from_pack(name)
    backend_name = "pack" if language is not None else None
    if language is None:
        language = _load_from_wheel(name)
        backend_name = "wheel" if language is not None else None
    _languages[name] = language
    _backends[name] = backend_name
    return language


def is_available(name: str) -> bool:
    """Whether an AST grammar for ``name`` is installed."""
    return get_language(name) is not None


def backend(name: str) -> str | None:
    """Which backend provided the grammar: ``"pack"``, ``"wheel"``, or ``None``."""
    get_language(name)
    return _backends[name]


def clear_cache() -> None:
    """Drop all cached grammars (for tests)."""
    _languages.clear()
    _backends.clear()
