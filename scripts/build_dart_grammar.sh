#!/usr/bin/env bash
# Build the tree-sitter Dart grammar into a shared library that codenav can load
# at runtime. Without this step, Dart files are still analyzed via regex fallback.
#
# Usage:
#   bash scripts/build_dart_grammar.sh            # build into src/codenav/
#   CODENAV_DART_LIB_PATH=/tmp/dart.so bash ...   # build to a custom path
#
# Requirements:
#   - git
#   - clang or gcc
#
# Resulting library is loaded by codenav.dart_analyzer in this order:
#   1. $CODENAV_DART_LIB_PATH
#   2. <package_dir>/dart.<ext>
#   3. ~/.codenav/lib/dart.<ext>

set -euo pipefail

GRAMMAR_REPO="${CODENAV_DART_GRAMMAR_REPO:-https://github.com/UserNobody14/tree-sitter-dart}"
GRAMMAR_REF="${CODENAV_DART_GRAMMAR_REF:-master}"

# Detect platform-specific shared-library extension.
case "$(uname -s)" in
    Linux*)   EXT="so"    ;;
    Darwin*)  EXT="dylib" ;;
    MINGW*|MSYS*|CYGWIN*) EXT="dll" ;;
    *)        EXT="so"    ;;
esac

# Pick a C compiler.
if command -v clang >/dev/null 2>&1; then
    CC="clang"
elif command -v gcc >/dev/null 2>&1; then
    CC="gcc"
else
    echo "ERROR: neither clang nor gcc found on PATH" >&2
    exit 1
fi

# Resolve repo root (script lives in scripts/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PKG_DIR="$REPO_ROOT/src/codenav"

# Destination: CODENAV_DART_LIB_PATH if set, else package dir.
DEST="${CODENAV_DART_LIB_PATH:-$PKG_DIR/dart.$EXT}"
mkdir -p "$(dirname "$DEST")"

# Clone (or update) grammar into a workdir.
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "Cloning $GRAMMAR_REPO (ref: $GRAMMAR_REF)..."
git clone --depth 1 --branch "$GRAMMAR_REF" "$GRAMMAR_REPO" "$WORKDIR/tree-sitter-dart"

cd "$WORKDIR/tree-sitter-dart"

# Compile parser.c + scanner.c (if present) into the shared lib.
SRC_FILES=(src/parser.c)
if [ -f src/scanner.c ]; then
    SRC_FILES+=(src/scanner.c)
fi

echo "Compiling Dart grammar with $CC..."
"$CC" -shared -fPIC -O2 -o "$DEST" "${SRC_FILES[@]}" -I src

echo ""
echo "Built Dart tree-sitter grammar:"
echo "  $DEST"
echo ""
echo "codenav will now use AST-based Dart analysis automatically."
