---
name: anti-bug-review
description: Read-only defect review of a codebase - deep context and business-rule capture, perspective-based sweeps (business logic, error handling, security, correctness, concurrency, data integrity, performance, config, test quality), reproduction of each finding, severity calibration, and a decision-ready audit report with recommended fixes that are described but never applied. The codebase is left byte-identical. Use this whenever findings are wanted without changes, such as "review this codebase", "audit it but do not touch anything", "code review", "PR review", "second opinion on this code", "security assessment", "due diligence", "is this safe to ship", "what is wrong with this code", "review only", "report only", "read-only review", "check it without changing anything". Use it equally for business-logic defects where nothing crashes but the result is wrong - a wrong total, discount, tax or balance, a skippable step, a replayable action, a quota that does not hold, a user seeing another user's data. Prefer this over anti-bug whenever the user wants a report rather than a repaired repo, when the code belongs to someone else, or when changes need approval first. If the user actually wants the bugs fixed, use anti-bug instead.
---

# Anti-Bug Review

Read a codebase hard, prove what is broken, and hand back a report someone can act on — without changing a single byte.

## What makes a review different from a repair

This is not the anti-bug skill minus the fixing. The stance is different, and one fact drives the difference:

**In a repair run, a wrong finding usually dies quietly.** The fix fails, the test will not go red, the sibling search comes up empty — the work itself filters mistakes out before anyone sees them.

**In a review, there is no filter.** Every finding goes straight to a human who will spend real hours on it, or dismiss the whole report because two items were imagined. Google's static-analysis team measured where that cliff sits: developers abandon a tool once roughly 10% of its reports are findings nobody acts on, and the real findings die with the false ones.

So the burden shifts. In a repair, the fix is the product. **Here the report is the product**, and its accuracy, ordering and honesty are the whole job.

Every rule below traces to published evidence, collected in `references/research-basis.md`. Read it when a judgement call needs grounding, when calibrating how much to trust a signal, or when someone asks why the review insists on something.

## Philosophy

Rules cover anticipated situations. These are for the rest, and each resolves to a behavior.

**A bug is a gap between intent and behavior — so establish intent first.** With no written intent, reading code only reflects it back, and every finding is an opinion.

**The code cannot testify about itself.** An implementation is the defendant, not the witness. Expected behavior comes from a specification, a business rule, a contract, or a person — never from running the code and recording what it printed.

**Green is a clue, not a verdict.** A passing suite says "nothing here caught it," which is a fact about the tests, not the code.

**A finding that cannot be reproduced is a question, not a defect — so file it as one.** Questions are welcome in a review and belong in their own section. Questions dressed as findings are what destroy the report's credibility.

**A bug found once is a habit, not an accident.** Report every occurrence, not the one that happened to surface.

**The most expensive bugs never crash.** They return 200, complete successfully, and are wrong. No linter has an opinion about those, which is why they reach production.

**The report is the product.** No later step will catch a mistake in it. Rank by what it costs the reader to be wrong.

**Silence about what was not checked is a form of lying.** Say what was covered, what was skipped, and why.

**Leave no trace.** The repository is byte-identical when the review ends. A reviewer who edits the thing under review has destroyed the evidence and the trust in one move.

**When the rules run out, ask what the user loses.** Severity and ordering resolve to blast radius: money, data, access, trust, time.

## The read-only contract

"Read-only" needs a precise boundary, because some ordinary review actions do write.

**Work on a disposable copy whenever possible.** This turns every question below into a non-question:

```bash
git -C <repo> worktree add /tmp/review-copy HEAD    # preferred, if git
# or
cp -r <repo> /tmp/review-copy                        # any repo
```

Then install, build, and run freely in the copy. Nothing touches the original.

If reviewing in place, the tiers are:

**Always allowed** — reading files; `grep`/`rg`/`find`; `git log`, `git diff`, `git show`, `git blame` (never `checkout`, `reset`, `stash`, `clean`); linters, type checkers, static analysis, dependency audits that read manifests.

