# Codenav: correctness, economy, coverage — findings and régimen

This report covers the work triggered by a third-party measurement of codenav
against a private repo (a gitignore bug that silently dropped subtrees, and a
persistent tokens-per-question gap versus native search), extended to a
polyglot target (Go, Ruby/Rails, Python, Dart). Numbers are either reproduced
here on public corpora or explicitly marked as inherited/predicted.

## 1. Reproduction

**0.a — the gitignore bug (reproduced, fixed).** `scripts/repro_gitignore_bug.py`
on the canonical 10-line repo:

| | count |
|--|--|
| OLD substring logic swallowed | **2/3** (`internal/domain/entity/thing.go`, `cmd/api/main.go`) |
| NEW matcher indexes | **3/3** |
| `git check-ignore` says ignored | **0/3** |

Root cause: `should_ignore` tested `pattern in path_str` (a raw substring on the
full path). Fixed by a self-contained `gitignore.py` validated in tests against
`git check-ignore` as oracle. Shipped as **v2.2.9** (PR #44).

**0.b — the token/time gap (harness built; full sweep not run).** The A/B
harness (`scripts/agent-eval/`) isolates arms by `--mcp-config` only and reads
every metric from the stream-json trace. The full corpus×model×size×reps sweep
was **not run**: the account was at 78% of its 7-day rate limit and a navigation
sweep is the heaviest possible workload — running it risked blocking the user's
own work. One real cell was run (see §2).

## 2. Diagnosis (from a real trace, not theory)

One A/B cell — gin, "trace request→handler", sonnet, reduction mode:

| arm | calls | Read | native-search | tokens in | duration | **codenav calls** |
|-----|-------|------|---------------|-----------|----------|-------------------|
| native  | 9 | 5 | 5 | 156,798 | 36s | — |
| codenav | 9 | 4 | 4 | 130,135 | 30s | **0** |

The codenav arm had the server wired (`mcp_servers=["codenav"]`) and **called
zero codenav tools** — it used Read + Bash(grep) in both arms. The ~17% token
delta is run-to-run variance, not codenav doing work.

**This is the load-bearing finding.** The earlier private-repo measurement asked
"why does codenav spend more per answer"; the sharper question this trace poses
is "why is codenav *not chosen at all*". Wiring a retrieval MCP server does not
make the agent use it — the influence channels (server instructions, tool
descriptions) are low-salience, and against a model that writes a competent
ripgrep the agent defaults to native search. CodeGraph documents the same wall
("adapt the tool to the agent — you can't make the agent use it"). So the
token-economy problem is, first, an **adoption** problem; a naive "just wire the
MCP" A/B measures spontaneous adoption, which under sonnet is ≈0.

## 3. What was done (prioritized; correctness first)

| # | change | proof | status |
|---|--------|-------|--------|
| W1 | real gitignore semantics (self-contained, zero-dep) | 9 oracle tests vs `git check-ignore`; 0.a repro | shipped v2.2.9 (#44) |
| W2 | coverage invariant + skip-cause breakdown + MCP self-disclosure + index version bump | 9 tests; `exit 2` on a dead analyzer | shipped v2.2.9 (#44) |
| W4 | Ruby/Rails metaprogramming extraction | 8 tests; 1/13→12/12 on a model | economy branch |
| W5 | `codenav_lookup` (locate+body+callers in 1 call) + reverse caller index | 6 tests; end-to-end demo | economy branch |
| W3 | A/B harness + one real cell + adoption finding | validated plumbing; §2 | economy branch |

## 4. Changes implemented (tests that failed before, pass after)

- `gitignore.py` + `tests/test_gitignore.py` (oracle) — kills the substring class.
- Coverage invariant / `per_language` / skip causes / index version `1.0→2` +
  `tests/test_coverage_invariant.py`; MCP `_index_health_note` /
  "on disk but not indexed" disclosure.
- `languages/ruby.py` macro handler + `tests/test_ruby_analyzer.py::TestRailsMetaprogramming`.
- `codenav_lookup` + `CodeSearcher.find_callers` + `tests/test_lookup.py`.

## 5. Coverage by language (measured, name-to-name vs the CodeGraph oracle over shared files)

| language | corpus | codenav symbols | invocable capture | method |
|----------|--------|-----------------|-------------------|--------|
| Go | gin | 1,678 | **100.0%** (1715/1715) | vs codegraph nodes in shared files |
| Ruby | sidekiq | 1,480 | **100.0%** (1436/1436, excl. codegraph's method-local vars) | idem; +62 `attr_*` now captured |
| Dart | flutter/samples | 8,920 | **99.8%** (2253/2257) | idem |
| Python | flask | 1,629 | defined-symbol ≈complete, **0 coverage gaps** | stdlib `ast` is authoritative for def/class/method |

- **Ruby was the biggest gap and the biggest win.** Before W4, a representative
  ActiveRecord model yielded **1 of 13** invocable methods (only plain `def`);
  after, **12/13** (associations, `attr_*`, `delegate` with prefix, `scope`,
  `define_method`). On sidekiq (a library, not Rails) this alone surfaced 62
  `attr_*` methods that were previously invisible; a Rails app surfaces far more.
- **Dart is calibrated** against a real corpus (flutter/samples), not asserted.
- **Frontier, deliberately uncovered:** Ruby `method_missing`/`send` dynamic
  dispatch and Python decorator/`__init__.py` re-export indirection — static
  extraction cannot resolve targets, and partial coverage is worse than none.

## 6. Codenav vs CodeGraph (McHenry) vs codegraph-nav — mechanism by mechanism

- **Symbol extraction (per file):** codenav (post-port) is at parity with both
  on Go/Ruby/Dart (§5), and W4 pushes Ruby *ahead* of a plain-`def` extractor.
- **Relations / "who calls X":** codenav now answers this via the reverse
  caller index (W5) — the one query grep structurally cannot. But it is
  name-based (unresolved), not a true resolved call graph.
  **Where codenav loses:** CodeGraph resolves references cross-file (imports →
  file → symbol, framework routes) and **synthesizes dynamic-dispatch edges**
  (callbacks, React re-render, ORM), then answers a whole flow in ONE
  `codegraph_explore` call. codegraph-nav (codenav's sibling) has a persistent
  SQLite graph with real `CALLS`/`INHERITS` edges, PageRank and blast radius.
  codenav's flat `.codenav.json` cannot match either on multi-hop flow
  questions — it has no resolved edges and no graph traversal.
- **Freshness:** CodeGraph has a native file-watcher with debounced auto-sync;
  codenav re-indexes on demand (`--incremental`, hash-based). CodeGraph wins on
  "always fresh".
- **Adopt from CodeGraph:** the fused, sufficient single-call answer (done in
  W5); the monotonic per-repo output budget (done in W5); "never say 'not
  found' ambiguously / never send the agent to Read" (done in W2c + lookup
  steering).
- **Reject for codenav's core:** the heavy synthesizer machinery — it violates
  codenav's zero-dependency core, and a half-bridged flow is worse than none.
  Deep relation/flow work belongs in **codegraph-nav** (which already has the
  graph), not in codenav.

## 7. Régimen — where codenav is the right tool

Stated as honestly as the evidence allows, with the caveat that the full A/B
sweep is pending (quota):

- **Codenav's durable, measured edge is the index itself, not agent-loop
  economy.** Correct, complete, honest extraction across Go/Ruby/Rails/Python/
  Dart with a **zero-dependency core**, plus a coverage invariant that makes a
  silently-broken index impossible. That is real and shipped.
- **Against a frontier model on a few-hundred-file repo, codenav does not beat
  native search on tokens/time** — because the agent does not spontaneously call
  it (§2). This matches the inherited private-repo result (native won on economy
  at equal quality) and is the honest answer for that regime.
- **Codenav is expected to pay when the agent is configured to prefer it**
  (MCP-first setup, or `codenav_lookup` as the sanctioned entrypoint) **and/or
  when the repo is large enough that native "grep-then-read-many" cannot sustain
  the answer in one context.** The file-count cross-over is *not yet measured* —
  finding it (small vs large corpora, `run-ab.sh` on hugo/django/mastodon) is
  the first thing to run when quota resets, alongside the model sweep
  (sonnet vs opus).
- **What would change this conclusion:** (a) a strict-isolation or steered A/B
  showing `codenav_lookup` answers the same question sufficiently in fewer
  tokens once actually used; (b) the cross-over sweep showing codenav ahead
  beyond N files; (c) a weaker (floor) model adopting codenav where a frontier
  model doesn't — which would make the target audience "weaker agents on large
  repos", exactly where an index earns its keep.

**One-line régimen:** codenav is the cheapest *correct* index to stand up
(zero-dep, polyglot, self-verifying), and it wins the agent loop specifically
when it is the sanctioned retrieval path or the repo outgrows what native
grep-and-read can hold in context — not as a spontaneous drop-in against a
frontier model on a small repo, where native search still wins on economy.
