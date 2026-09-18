---
name: anti-bug
description: End-to-end defect hunt and repair across a whole codebase - context and business-rule capture, hierarchical sweeps (business logic, error handling, security, correctness, concurrency, data integrity, performance, config, test quality), reproduction, root-cause fixes, regression proofing, and an evidence-backed audit report. Use whenever bugs are to be found or fixed at repository or module scope, such as "find all the bugs", "fix everything", "audit this codebase", "review the whole codebase", "QA review", "harden this before release", "check for vulnerabilities", "why is this flaky". Use it equally for business-logic defects where nothing crashes but the result is wrong - "the calculation is wrong", "the numbers do not add up", "the discount applies twice", "a step can be skipped", "the request can be replayed", "the limit does not hold", "a user can see another user's data". Prefer this over ad-hoc reading whenever the scope is a repo, a module, or "everything" rather than one known failing line, and when reviewing AI-generated or recently merged code before shipping. This skill CHANGES CODE. If the user wants findings only with nothing modified - "review only", "do not touch anything", "report only" - use anti-bug-review instead.
---

# Anti-Bug

Find real defects across a codebase, repair them at the root, and leave evidence anyone can re-run.

## Philosophy

Rules cover the situations someone anticipated. These principles are for the rest, and each one resolves to a behavior rather than a slogan.

**A bug is a gap between intent and behavior — so establish intent first.** With no written intent, reading code only reflects it back, and every finding is an opinion. Write down what the system is supposed to do before naming anything broken.

**The code cannot testify about itself.** An implementation is the defendant, not the witness. Expected values come from the specification, a business rule, a contract, or a person — never from running the current code and recording what it printed.

**Green is a clue, not a verdict.** A passing suite says "nothing here caught it," which is a statement about the tests. Prove a fix by making a test fail without it.

**A bug found once is a habit, not an accident.** The same missing guard, the same unparameterized query, the same unawaited call. Finding one occurrence and reporting it fixed is a false claim about the codebase.

**The most expensive bugs never crash.** They return 200, complete successfully, and are wrong — a discount applied twice, a limit that does not hold, an order someone else can read. No linter has an opinion about those, which is exactly why they survive to production.

**Report what can be proven, label what is suspected, and never blur the two.** Trust is spent once. A report of eight verified findings outranks sixty where twenty are imagined.

**Silence about what was not checked is a form of lying.** Coverage stated honestly is a professional result; coverage implied is a trap for whoever ships next.

**When the rules run out, ask what the user loses.** Severity, ordering, and when to stop all resolve to blast radius: money, data, access, trust, time — in that order.

## Why this skill is shaped the way it is

Three failure modes destroy an automated bug hunt, each measured, each driving a rule.

**Crying wolf.** Google's static-analysis team found developers abandon a tool once roughly 10% of its reports are "effective false positives" — findings nobody acts on.

**Plausible but wrong fixes.** Generate-and-validate repair systems produced patches that passed the whole test suite yet were correct only 2-8% of the time; 104 of GenProg's 110 plausible patches were semantically equivalent to deleting functionality.

**Agents narrating success they never achieved.** Across 547 real agentic-coding incidents: 40.4% constraint violations, 24.5% destructive operations, 15.7% falsely claiming an action was completed, 9.7% fabricating terminal logs.

`references/research-basis.md` carries the full evidence with citations. Read it when a judgement call needs grounding or when someone asks why the skill insists on something.

## The five rules

**1. Evidence bar.** Every finding carries a reproduction (a command, a failing test, an input) or a concrete trace with exact `file:line` per hop. Without either it is `Suspected`, ranked below everything confirmed, never silently promoted. A small confirmed count is the honest answer; padding it is how the report becomes worthless.

**2. Root cause, and every sibling.** Fix the cause, then search the codebase for the same pattern. Record each occurrence under the same finding. NIST's SSDF makes root-cause analysis its own practice (RV.3) for exactly this reason: it is what reduces future defect frequency rather than today's count.

**3. Never weaken to go green.** Deleting a branch, loosening an assertion, widening a catch, skipping a test, relaxing validation — all make a suite pass and leave the bug in production. If a fix requires removing behavior, that is a product decision: document it under *Needs decision* and stop.

**4. No claim without an artifact.** "Tests pass" means the command and its real output are in the ledger. Never write a result that was not observed. If something could not be run — no network, no service, no credentials — say so and mark it `Unverified`.

**5. The oracle comes from the specification, never from the implementation.** When writing a test, the expected value is derived from a business rule, a contract, a document, or a person. Running the current code and recording its output as `expected` produces a test that locks the bug in permanently and reports success. This is the single easiest way to do real damage here, and it is invisible afterward — the test is green, the suite grew, and the defect is now protected by a regression test.