**Allowed only with permission, because it writes** — installing dependencies (`npm install` writes `node_modules/` and can rewrite lockfiles; use `npm ci` or a copy); building (writes `dist/`, `target/`, `__pycache__/`); running the test suite (may write to a dev database, create fixtures, or hit the network). Ask once, covering all of them, rather than per command.

**Never** — editing source; running migrations; writing to any shared or production database; `git` operations that change refs, history, or the working tree; killing processes this session did not start; deleting anything.

The review's own artifacts — ledger, reproductions, notes — live in a workspace **outside** the repository, so the tree stays clean. `scripts/ledger.py init` sets this up and prints where.

Prove it rather than asserting it. Snapshot before, check after:

```bash
python scripts/integrity.py snapshot --repo <path>   # at the start
python scripts/integrity.py check --repo <path>      # before writing the report
```

The check output goes in the report. A reviewer's claim to have changed nothing is exactly the kind of unverifiable claim this skill refuses to accept from anyone else.

## The four rules

**1. Evidence bar, tightened.** Every finding in the main table carries a reproduction — a command with its real output, a failing test, or an input that triggers it — or a complete trace with exact `file:line` per hop. Anything less goes in the **Questions** section instead, phrased as a question. A report of eight proven findings outranks forty where twelve are imagined, because the second report gets nothing fixed.

**2. Root cause, and every occurrence.** Identify the cause, then search for the same pattern everywhere and list every hit under the finding. A defect found once is usually a habit. NIST's SSDF makes root-cause analysis its own practice (RV.3) because it is what reduces future defect frequency rather than today's count.

**3. No claim without an artifact.** "Tests pass", "the build is clean", "this is exploitable" — each means the command and its real output are recorded. Never write a result that was not observed. If something could not be run, say so and mark the finding `Unverified`. Across 547 real agentic-coding incidents, 15.7% involved falsely claiming an action was completed and 9.7% fabricating terminal output; those two numbers are why this rule outranks thoroughness.

**4. Recommend, never apply.** Every finding carries a proposed fix described precisely enough to act on — the approach, the files, the risk — and nothing is edited. If a fix seems urgent, say so in the verdict; that is the reviewer's lever, not the keyboard.

## The ledger

Long contexts degrade in the middle and a repository sweep overflows any window, so findings live on disk — outside the repo:

```bash
python scripts/ledger.py init --repo <path>          # prints the workspace location
python scripts/ledger.py rule --area checkout \
  --text "Discount code redeemable once per customer per campaign" \
  --source "docs/campaigns.md:14" --confidence stated
python scripts/ledger.py add --severity critical --category business-logic \
  --title "Discount redeemable N times under concurrency" \
  --location "src/billing/redeem.py:88-94" --status reproduced --rule R-01 \
  --perspective attacker \
  --repro "30 parallel POST /redeem with one code -> 30 credits applied" \
  --evidence "read-check-write, no unique constraint, no transaction" \
  --recommendation "Unique constraint on (customer, campaign) plus SELECT FOR UPDATE inside one transaction" \
  --effort S --fix-risk medium
python scripts/ledger.py question --about "src/auth/session.py:40" \
  --text "Sessions are never invalidated on password change. Intended, or an oversight?"
python scripts/ledger.py stats      # flags anything unproven sitting in the findings table
python scripts/ledger.py report     # the review document
```

`--effort` is S/M/L and `--fix-risk` is low/medium/high. Both exist because a reader deciding what to do this week needs cost next to severity; a report that ranks only by severity hands them half the decision.

## Phase 0 — Context, business rules, read-only setup

Finding defects requires more complete understanding than any other review activity, and reviewers working in unfamiliar code produce measurably shallower feedback — the defect comments they do produce skew toward "uncomplicated logical errors." This phase is where review quality is actually decided.

Set up first: take the integrity snapshot, initialize the ledger, and decide copy-vs-in-place.

Run `python scripts/recon.py <repo>` — it detects languages, entry points, tests, config and risk surfaces, and prints available commands. Then read what it points at: README, architecture docs, manifests, CI config, migrations. With git history, `python scripts/hotspots.py <repo>` ranks files by change frequency crossed with bug-fix density; start there, but roughly a third of files are needed to cover 80% of distinct bugs, so never stop there.

