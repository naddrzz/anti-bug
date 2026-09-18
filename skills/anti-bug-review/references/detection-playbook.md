# Detection Playbook

Concrete patterns, search recipes and traps for each sweep pass in SKILL.md Phase 2.
Grep examples use ripgrep (`rg`); substitute `grep -rn` if unavailable.

> **This is a read-only review.** Everything below is for finding and proving. Nothing is edited; each confirmed pattern becomes a finding with a recommended fix described in words.

**Pass BL (business logic) lives in its own file**, `business-logic.md`, because it works differently from everything here: the passes below match patterns in code, while Pass BL compares code against written business rules. No grep in this file finds a discount applied in the wrong order.

## Contents
- Pass BL - Business logic -> see `business-logic.md`
- [Pass A - Error and failure handling](#pass-a)
- [Pass B - Security](#pass-b) (see also `security-audit.md`)
- [Pass C - Correctness and edge cases](#pass-c)
- [Pass D - Concurrency and state](#pass-d)
- [Pass E - Data integrity](#pass-e)
- [Pass F - Performance and resources](#pass-f)
- [Pass G - Configuration and deployment](#pass-g)
- [Pass H - Test quality](#pass-h)
- [Reading a finding like a reviewer](#reviewer)

---

<a name="pass-a"></a>
## Pass A - Error and failure handling

The three "Aspirator" patterns below were derived from an analysis of 198 real production failures; they alone accounted for 35% of catastrophic failures. Start here because they are mechanically findable.

**A1. Empty or log-only handler.** The error is detected, then discarded. The system continues in a state its author never considered.

```bash
# Python: bare except, pass-only, log-only
rg -n -U 'except[^:]*:\s*\n\s*(pass|return None|continue)\b'
rg -n -U 'except[^:]*:\s*\n\s*(logger|log|logging)\.\w+\([^)]*\)\s*\n\s*(?!raise)'
# JS/TS: catch that swallows
rg -n -U 'catch\s*\([^)]*\)\s*\{\s*\}'
rg -n -U 'catch\s*\([^)]*\)\s*\{\s*(console\.\w+|logger\.\w+)\([^;]*\);?\s*\}'
# Go: ignored error
rg -n '(^|\s)_\s*[:=]\s*[\w.]+\(' -g '*.go'
rg -n -U 'if err != nil \{\s*\}' -g '*.go'
# Java/Kotlin/C#
rg -n -U 'catch\s*\([^)]*\)\s*\{\s*(//[^\n]*)?\s*\}'
```

Ask for each hit: what is the caller's state after this? Does a partially-written record survive? Does a caller receive a success value for work that failed?

**A2. Over-broad catch paired with a hard stop.** `catch (Exception)` around a wide block, then `exit`, `abort`, `System.exit`, `panic`, or `process.exit`. A recoverable error takes down the whole process.

```bash
rg -n -B4 '(System\.exit|os\.exit|process\.exit|panic\(|abort\(|sys\.exit)'
```

**A3. Handler containing TODO/FIXME.** An explicitly unfinished error path that shipped.

```bash
rg -n -A3 'catch|except' | rg -n '(TODO|FIXME|XXX|HACK|not implemented|implement later)'
```

**A4. Swallowed async failures.** A rejected promise with no handler, or a fire-and-forget call.

```bash
# unawaited promise-returning calls
rg -n -P '^\s*(?!await|return|yield)[\w.]+\.(then|catch)\(' -g '*.{js,ts,jsx,tsx}'
rg -n '\.then\([^)]*\)\s*;?\s*$' -g '*.{js,ts}'    # then without catch
rg -n -P '(?<!await )(?<!return )\b\w+\.(save|send|write|flush|commit|delete)\(' -g '*.{js,ts}'
# Python: coroutine created and dropped
rg -n 'asyncio\.create_task\(' -A2
```
In Node, an unhandled rejection terminates the process by default in modern versions - this is a crash, not a warning.

**A5. Cleanup that does not run on the failure path.** Resource acquired, then early `return`/`throw` before release. Look for `open(`, `connect(`, `acquire(`, `lock(`, `beginTransaction(` without `finally`, `with`, `defer`, `using`, or try-with-resources.

```bash
rg -n '(open|connect|acquire|lock|begin(Transaction)?)\(' -A15 | rg -v '(finally|defer |with |using )'
```

**A6. Retry without backoff or cap.** `while True` around a network call, retry counts with no ceiling, retries on non-idempotent operations (a retried payment charges twice).

**A7. Error message loses the cause.** `raise ValueError("failed")` discarding the original exception; `throw new Error(e.message)` dropping the stack; `catch { return null }` turning a diagnosable failure into a null that crashes three layers up. Python: check for missing `from e`. JS: missing `{ cause: e }`.

**A8. Success returned for failed work.** A function returning `True`/`200`/`{ok:true}` in a branch where the operation did not actually complete. Trace every early return in write paths.

---

<a name="pass-b"></a>
## Pass B - Security

Full checklist in `security-audit.md`. The method that matters: **trace taint, do not grep for sinks.** Start at each entry point found in Phase 0, follow user-controlled data forward, and check for a sanitizer or parameterization on every path to a sink. A grep for `execute(` finds the sinks; only the trace tells you whether the data reaching them is attacker-controlled.

The highest-value target in most codebases is **authorization**, because no scanner can find it. A scanner cannot know that `GET /invoices/:id` should only return invoices belonging to the caller. For every route, ask: authenticated? authorized *for this specific object*? enforced server-side (not just hidden in the UI)? Missing Authorization and Incorrect Authorization both sit in the CWE Top 25, and "Authorization Bypass Through User-Controlled Key" (IDOR) is its own entry.

---

<a name="pass-c"></a>
## Pass C - Correctness and edge cases

**C1. Boundaries.** For every loop and slice: does it handle length 0 and length 1? Is the last element included or dropped? `<` vs `<=`, `i-1` at `i=0`, `range(1, n)` vs `range(n)`.

**C2. Null and absence.** Distinguish "missing", "null", "empty string", "zero", and "false" - collapsing them is a classic defect. In JS, `||` for defaults silently overrides `0` and `""` (use `??`). In Python, `if not x:` treats `0`, `[]`, `""`, and `None` alike. Optional chaining that hides a real absence bug downstream.

**C3. Numbers.** Money in floats (`0.1 + 0.2`); integer division truncating; unchecked `parseInt` without radix; `NaN` propagating silently; overflow in languages with fixed-width ints; percentage and rounding applied in the wrong order.

**C4. Time.** Naive datetimes compared with aware ones; local time stored without a zone; DST gaps making an hour nonexistent; `date.now()` used twice in a calculation that assumes atomicity; durations in mixed units; month arithmetic on the 31st.

**C5. Strings and encoding.** Length in bytes vs code points vs grapheme clusters; case-insensitive comparison with locale surprises (Turkish `i`); truncation splitting a multi-byte character; normalization mismatch in equality checks.

**C6. Mutable defaults and aliasing.** Python `def f(x=[])`; JS object literals shared across module scope; a "copy" that is a reference; sorting in place a caller's array.

**C7. Conditions.** Inverted booleans, De Morgan errors, `and`/`or` precedence without parens, an `if/elif` chain where an earlier branch shadows a later one, a `switch` missing `break` or `default`.

**C8. Requirement mismatch.** Compare behavior against the acceptance criteria inferred in Phase 0. Code that is internally consistent but does the wrong thing is still a defect - and it is the category automated tools never find.

---

<a name="pass-d"></a>
## Pass D - Concurrency and state

Empirically, 96% of concurrency bugs involve just two threads and 69% are atomicity violations, so look for pairs and for read-modify-write sequences rather than exotic schedules.

**D1. Check-then-act (TOCTOU).** `if not exists(x): create(x)`; `if balance >= amount: balance -= amount`; "get or create" without a unique constraint or an upsert. Two requests interleave and both pass the check.

**D2. Non-atomic read-modify-write.** `counter = counter + 1`, `cache[k] = cache[k] + v`, read-model-save without optimistic locking or `SELECT FOR UPDATE`. In SQL, prefer `UPDATE t SET n = n + 1` over reading then writing.

**D3. Missing transaction boundary.** Two or more writes that must both happen, with no transaction around them. Check every multi-write handler, and check that the transaction wraps the *whole* unit - a common bug is opening it after the first write.

**D4. Async misuse.**
```bash
rg -n -P '(?<!await )\bfetch\(|(?<!await )\baxios\.' -g '*.{js,ts}'
rg -n 'forEach\(\s*async' -g '*.{js,ts}'       # forEach does not await
rg -n 'async def .*\n.*time\.sleep\(' -U -g '*.py'   # blocking sleep in async
```
`Array.forEach` with an async callback does not wait; use `for...of` with `await` or `Promise.all`. Also: `await` inside a held lock serializes or deadlocks; `Promise.all` where one rejection should not cancel the rest (use `allSettled`).

**D5. Shared mutable state.** Module-level dicts/objects mutated per request; singletons holding request-scoped data (a classic auth leak between users); class attributes used where instance attributes were meant; connection or client objects assumed thread-safe when they are not.

**D6. Ordering assumptions.** Code assuming initialization completed, a callback fired, or a message arrived in order. Order violations are 32% of concurrency bugs and are usually invisible in single-threaded testing.

---

<a name="pass-e"></a>
## Pass E - Data integrity

- Columns the code treats as non-null that the schema allows to be null, and vice versa.
- Missing unique constraints behind "get or create" logic (the DB is the only reliable arbiter under concurrency).
- Missing foreign keys, or cascades that delete more than intended.
- Migrations that drop or rename columns without a backfill, or that are not reversible. Check that every migration has a working `down`.
- Writes to two systems (DB + cache, DB + search index, DB + third party) with no reconciliation when the second fails.
- Validation present in the UI or serializer but absent at the persistence boundary.
- Enum/status values in code that do not match those in the database or in existing rows.
- Soft-delete columns that queries forget to filter on.

---

<a name="pass-f"></a>
## Pass F - Performance and resources

**F1. N+1 queries.** A query inside a loop, or lazy-loaded relations accessed while iterating. Look for ORM access inside `for`/`map` bodies and template loops.
```bash
rg -n -A8 'for .* in .*:' -g '*.py' | rg -n '\.(objects|query|filter|get|all)\('
rg -n -A6 '\.map\(|\.forEach\(' -g '*.{js,ts}' | rg -n '(await|findOne|findById|query\()'
```
Confirm by enabling query logging and counting queries for one request - that count is the reproduction.

**F2. Unbounded results.** `SELECT` with no `LIMIT`, list endpoints without pagination, `find({})`, reading a whole file into memory, `JSON.parse` on an unbounded body. Fine at 100 rows, fatal at 10 million.

**F3. Missing indexes.** Every column used in a `WHERE`, `JOIN`, or `ORDER BY` on a large table. Run `EXPLAIN` on the slow paths; a sequential scan on a growing table is the finding.

**F4. Leaks.** Connections, file handles, sockets, subscriptions, timers, and event listeners created without a matching close/clear/unsubscribe. In front-end code, effects without cleanup. In long-running workers, caches and lists that only ever grow.

**F5. Blocking the loop.** Synchronous I/O, CPU-heavy work, or `time.sleep` on an event loop or a request thread. In Node: `fs.readFileSync`, `crypto.pbkdf2Sync`, big `JSON.parse` in a handler.

**F6. Work that belongs outside the loop.** Recompiled regexes, re-opened connections, repeated config parsing, re-fetched constants.

---

<a name="pass-g"></a>
## Pass G - Configuration and deployment

```bash
rg -n -i '(api[_-]?key|secret|password|token|passwd|private[_-]key)\s*[=:]\s*["\x27][^"\x27]{8,}'
rg -n 'process\.env\.\w+' -g '*.{js,ts}' | rg -v '(\|\||\?\?|default)'   # env read with no default
rg -n -i '(verify\s*=\s*False|rejectUnauthorized:\s*false|InsecureSkipVerify:\s*true|NODE_TLS_REJECT)'
rg -n -i '(debug\s*=\s*true|DEBUG=1|origin:\s*["\x27]\*|Access-Control-Allow-Origin.*\*)'
rg -n -i '(localhost|127\.0\.0\.1|:3000|:5432|http://)' -g '!*test*' -g '!*.md'
```

Also: compare `.env.example` against every env var the code actually reads (drift in either direction is a bug); confirm secrets are not committed in git history, not only in the working tree; check the vulnerability audit output from Phase 1 for advisories with a known exploit path into this code.

---

<a name="pass-h"></a>
## Pass H - Test quality

**H1. Tests that cannot fail.** Assertions on constants, `assert True`, snapshot tests regenerated on every run, tests whose only assertion is "no exception raised", and tests that mock the unit under test so thoroughly that only the mock is exercised.

**H2. Coverage without verification.** A line executed is not a line tested. The reliable check is the revert-check from Phase 4: undo the behavior and see whether anything goes red. Mutation score correlates with real fault detection significantly better than statement coverage does, and about 73% of real faults are coupled to standard mutation operators - so a small targeted mutation run on critical modules is worth more than a coverage percentage.

**H3. Flakiness triage.** Before blaming production code, classify:
- **Async wait (45%)** - a fixed `sleep` standing in for a condition. Fix with a wait-for-condition, not a longer sleep.
- **Concurrency (20%)** - genuine race, often a real product bug surfacing in the test.
- **Test-order dependency (12%)** - shared state not reset. Reproduce by running the suite shuffled and the test in isolation; fix in setup/teardown.
- Remainder: resource leaks, network, time, randomness, unordered collections (a set/map iteration order assumed stable).

78% of flaky tests are flaky from the moment they are written, so a newly added flaky test is a defect in that test, not decay.

---

<a name="reviewer"></a>
## Reading a finding like a reviewer

Before writing a finding to the ledger, answer these. If you cannot, it is `Suspected`, not `Confirmed`.

1. **What input triggers it?** Name a concrete value or sequence.
2. **What happens instead of the correct behavior?** Expected vs actual, specifically.
3. **Who is harmed and how badly?** This sets severity, not your irritation with the code.
4. **Why is it wrong?** Cite the contract: a docstring, a test, a schema constraint, a framework guarantee, or a Phase 0 acceptance criterion. "I would have written it differently" is not a defect.
5. **Where else does this pattern appear?** The answer is rarely "nowhere".
