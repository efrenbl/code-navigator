# A/B navigation tasks and rubrics (pre-registered)

Written **before** the first run and not adjusted after. Each task is
read-only, has a verifiable answer against the code, and is scored on 4–6
binary criteria. Metrics (tokens, duration, tool calls, native-search count)
come only from the stream-json trace via `parse-run.mjs`; the rubric scores
whether the *answer* is correct at the same quality bar in both arms.

The measurement question is **tokens per question answered** at equal quality —
not tokens per call. A win for codenav means fewer tokens/time for the same
verified answer; if it doesn't win in some regime, that regime is reported.

## Corpora (size is an experiment variable — record file counts at run time)

| lang | small | large |
|------|-------|-------|
| Go | gin-gonic/gin | gohugoio/hugo |
| Ruby | sidekiq/sidekiq | mastodon/mastodon (Rails) |
| Python | pallets/flask | django/django |
| Dart | flutter/samples | (same, large) |

## Tasks (2 per corpus; T1 = trace a request, T2 = cross-layer)

### Go — gin
- **G1 (trace):** "How does an incoming HTTP request reach a registered route
  handler? Name the files and the functions on the path from the server
  entrypoint to handler invocation."
  Rubric: (a) names `Engine.ServeHTTP`; (b) names `handleHTTPRequest`;
  (c) names the `RouterGroup`/`methodTree` lookup; (d) names `Context.Next`;
  (e) no invented file paths.
- **G2 (cross-layer):** "How does middleware get executed relative to the route
  handler? Name the mechanism and the symbols."
  Rubric: (a) identifies the handlers chain on `Context`; (b) names
  `Context.Next`; (c) explains index-advance execution; (d) no invented paths.

### Ruby — sidekiq
- **R1 (trace):** "How does `Sidekiq::Client.push` end up placing a job in
  Redis? Name the files and methods on the path."
  Rubric: (a) names `Client#push`; (b) names `normalize_item`/middleware chain;
  (c) names the Redis `lpush`/`raw_push`; (d) no invented paths.
- **R2 (cross-layer, exercises metaprogramming):** "For a class that
  `include Sidekiq::Job`, what instance/class methods does that mix in, and
  where is `perform_async` defined?"
  Rubric: (a) identifies `Sidekiq::Job` module; (b) names `perform_async`;
  (c) connects `include` to the mixed-in surface; (d) no invented paths.

### Python — flask
- **P1 (trace):** "How does a request dispatch to a view function? Name the
  path from `Flask.wsgi_app` to `view_func` invocation."
  Rubric: (a) `wsgi_app`; (b) `full_dispatch_request`; (c) `dispatch_request`;
  (d) `url_map`/`Rule` match; (e) no invented paths.
- **P2 (cross-layer):** "How is a blueprint's route registered onto the app?
  Name the symbols."
  Rubric: (a) `Blueprint.route`; (b) `add_url_rule`; (c) deferred-function
  registration; (d) no invented paths.

### Dart — flutter/samples
- **D1 (trace):** pick one sample app; "How does a button tap update the
  displayed state? Name the widget, the handler, and the state class."
  Rubric: (a) names the `on*`/handler; (b) names `setState`; (c) names the
  `State` subclass and `build`; (d) no invented paths.
- **D2 (cross-layer):** "Where is the app's routing/navigation configured and
  how does a screen get pushed?" Rubric: (a) router config location;
  (b) `Navigator.push`/route map; (c) target screen widget; (d) no invented.

## Protocol
- ≥3 reps per cell (run-to-run variance is large — report the range).
- Sweep model class: **sonnet** (floor) and **opus** (frontier).
- Sweep repo size (small vs large) to find the cross-over point in file count.
- Both arms use the same model and the same question; only the MCP wiring
  differs. Score the answer against the rubric independently of the metrics.