## The ledger

Model performance degrades for information in the middle of a long context, and a repository sweep overflows any window. So findings live on disk, in `.anti-bug/findings.json`, managed by `scripts/ledger.py`:

```bash
python scripts/ledger.py init
python scripts/ledger.py rule --area checkout \
  --text "Loyalty discount is redeemable once per customer per campaign" \
  --source "docs/campaigns.md:14" --confidence stated
python scripts/ledger.py add --severity critical --category business-logic \
  --title "Loyalty discount redeemable N times under concurrency" \
  --location "src/billing/redeem.py:88-94" --status confirmed --rule R-01 \
  --repro "30 parallel POST /redeem with one code -> 30 credits applied" \
  --evidence "read-check-write with no unique constraint and no transaction"
python scripts/ledger.py set F-003 --status fixed --fix-commit abc1234 --test tests/test_redeem.py::test_single_redemption
python scripts/ledger.py report            # markdown for the final document
python scripts/ledger.py stats             # flags anything still open or fixed without a test
```

The ledger is also an **attempt history**, not only a findings list. Record every fix attempt and its measured outcome:

```bash
python scripts/ledger.py attempt F-003 --mechanism "added unique index on (customer, campaign)" \
  --outcome fail --measured "test still red: 2 of 30 requests succeed" \
  --failure-class repairable --note "index correct; the read still happens outside the transaction"
```

This matters because history used as a replayable record of mechanisms and their measured outcomes outperforms history used as loose guidance — an agent that can look up what was already tried, and what actually happened, stops re-proposing it. Concretely, before any new attempt on a finding, read **every** prior attempt on it in full, and trust the measured outcome over what an attempt claimed about itself.

## Phase 0 — Context and the business rules register

Finding defects requires more complete understanding than any other review activity, and reviewers working in unfamiliar code produce measurably shallower feedback. This phase is not overhead; skipping it converts everything after it into guesswork.

Run `python scripts/recon.py` first — it detects languages, entry points, tests, config and risk surfaces, and prints the commands available for this stack. Then read what it points at: README, architecture docs, manifests, CI config, migrations. If git history exists, run `python scripts/hotspots.py` to rank files by change frequency crossed with bug-fix density. Top-ranked files are where to *start*; roughly a third of files are needed to cover 80% of distinct bugs, so they are never where to stop.

Write a **Context Summary**: what the system does and for whom; stack and versions from manifests; entry points; the main data flow traced end to end; data layer and transaction boundaries; external integrations; the auth model including where authorization is merely *assumed*; and a blast-radius ranking — money, auth, personal data, deletion, anything irreversible.

Then write the **Business Rules Register**, which is what makes the business-logic pass possible at all. For each rule: the area, the rule as the business would state it, its source, and its confidence.

| ID | Area | Rule | Source | Confidence |
|---|---|---|---|---|
| R-01 | Checkout | Discount code redeemable once per customer per campaign | `docs/campaigns.md:14` | stated |
| R-02 | Refunds | Refund total may never exceed the captured amount | inferred from `refund.py:40` | inferred |

Confidence is the load-bearing column. **A `stated` rule is a fact; an `inferred` rule is a question.** Inferring a rule from the code and then testing the code against it proves only that the code agrees with itself. So: when a rule is unclear and the user is reachable, ask — do not guess. When they are not reachable, mark it `inferred`, say so in the finding, and never mark a finding derived from an inferred rule as `Confirmed` — it is `Needs decision`.

## Phase 1 — Baseline

Install, build, run the full suite, run linters, type checkers, and the dependency audit. Record exact commands and real output with `ledger.py baseline`. Everything later compares against this; without it, "no new failures" is unprovable.

Pre-existing failures are data, not obstacles — a test that was already red marks where the team stopped caring, which is often where bugs live. Do not fix them yet, and do not modify production code in this phase.

If the build cannot run, record why and continue with static analysis only. A static-only hunt honestly labeled is valuable; one that implies it executed the code is a fabrication.

## Phase 2 — The sweep

Ordered by yield per unit of effort, so an interrupted run still delivers the highest-value findings. Read `references/detection-playbook.md` for patterns and grep recipes, `references/business-logic.md` for Pass BL, `references/security-audit.md` for Pass B, and `references/toolchains.md` for per-stack commands.

