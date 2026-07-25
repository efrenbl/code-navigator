#!/usr/bin/env bash
# Clone the public A/B corpora (shallow) and index each with codenav.
# Records per-language file counts (size is an experiment variable).
#
# Usage: setup-corpus.sh [small|large|all]   (default: small)
# Env:   CODENAV_BIN  codenav CLI (default: command -v codenav)
#        CORPUS_DIR   clone root (default: /tmp/codenav-corpus)
set -uo pipefail

WHICH="${1:-small}"
CODENAV_BIN="${CODENAV_BIN:-$(command -v codenav)}"
DIR="${CORPUS_DIR:-/tmp/codenav-corpus}"
mkdir -p "$DIR"
[ -n "$CODENAV_BIN" ] || { echo "no codenav on PATH (set CODENAV_BIN)"; exit 1; }

declare -A SMALL=(
  [gin]=https://github.com/gin-gonic/gin
  [sidekiq]=https://github.com/sidekiq/sidekiq
  [flask]=https://github.com/pallets/flask
  [samples]=https://github.com/flutter/samples
)
declare -A LARGE=(
  [hugo]=https://github.com/gohugoio/hugo
  [mastodon]=https://github.com/mastodon/mastodon
  [django]=https://github.com/django/django
)

clone_and_index() {
  local name="$1" url="$2" dest="$DIR/$name"
  if [ ! -d "$dest/.git" ]; then
    echo ">>> cloning $name"
    git clone -q --depth 1 "$url" "$dest" || { echo "clone failed: $name"; return; }
  fi
  echo ">>> indexing $name"
  "$CODENAV_BIN" map "$dest" -o "$dest/.codenav.json" --use-gitignore 2>&1 | tail -2
  echo -n ">>> $name file counts: "
  find "$dest" -type f \( -name '*.go' -o -name '*.rb' -o -name '*.py' -o -name '*.dart' \) \
    -not -path '*/.git/*' | sed 's/.*\.//' | sort | uniq -c | tr '\n' ' '
  echo
}

run_set() {
  local -n set=$1
  for name in "${!set[@]}"; do clone_and_index "$name" "${set[$name]}"; done
}

case "$WHICH" in
  small) run_set SMALL ;;
  large) run_set LARGE ;;
  all)   run_set SMALL; run_set LARGE ;;
  *) echo "arg must be small|large|all"; exit 1 ;;
esac
echo "done -> $DIR"