Write a **Context Summary**: what the system does and for whom; stack and versions from manifests; entry points; the main data flow end to end; data layer and transaction boundaries; external integrations; the auth model including where authorization is merely *assumed*; and a blast-radius ranking.

Then the **Business Rules Register**, which is what makes the business-logic pass possible:

| ID | Area | Rule | Source | Confidence |
|---|---|---|---|---|
| R-01 | Checkout | Discount redeemable once per customer per campaign | `docs/campaigns.md:14` | stated |
| R-02 | Refunds | Refund total may never exceed captured amount | inferred from `refund.py:40` | inferred |

Confidence is load-bearing. A `stated` rule is a fact; an **`inferred` rule is a question**, and a finding resting on one belongs in the Questions section, not the findings table — testing code against a rule inferred from that same code proves only that the code agrees with itself. When a rule is unclear and the user is reachable, ask.

## Phase 1 — Environment survey

Establish what can actually be observed, and record it. Run the build, the test suite, linters, type checkers, and the dependency audit — in the copy, or after the one permission request. Record exact commands and real output with `ledger.py env`.

Pre-existing failures are findings in their own right: a suite that was already red tells the reader something true about the project's state, and it belongs in the report rather than being quietly worked around.

If nothing can be executed — no dependencies, no services, unsupported platform — record why and continue with static review only. Then say so in the report's scope section and mark findings accordingly. A static-only review honestly labeled is a real deliverable; one that implies execution is a fabrication.

## Phase 2 — The sweep

Read `references/detection-playbook.md` for patterns and grep recipes, `references/business-logic.md` for Pass BL, `references/security-audit.md` for Pass B, `references/toolchains.md` for per-stack commands.

**Read each pass in a named perspective.** Reviewers assigned a specific viewpoint find more defects than reviewers reading generally — around 30% better in controlled experiments, because a narrow focus produces deeper analysis and distinct perspectives overlap less. Passing over the same code as *the attacker*, then as *the accountant*, then as *the operator* surfaces different things than three general readings. Record the perspective on each finding (`--perspective`) so the report shows which lenses were actually used, and which were not.

**Pass BL — Business logic. The accountant's and the abuser's eye.** First, because it is the only class no tool covers: CWE-840 exists precisely because judging these requires "domain-specific knowledge or business rules," and they "do not produce clear errors or undefined behavior at the code level." OWASP is blunter — automated tools cannot understand context, so this is manual work. Walk each register rule against the code: limits and quotas, calculations (price, discount, tax, balance, rounding, currency), flow and state (skippable steps, illegal transitions, replayable actions), logic-level authorization, concurrency on stock and transactions, hidden assumptions, and feature abuse. `references/business-logic.md` has each subcategory with detection scenarios.

**Pass A — Error and failure handling. The operator's eye, at 3am.** The highest-yield mechanical pass: 92% of catastrophic production failures came from mishandling errors the software had already detected, and 35% from three trivial patterns — empty or log-only handlers, over-broad catches that abort, handlers with TODO/FIXME. Also: swallowed rejections, ignored return codes, retries without cap, cleanup skipping the error path.

**Pass B — Security. The attacker's eye.** Trace taint from entry points to sinks rather than grepping sink names. Walk the CWE Top 25 and OWASP Top 10 against the real attack surface. Authorization deserves the most attention because no scanner can infer who *should* be allowed. Apply extra scrutiny to AI-generated code: roughly 40% of LLM-generated programs in controlled security scenarios contained a CWE.

**Pass C — Correctness and edge cases. The hostile user's eye.** Off-by-one, inverted conditions, precedence, integer/float confusion, timezone and DST, currency in floats, mutated shared defaults, boundaries.

**Pass D — Concurrency and state. The second user arriving at the same millisecond.** 96% of concurrency bugs involve only two threads and 69% are atomicity violations, so look for pairs: check-then-act, non-atomic read-modify-write, missing transaction boundaries, unawaited async calls, request data in global state.