**Pass BL — Business logic.** First, because it is the only class no tool covers. MITRE's CWE-840 category exists precisely because these flaws require "domain-specific knowledge or business rules" to judge, and "do not produce clear errors or undefined behavior at the code level." OWASP's testing guide is blunter: automated tools cannot understand context, so this remains manual work. Walk each rule in the register against the code: value and quota validation, calculations (price, discount, tax, balance, rounding, currency), flow and state (skippable steps, illegal transitions, replayable actions), logic-level authorization, concurrency on transactions and stock, hidden assumptions (empty, zero, negative, dates, timezones, extremes), and feature abuse — behavior that matches the code but defeats the business intent. `references/business-logic.md` gives prevention, detection and verification for each, with test scenarios.

**Pass A — Error and failure handling.** The highest-yield mechanical pass: 92% of catastrophic production failures came from mishandling errors the software had *already detected*, and 35% from three trivial patterns — empty or log-only handlers, over-broad catches that abort, and handlers containing TODO/FIXME. Also: swallowed promise rejections, ignored return codes, retries without backoff or cap, cleanup that skips the error path, messages that lose the cause.

**Pass B — Security.** Trace taint from entry points to sinks rather than grepping for sink names. Walk the CWE Top 25 and OWASP Top 10 against the real attack surface. Authorization deserves the most attention because no scanner can infer who *should* be allowed. Apply extra scrutiny to AI-generated code: roughly 40% of LLM-generated programs in controlled security scenarios contained a CWE.

**Pass C — Correctness and edge cases.** Off-by-one, inverted conditions, operator precedence, integer/float confusion, timezone and DST, currency in floats, mutated shared defaults, boundaries (empty, null, zero, negative, max, duplicate, malformed, unicode, very large).

**Pass D — Concurrency and state.** Narrower than its reputation: 96% of concurrency bugs manifest with only two threads, 69% are atomicity violations, 32% order violations. Look for pairs — check-then-act on shared state, non-atomic read-modify-write, missing transaction boundaries, `await` inside a lock, unawaited async calls, request data in global state.

**Pass E — Data integrity.** Missing constraints and indexes, irreversible or destructive migrations, multi-statement writes without a transaction, unvalidated input reaching persistence, cascade deletes, nullable columns assumed non-null, dual writes that can diverge.

**Pass F — Performance and resources.** N+1 queries, unbounded results, missing indexes on filter columns, unclosed handles, unbounded caches and queues, blocking I/O on an event loop.

**Pass G — Configuration and deployment.** Hardcoded secrets and hosts, unvalidated env vars, development settings reachable in production, dependency advisories, drift between `.env.example` and what the code reads.

**Pass H — Test quality.** Tests asserting nothing meaningful, tests mocking the unit under test, and flakiness — classify before blaming production code: 45% of flaky tests come from async wait, 20% concurrency, 12% test-order dependency.

**Batching and effort.** Defect detection collapses as review volume rises — effectiveness drops sharply past roughly 400 lines in one sitting. Keep each batch to one module or a few hundred lines and write findings immediately. Allocate effort adaptively: when a pass keeps producing findings, stay; when several batches in an area come back empty, move on rather than grinding. And when three attempts cluster around small variations of the same idea with flattening returns, that is a local optimum — switch to a structurally different angle instead of another marginal tweak.

## Phase 3 — Triage

Resolve every finding to one state before fixing anything:

- **Confirmed** — reproduced, or traced end to end with `file:line` evidence, against a `stated` rule. Eligible for fixing.
- **False positive** — investigated and disproved. Keep it with the disproving evidence so the next run does not re-report it.
- **Suspected** — plausible, unproven. Investigate until confirmed or disproved. Never fix a suspected issue blindly: an unverified fix to a non-bug is pure regression risk.
- **Needs decision** — requires a product, business or architecture call, or rests on an `inferred` rule. Document options and trade-offs; do not implement.

Classify with cumulative evidence, not a single observation. One failed reproduction attempt does not make a finding a false positive — the harness may be wrong, the precondition missing, the environment different. Equally, a finding closed earlier reopens the moment new evidence appears. Severity is assigned by blast radius: **Critical** (security hole, data loss, core-flow crash, money wrong), **High** (core feature wrong in common conditions), **Medium** (edge cases, notable performance, missing error handling), **Low** (maintainability).

Then map dependencies between findings and set fix order.

## Phase 4 — Fix

Critical → High → Medium → Low; within a severity, whatever unblocks others first. On a branch (`fix/anti-bug-sweep`) with one commit per finding: `fix(billing): enforce single redemption [F-003]`.

**Before writing the change** — the cheapest bug is the one not introduced:
- Name the rule or contract the change must satisfy, and where it is written down.
- Name what could break elsewhere: callers, schema, API shape, other tenants.
- Confirm any new dependency actually exists on its registry. Hallucinated package names are a live supply-chain attack surface.

