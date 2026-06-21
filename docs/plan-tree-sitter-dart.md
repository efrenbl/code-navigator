# Plan: publicar un `tree-sitter-dart` propio (wheels precompilados)

## Objetivo

Hoy el análisis AST de Dart depende de **`tree-sitter-language-pack`**, que
funciona pero trae su **propio core** con una API no estándar (métodos en lugar
de propiedades: `root_node()`, `kind()`, `start_position()`…). Por eso
`dart_analyzer.py` necesita un adaptador `_Node`. El resto de lenguajes
(JS/TS/Go/Ruby/Rust) usan el binding estándar **py-tree-sitter**
(`Language(ts_x.language())`, `.type`, `.children`).

**Meta:** publicar un paquete PyPI `tree-sitter-dart` con wheels precompilados
para Linux/macOS/Windows, compatible con `tree-sitter>=0.23`, que exponga
`tree_sitter_dart.language()` como los demás grammars oficiales. Esto:

- Elimina la dependencia de `tree-sitter-language-pack`.
- Permite borrar el adaptador `_Node` y unificar Dart con los demás analizadores.
- Nos da control de versión/grammar (sin esperar al mantenedor del pack).

## Contexto

- La gramática canónica de Dart es
  [`UserNobody14/tree-sitter-dart`](https://github.com/UserNobody14/tree-sitter-dart)
  (es la que el viejo `build_dart_grammar.sh` clonaba y compilaba).
- No existe `tree-sitter-dart` en PyPI compatible con `tree-sitter>=0.23`
  (verificado: el nombre no está publicado para esa línea). Ese es exactamente
  el hueco que vamos a llenar.
- La gramática es C generado (`src/parser.c` + a veces `src/scanner.c`), igual
  que `tree-sitter-go`, `tree-sitter-rust`, etc. Empaquetarla es un patrón
  resuelto: lo hace el propio `tree-sitter` con su plantilla de bindings.

## Decisión de estrategia

| Opción | Qué implica | Recomendación |
|--------|-------------|---------------|
| **A. Bindings sobre el grammar existente** | Hacer fork/submódulo de `UserNobody14/tree-sitter-dart`, regenerar el parser y publicar el wheel. Sin tocar la gramática. | ✅ **Empezar aquí.** Mínimo esfuerzo, máximo valor. |
| **B. Mantener/evolucionar la gramática** | Además de A, arreglar nodos faltantes (records, patterns de Dart 3, etc.) en `grammar.js`. | Solo si A no cubre construcciones que necesitamos. |

El plan detalla **A** y deja **B** como extensión.

## Fase 1 — Repo del grammar y generación del parser

1. Crear repo `efrenbl/tree-sitter-dart` (o un subdirectorio dentro de
   code-navigator si se prefiere monorepo; recomiendo repo aparte para
   versionar/publicar independiente).
2. Añadir `UserNobody14/tree-sitter-dart` como submódulo git o vendorizar
   `grammar.js`, fijando un commit concreto (reproducibilidad).
3. Regenerar el parser con la CLI oficial:
   ```bash
   npm install -g tree-sitter-cli   # o npx tree-sitter
   tree-sitter generate             # produce src/parser.c (+ grammar fija)
   ```
4. Verificar que compila localmente y parsea el fixture
   (`tests/fixtures/sample_dart.dart` de code-navigator) con el árbol esperado.

**Salida:** `src/parser.c`, `src/scanner.c` (si aplica), `src/tree_sitter/*`,
`grammar.js`, commit fijado del upstream.

## Fase 2 — Empaquetado Python (binding estándar)

Usar la plantilla oficial de bindings de Python que genera el propio
`tree-sitter` (carpeta `bindings/python/`). Estructura objetivo:

```
tree-sitter-dart/
├── grammar.js
├── src/parser.c, scanner.c, tree_sitter/parser.h
├── bindings/python/
│   ├── tree_sitter_dart/__init__.py     # expone language() -> int (PyCapsule)
│   ├── tree_sitter_dart/__init__.pyi
│   └── tree_sitter_dart/binding.c       # módulo de extensión
├── pyproject.toml                        # build-backend: setuptools, ext module
└── setup.py                              # compila binding.c + parser.c (+scanner)
```

Claves del `pyproject.toml` / `setup.py`:
- Declarar el `Extension` que compila `src/parser.c`, `src/scanner.c` y
  `bindings/python/tree_sitter_dart/binding.c`.
- `__init__.py` expone `def language() -> int:` devolviendo el puntero del
  lenguaje (idéntico a `tree_sitter_go.language()`), usable con
  `tree_sitter.Language(tree_sitter_dart.language())`.
- Pin de compatibilidad: probar con `tree-sitter>=0.23,<0.26` y fijar el rango
  real tras testear (la ABI del binding cambió entre 0.21/0.22/0.23).

**Validación local:**
```python
import tree_sitter, tree_sitter_dart
from tree_sitter import Language, Parser
parser = Parser(Language(tree_sitter_dart.language()))
tree = parser.parse(b"class A extends B { void m() {} }")
assert tree.root_node.type == "program"
```

## Fase 3 — Wheels multiplataforma con `cibuildwheel`

GitHub Actions + [`cibuildwheel`](https://cibuildwheel.pypa.io/) construye
wheels binarios para todas las combinaciones plataforma × versión de Python:

- **Targets:** `manylinux` (x86_64, aarch64), `macosx` (x86_64, arm64),
  `win_amd64`; CPython 3.10–3.13.
- Job de `sdist` además de los wheels.
- Smoke test dentro de cada wheel: importar y parsear un snippet (vía
  `CIBW_TEST_COMMAND`).

`.github/workflows/release.yml` (boceto):
```yaml
jobs:
  build_wheels:
    strategy: { matrix: { os: [ubuntu-latest, macos-latest, windows-latest] } }
    steps:
      - uses: actions/checkout@v4
        with: { submodules: true }
      - uses: pypa/cibuildwheel@v2
        env:
          CIBW_TEST_REQUIRES: tree-sitter>=0.23
          CIBW_TEST_COMMAND: python -c "import tree_sitter, tree_sitter_dart; \
            from tree_sitter import Language,Parser; \
            Parser(Language(tree_sitter_dart.language())).parse(b'class A{}')"
```

## Fase 4 — Publicación

1. Reservar el nombre `tree-sitter-dart` en PyPI (si está libre) o usar
   `tree-sitter-dart-efrenbl` como fallback de namespace.
2. Publicar a **TestPyPI** primero; instalar en limpio y correr la validación.
3. Tag + release → workflow publica wheels + sdist a PyPI vía OIDC/trusted
   publishing (sin tokens en secrets).
4. Versionado: seguir al grammar upstream (p.ej. `0.1.0` inicial), documentar
   qué commit de la gramática incluye cada release.

## Fase 5 — Integrar de vuelta en code-navigator

Una vez publicado y estable:

1. `pyproject.toml`: reemplazar
   `tree-sitter-language-pack>=1.9.0` por `tree-sitter-dart>=0.1.0` en los
   extras `ast` y `all`.
2. `dart_analyzer.py`:
   - **Borrar** el adaptador `_Node` y el alias `Node = _Node`.
   - Cargar como los demás: 
     ```python
     import tree_sitter_dart
     from tree_sitter import Language, Parser
     _DART_LANGUAGE = Language(tree_sitter_dart.language())
     ...
     parser = Parser(_DART_LANGUAGE)
     tree = parser.parse(bytes(self.source, "utf-8"))
     self._visit_node(tree.root_node)
     ```
   - La lógica de extracción (`_extract_*`) queda **idéntica**: ya usa la API
     estándar (`.type`, `.children`, `.start_point`, `.start_byte`).
3. Tests: `tests/test_dart_analyzer.py` no cambia (mismas aserciones).
4. Actualizar README/CHANGELOG: Dart pasa a tener su propio grammar oficial.

**Resultado:** Dart unificado con JS/TS/Go/Ruby/Rust, una sola API
tree-sitter en todo el proyecto, sin dependencias con core divergente.

## Pruebas y aceptación

- [ ] El wheel instala en Linux/macOS/Windows + CPython 3.10–3.13 sin compilador.
- [ ] `tree_sitter.Language(tree_sitter_dart.language())` funciona con la
      versión de `tree-sitter` que ya usa code-navigator.
- [ ] `tests/test_dart_analyzer.py` pasa con el nuevo paquete (sin el adaptador).
- [ ] Parsea Dart 3 moderno: records, sealed/base classes, patterns
      (si falla → activar Fase B sobre la gramática).
- [ ] CI verde en los tres SO.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| ABI de py-tree-sitter cambia entre minors | Pin `tree-sitter>=0.23,<0.26`; matriz de CI por versión. |
| La gramática upstream se queda atrás de Dart 3 | Fase B: parche local en `grammar.js`, regenerar. |
| Mantenimiento continuo (releases del grammar) | Workflow de release automatizado; bot que vigile el upstream (opcional). |
| Nombre `tree-sitter-dart` ocupado en PyPI | Publicar bajo namespace propio. |

## Esfuerzo estimado

- **Fases 1–4 (paquete publicado, opción A):** ~1–2 días de trabajo.
- **Fase 5 (integración en code-navigator):** ~1–2 horas (el adaptador ya
  aísla el cambio).
- **Fase B (evolucionar gramática):** variable, solo si se necesita.

## Recomendación

Mantener `tree-sitter-language-pack` como está **ahora** (funciona, 0 fricción).
Abordar este plan cuando se quiera: (a) eliminar el core divergente, (b) tener
control de versión del grammar, o (c) reducir el tamaño de dependencias. No es
urgente: es una mejora de consistencia y control, no un arreglo de bug.