**Pass E — Data integrity. The DBA's eye.** Missing constraints and indexes, irreversible or destructive migrations, multi-statement writes without a transaction, cascade deletes, nullable columns assumed non-null, dual writes that can diverge.

**Pass F — Performance and resources. The eye of someone with 100× the data.** N+1 queries, unbounded results, missing indexes on filter columns, unclosed handles, unbounded caches, blocking I/O on an event loop.

**Pass G — Configuration and deployment. The new hire's first deploy.** Hardcoded secrets and hosts, unvalidated env vars, development settings reachable in production, dependency advisories, `.env.example` drift.

**Pass H — Test quality. The eye of whoever inherits this.** Tests asserting nothing meaningful, tests mocking the unit under test, and flakiness — 45% of flaky tests come from async wait, 20% concurrency, 12% order dependency.

**Batching.** Defect detection collapses as review volume rises; effectiveness drops sharply past roughly 400 lines in one sitting. Keep each batch to one module or a few hundred lines, write findings immediately, and move on. When several batches in an area come back empty, move on rather than grinding.

## Phase 3 — Prove it

This is the phase that repair runs get for free and reviews have to do deliberately. The revert-check is unavailable here, so reproduction is the only proof a finding is real.

For each candidate finding, produce the strongest evidence available, in this order:

1. **A runnable reproduction** — a command, script or request with its real output, saved in the workspace so the reader can run it themselves. Minimize it: strip everything not required to trigger the failure, until removing one more thing makes it stop reproducing.
2. **A failing test** written in the workspace (never committed to the repo) whose expected value comes from the specification, not from observed behavior.
3. **A complete trace** — source to sink, `file:line` at each hop, with the missing guard named. This is the right evidence for authorization and taint findings, where a live reproduction may require credentials.

Then set status: **Reproduced** (1 or 2), **Traced** (3), or **Unverified** — could not be checked, with the reason recorded. Unverified items are legitimate; unverified items presented as confirmed are not.

Classify with cumulative evidence, not one observation. A single failed reproduction attempt does not disprove a finding — the harness may be wrong, a precondition missing, the environment different. Record what was tried.

## Phase 4 — Triage and calibrate

Severity is assigned by blast radius, not by how annoying the code is: **Critical** (security hole, data loss, core-flow crash, money wrong), **High** (core feature wrong in common conditions), **Medium** (edge cases, notable performance, missing error handling), **Low** (maintainability). State the preconditions for each — a finding needing local root access is not the one needing a browser, and conflating them is how the Critical list stops being read.

Then add the reader's half of the decision: `--effort` (S/M/L) and `--fix-risk` (low/medium/high) for the recommended fix. A Critical/S/low goes first this week; a Medium/L/high may reasonably wait a quarter.

Sort everything into four buckets: **Findings** (reproduced or traced), **Questions** (unproven, or resting on an inferred rule — phrased as questions), **Observations** (true but not defects: dead code, inconsistencies, upgrade opportunities), and **Not assessed** (what the scope did not cover, and why).

## Phase 5 — Report and verdict

```bash
python scripts/integrity.py check --repo <path>      # prove nothing changed
python scripts/ledger.py report > anti-bug-review-report.md
```

Write the report to the workspace, not the repo, then hand it over. Expand it with the narrative sections using `assets/report-template.md`: scope and method (including which perspectives were used and what was not assessed), context summary, business rules register, findings with evidence and recommendations, questions, observations, the integrity check result, and a prioritized action list.

Lead with the verdict — **Ready / Ready with conditions / Not ready** — and name the conditions. A review that ends without a recommendation has handed the decision back unmade.

Close the conversation with the short version: findings by severity, the verdict, the single most urgent item, and the top open question. The reader opens the report for the rest.

## When to stop and ask

Ask when: a business rule is unclear and cannot be settled from documentation or tests; running the tests would write to something shared; the scope is larger than the time available and something must be dropped; or a security finding depends on an authorization policy that lives in someone's head.

If the user is unavailable, take the most reasonable reading, say at the top of the report which reading was taken, and put the rest in Questions. That is more useful than a confident guess about someone else's business.
