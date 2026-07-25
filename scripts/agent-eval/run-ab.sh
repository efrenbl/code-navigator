#!/usr/bin/env bash
# A/B eval for codenav on a repo. Codenav is the ONLY variable.
#
#   NATIVE arm : empty MCP — the agent navigates with built-in Read/Grep/Glob/Bash.
#   CODENAV arm: codenav MCP wired (plus the same built-ins), so we measure how
#                far codenav pushes Read/Grep toward zero (the realistic deploy;
#                nobody removes Read). This is the "reduction" metric.
#
# Isolation is imposed by the CLI, never the prompt: the ONLY difference between
# arms is --mcp-config (enforced by --strict-mcp-config). Run from a checkout
# with no CLAUDE.md/AGENTS.md. Every metric is read from the stream-json trace
# by parse-run.mjs (system/init proves each arm's mcp_servers; the result event
# gives tokens/duration/turns; tool_use blocks give per-tool counts).
#
# NOTE: under --permission-mode bypassPermissions, --allowedTools does not gate
# tools, so the MCP config is what isolates the arms. A strict "codenav-only"
# arm (no built-in Read at all) needs --permission-mode default + an allowlist;
# the reduction metric below is the defensible, realistic one and is preferred.
#
# Usage: run-ab.sh <indexed-repo> "<question>"
# Env:   CODENAV_MCP_BIN  codenav-mcp binary (default: command -v codenav-mcp)
#        MODEL / EFFORT   claude model / effort (default: sonnet / high)
#        REPS             repetitions per arm (default: 1)
#        MAX_USD          per-run budget cap (default: 3)
#        AGENT_EVAL_OUT   output dir (default: /tmp/codenav-eval)
set -uo pipefail

REPO="${1:?usage: run-ab.sh <indexed-repo> \"<question>\"}"
Q="${2:?question required}"
MCP_BIN="${CODENAV_MCP_BIN:-$(command -v codenav-mcp)}"
OUT="${AGENT_EVAL_OUT:-/tmp/codenav-eval}"
REPS="${REPS:-1}"
MAX_USD="${MAX_USD:-3}"
HARNESS="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"

[ -n "$MCP_BIN" ] || { echo "no codenav-mcp on PATH (set CODENAV_MCP_BIN)"; exit 1; }
[ -f "$REPO/.codenav.json" ] || { echo "no .codenav.json in $REPO — run: codenav map \"$REPO\" -o \"$REPO/.codenav.json\" --use-gitignore"; exit 1; }

cat > "$OUT/mcp-codenav.json" <<JSON
{"mcpServers":{"codenav":{"command":"$MCP_BIN","args":[]}}}
JSON
echo '{"mcpServers":{}}' > "$OUT/mcp-empty.json"

echo "###### codenav-mcp: $MCP_BIN"
echo "###### repo:        $REPO   model: ${MODEL:-sonnet}/${EFFORT:-high}   reps: $REPS"
echo "###### question:    $Q"

run_arm() {
  local label="$1" cfg="$2"
  local log="$OUT/run-$label.jsonl"
  ( cd "$REPO" && claude -p "$Q" \
      --output-format stream-json --verbose \
      --permission-mode bypassPermissions \
      --no-session-persistence --setting-sources "" \
      --model "${MODEL:-sonnet}" --effort "${EFFORT:-high}" \
      --max-budget-usd "$MAX_USD" \
      --strict-mcp-config --mcp-config "$cfg" \
      > "$log" 2>"$OUT/run-$label.err" )
  echo "exit $? -> $log ($(wc -l < "$log" | tr -d ' ') lines)"
  node "$HARNESS/parse-run.mjs" "$log" 2>&1 || true
}

for rep in $(seq 1 "$REPS"); do
  echo; echo "############### NATIVE  (rep $rep) ###############"
  run_arm "native-$rep"  "$OUT/mcp-empty.json"
  echo; echo "############### CODENAV (rep $rep) ###############"
  run_arm "codenav-$rep" "$OUT/mcp-codenav.json"
done

echo; echo "###### aggregate the METRIC lines across cells with: grep -h '^METRIC' $OUT/*.err 2>/dev/null || grep -rh '^METRIC' $OUT"