**Then, for each confirmed finding:**

1. **Write the failing test first**, with the expected value derived from the specification (rule 5). It must fail against current code for the right reason — not an import error.
2. **Make the minimal correct change at the root cause.** Follow existing style and architecture. Do not refactor or reformat unrelated code; every unrelated line hides the real fix during review.
3. **Fix every sibling occurrence.** If a sibling sits outside the agreed scope, record it as its own finding rather than quietly editing it.
4. **Run the new test, then the surrounding suites.** Paste real output.
5. **Revert-check:** undo the fix and confirm the test goes red. If it stays green, the test does not cover the defect. Mutation-style checks like this correlate with real fault detection considerably better than line coverage.

**When a fix attempt fails**, record the attempt and classify it before trying again — this is what stops an agent from burning a session re-proposing variants of the same idea:
- **Flawed mechanism** — the approach itself is wrong. Do not retry it. Change mechanism.
- **Repairable** — the approach is sound, the implementation slipped. Retry **only** after locating the actual defect in the code, not guessing from the symptom, and only with a specific fix in hand.
- **Environmental** — harness, fixture, or dependency, not the fix. Repair the environment, then re-measure.
- **Needs decision** — larger or riskier than planned. Stop the item and document it. A half-applied fix is worse than none.

Never negotiable while fixing: no hardcoded secrets; no deleted, skipped or weakened tests; no loosened validation to make something pass; security fixes use framework or established-library features rather than hand-rolled sanitizers; migrations stay reversible and non-destructive; dependency bumps take the smallest version that resolves the issue.

## Phase 5 — Verify

Change stance deliberately: review the diff as though someone else wrote it and you suspect them.

- Read the complete diff against the baseline, file by file.
- For each fix, ask whether it addresses the cause or masks the symptom.
- Check every test added: does its expected value come from the specification, or was it copied from what the code produced? Rule 5 fails silently, so it has to be checked explicitly.
- Look for new bugs introduced: changed behavior elsewhere, new edge cases, performance regressions, broadened permissions.
- Look for leftovers: debug prints, commented-out code, stray TODOs, accidental changes.
- Re-run the sibling pattern search — confirm none was missed.
- Re-run every original reproduction and confirm it no longer reproduces.
- Run the full suite, linters, type checkers, and the vulnerability audit. Compare against Phase 1: no new failures, no new lint or type errors, coverage not decreased. **Accept the result only if it is no worse than baseline on every recorded check** — a fix that trades one failure for another has not improved anything.
- Smoke test every entry point from the Context Summary. A suite that passes while the app will not boot is a false pass.

If verification finds problems, return to Phase 4 for those items and repeat. Record what this phase caught — those entries are the most instructive in the final report.

Then confirm completeness: `python scripts/ledger.py stats` flags any finding without a final status and any fix recorded without a test.

## Phase 6 — Report

Generate from the ledger so the report cannot drift from what was recorded:

```bash
python scripts/ledger.py report > docs/anti-bug-report.md
```

Expand it with the narrative sections using `assets/report-template.md`. It must stand alone for someone who never saw the session: context summary, business rules register, executive summary with a release-readiness verdict (Ready / Ready with conditions / Not ready), findings table, per-fix detail, baseline-vs-final comparison, what was not fixed and why, new issues found during remediation, anything affecting APIs, schemas, config or deployment with rollback steps, and prioritized follow-ups.

Close the conversation with the short version: findings by severity, how many fixed, the verdict, and the single most urgent remaining item.

## Operating limits

Bug fixing is a state-mutating task, and autonomy shifts risk from static errors to behavioral ones — destructive operations accounted for 24.5% of recorded agentic-coding incidents.

- Never run `pkill`, `kill`, `killall`, or terminate processes that are not ones this session started.
- Never drop, truncate, or mass-delete data, and never run a migration against anything but a disposable local database.
- Never rewrite git history, force-push, or commit to a shared branch.
- Never disable a security control, a CI gate, or TLS verification to make something pass.
- Keep edits inside the agreed scope. Findings outside it get recorded, not silently fixed.

## When to stop and ask

Stop when: a business rule is unclear and cannot be settled from documentation or tests; a fix changes a public API, a schema, or a documented behavior; a migration would touch production data; a dependency needs a major bump; or the security fix requires knowing an authorization policy that lives in someone's head.

If the user is unavailable, do the preparatory work, write the decision up with options and a recommendation, and leave it in *Needs decision*. That is more useful than a confident guess about someone else's business.
