# A/B results (in progress)

Metrics are copied verbatim from `parse-run.mjs` over the stream-json traces.
Nothing here is self-reported by the agent.

## Harness status
- Plumbing validated end-to-end: `claude -p --output-format stream-json` yields
  `system/init` (mcp_servers — the isolation proof), `tool_use` blocks (per-tool
  counts) and the `result` event (tokens, duration_ms, num_turns).
- The **full sweep (corpus × model × size × ≥3 reps × 2 tasks) was NOT run**:
  the account was at **78% of its 7-day rate limit** when measurement began
  (`rate_limit_event … surpassedThreshold: 0.75`), and a navigation sweep is the
  most token-heavy workload possible. Running it risked exhausting the user's
  weekly quota and blocking their real work. The harness is ready; run it with
  `scripts/agent-eval/run-ab.sh` when quota permits.

## The one cell that was run (real numbers)

Repo: gin (99 indexed files). Task G1 (trace request→handler). Model:
sonnet/high. Reduction mode (both arms keep built-in tools; codenav arm also
has the codenav MCP). 1 rep.

| arm | tool calls | Read | Bash | native-search | tokens in | out | duration | codenav calls |
|-----|-----------|------|------|---------------|-----------|-----|----------|---------------|
| native  | 9 | 5 | 4 | 5 | 156,798 | 1,691 | 36s | — |
| codenav | 9 | 4 | 5 | 4 | 130,135 | 1,602 | 30s | **0** |

## The finding this cell surfaces (and it is the important one)

The codenav arm had the MCP server wired (`mcp_servers=["codenav"]`) yet the
agent **called zero codenav tools** — it navigated with Read + Bash(grep) in
both arms. The ~17% token gap is run-to-run variance, not codenav doing work.

This reproduces CodeGraph's own central lesson: **wiring a retrieval MCP server
does not make the agent use it.** The channels to influence tool choice (server
instructions, tool descriptions) are low-salience; against a model that already
writes a competent ripgrep, the agent defaults to native search. So a naive
"just wire the MCP" A/B measures *spontaneous adoption* — and under sonnet that
is ≈0, which is itself the result.

Consequences for the measurement design:
- To measure codenav's **sufficiency/economy at all**, the agent must be made to
  use it — either the **strict arm** (built-in Read/Grep removed, forcing
  codenav; the brief's 0.c isolation, which this vindicates) or explicit
  system-prompt steering (which contaminates the clean-isolation A/B).
- The realistic "reduction" metric is really an **adoption** metric first. The
  token-economy problem is not (only) that codenav's calls are inefficient; it
  is that they are not chosen. That reframes the régimen (see the final report):
  codenav pays when the harness is configured to prefer it, or when native
  search cannot sustain the answer in one context (very large repos).

Next runs to do when quota allows (commands in `run-ab.sh` / `TASKS.md`):
strict-mode cell on gin (force codenav, compare sufficiency + tokens), the same
on a large repo (hugo/django) to find the file-count cross-over, and the whole
matrix repeated on opus to sweep model class.
