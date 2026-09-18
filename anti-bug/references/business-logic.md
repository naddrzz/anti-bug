# Business Logic Reference

Read this for Pass BL. It covers the class of defect where the code runs without error, every test passes, every scanner is silent — and the result violates the rule the business actually operates by.

## Why this class needs its own pass

MITRE classifies these under **CWE-840 (Business Logic Errors)**, a category defined by the fact that judging them "requires domain-specific knowledge or business rules," and whose members "do not produce clear errors or undefined behavior at the code level." Its member weaknesses map almost exactly onto the subcategories below: CWE-283 Unverified Ownership, CWE-639 Authorization Bypass Through User-Controlled Key, CWE-640 Weak Password Recovery, CWE-708 Incorrect Ownership Assignment, CWE-770 Allocation of Resources Without Limits, CWE-826 Premature Release of Resource, CWE-837 Improper Enforcement of a Single Unique Action, CWE-841 Improper Enforcement of Behavioral Workflow.

OWASP's Web Security Testing Guide reaches the same conclusion from the testing side: automated tools "find it hard to understand context, hence it's up to a person to perform these kinds of tests," and business logic testing "remains a manual art relying on the skills of the tester." PortSwigger's characterization is the most useful one-liner: these flaws arise when developers "fail to anticipate unusual application states," and "won't be exposed by normal use of the application."

The practical consequence: **no amount of linting, typing, scanning or coverage finds these.** Only a written rule, compared against actual behavior, does. That is why Phase 0's Business Rules Register is a precondition for this pass rather than a nicety.

## The register comes first

Every finding in this pass cites a rule ID. A finding with no rule behind it is an opinion about how the code ought to behave.

```
R-01 | Checkout | A discount code is redeemable once per customer per campaign | docs/campaigns.md:14 | stated
R-02 | Refunds  | Refund total may never exceed the captured amount            | inferred from refund.py:40 | inferred
```

A `stated` rule can produce a `Confirmed` finding. An `inferred` rule cannot — it produces `Needs decision`, because testing code against a rule inferred from that same code only proves the code agrees with itself. When the rule is unclear and the user is reachable, **ask**. Guessing here does not produce a wrong finding; it produces a confident wrong fix.

---

## BL-1. Business rule validation — limits, quotas, thresholds, eligibility

**The shape.** A rule exists ("maximum 3 active subscriptions", "minimum order $10", "students only"), and the code either checks it in one place and not another, checks it on the client only, or checks it before a state change that invalidates it.

**Prevent.** Put the rule in one function with the rule ID in its name or docstring, and call it from every path. Enforce at the persistence boundary, not just the handler — a database constraint holds under concurrency and refactoring; an `if` in a controller does not. Make the limit a named constant with its source cited, never an inline literal.

**Detect.** For each rule in the register, find every code path that can change the constrained quantity, not just the obvious one. Bulk endpoints, admin overrides, imports, background jobs, and retries are where the check is usually missing. Then test the boundary on each: limit−1, limit, limit+1, and limit reached through two different paths.

Test scenarios:
- Reach the quota through the normal endpoint, then exceed it through the bulk/import path.
- Satisfy eligibility, start the action, make yourself ineligible, complete the action.
- Submit exactly the boundary value, then boundary+1, through every path that accepts it.

**Verify the fix.** The test asserts the rule as the register states it, in the register's units. Prove the check holds at the boundary and on *every* path found in detection — one passing path is not the fix. If a database constraint was added, prove it by attempting the violation with the application-level check bypassed.

---

## BL-2. Calculation — price, discount, tax, balance, rounding, currency

**The shape.** Arithmetic that is individually reasonable and collectively wrong: discount applied after tax when policy says before, rounding at each line instead of the total, a percentage of a percentage, floats accumulating cents, or two currencies added without conversion.

**Prevent.** Never represent money as a binary float — use integer minor units or a decimal type. Fix the order of operations once, in one place, documented against the rule. Make currency part of the type, not a separate column read by convention. Decide rounding mode and rounding point explicitly (half-up at the total, versus half-even per line, are different products).

**Detect.** Recompute independently. Take real inputs, calculate the expected result by hand or in a throwaway script from the *rule*, and compare — this is the only reliable oracle, and the reason rule 5 exists. Then look specifically for: order of operations against the stated policy, rounding applied more than once, division before multiplication, and any place a total is recomputed rather than carried.

This subcategory is where **property-based testing** pays off most: invariants are easy to state and hold across all inputs. Empirically, property-based tests caught mutations roughly 50× more often per test than example-based unit tests in a controlled Python study, with exception-raising properties the single most effective category — and 55% of the mutations they caught were caught by a *single* input, meaning the value comes from thinking in properties, not from generating volume.

Properties worth asserting here:
- Sum of line totals equals the order total, for any basket.
- Applying a 0% discount changes nothing; applying 100% yields zero, never negative.
- Discount then tax and tax then discount differ — assert which one the rule requires.
- Total is never negative; refund never exceeds capture; balance after a reversed pair of operations equals the balance before (a metamorphic relation).

**Verify the fix.** Recompute expected values from the rule, never from the new code. Include at least one case with a repeating decimal (e.g. dividing by 3), one at a rounding boundary (x.005), and one crossing currencies if the system has more than one.

---

## BL-3. Flow and state — skippable steps, illegal transitions, replayable actions

**The shape.** CWE-841 (Improper Enforcement of Behavioral Workflow) and CWE-837 (Improper Enforcement of a Single, Unique Action). A checkout that can be completed without payment because step 3 is reachable directly. An order that can move from `shipped` back to `pending`. A submit button pressed twice that charges twice.

**Prevent.** Model state explicitly: an enum plus an allowed-transition table, and one function that performs transitions and rejects everything not in the table. Derive the current step from server-side state, never from a client-supplied step number or a hidden field. For anything that changes state and can be retried, require an **idempotency key**: the server stores the result of the first request under that key and returns the same result for repeats — the pattern payment platforms standardized precisely because network retries are unavoidable. Make the key the client's, generated per logical operation, and compare incoming parameters against the original to catch accidental reuse.

**Detect.** Draw the intended state machine from the register, then enumerate the transitions the code actually permits and diff the two. Every transition present in code but absent from the model is a finding. Separately, for each state-changing endpoint: can it be called twice? Out of order? Without its predecessor? After the flow completed? **Model-based and FSM-based testing** exists for exactly this comparison, and is worth running where a state machine is explicit enough to encode.

Test scenarios:
- Call the final step directly with a valid session and no preceding steps.
- Replay the same request twice with identical payloads; then twice in parallel.
- Drive the entity to a terminal state, then attempt each earlier transition.
- Complete a flow, then replay a mid-flow step with the original token.

**Verify the fix.** The test drives an illegal transition and asserts rejection with the *correct* error, plus asserts the state did not change. For idempotency, assert that two identical requests produce one effect and the same response body, and that the second returns the stored result rather than re-executing.

---

## BL-4. Logic-level authorization — access and modification beyond entitlement

**The shape.** CWE-639 and CWE-283. Authentication works; authorization is missing, partial, or derived from something the user controls. The list endpoint scopes to the caller and the detail endpoint does not. The UI hides the button and the API does not. A `role` or `user_id` arrives in the request body and is trusted.

**Prevent.** Scope at the query, not in a branch: `Order.get(id, user=request.user)` cannot be forgotten in a way that silently succeeds, while `if order.user != request.user` can be omitted entirely. Derive identity only from the authenticated session or a verified token claim. Default to deny — an unlisted action is refused rather than allowed.

**Detect.** Build a route inventory and answer four questions per route: is authentication required and enforced server-side; is authorization checked against the *specific object*; where does identity come from; and does the check happen before the effect? Then test cross-tenant access on every object-scoped route, not a sample — this is where per-route inconsistency lives.

Test scenarios:
- User A requests user B's object by ID on every object-scoped route.
- Send a `user_id`/`role`/`tenant_id` in the body that differs from the session's.
- Call a bulk endpoint with a list mixing owned and unowned IDs (checks often validate the first only).
- Use a valid token from a lower-privileged role against every privileged route.

**Verify the fix.** Assert 404 or 403 — and prefer 404 where existence itself is sensitive. Assert the object was not modified. Add the cross-tenant test for *every* route the sibling search turned up, not only the reported one.

---

## BL-5. Concurrency on business state — transactions, stock, balances, redemptions

**The shape.** The rule holds in sequence and breaks under parallelism. The documented case: a $20,000 discount redeemed 30 times in parallel produced $600,000 of fee-free transactions, and the vendor's *first* patch was incomplete — a race still permitted multiple redemptions. That detail is the lesson: an obvious fix to a concurrency bug frequently does not close it.

**The mechanism** is almost always check-then-act or read-modify-write across a boundary without atomicity — 69% of real concurrency bugs are atomicity violations, and 96% involve just two actors, so look for pairs rather than exotic interleavings.

**Prevent.** Make the database the arbiter: a unique constraint for "only once", a conditional update (`UPDATE ... WHERE stock >= n`) for decrements, `SELECT FOR UPDATE` or optimistic version columns for read-modify-write. Keep the check and the write inside one transaction, and confirm the transaction opens *before* the read, not after. Application-level locks that do not survive multiple processes are not locks.

**Detect.** For every rule expressing "once", "at most N", or "not below zero", find the code that enforces it and ask whether the enforcement is atomic with the write. Then actually run it in parallel — a 20-request burst against a local instance settles the question faster than reading.

Test scenarios:
- N parallel identical requests against the once-only action; assert exactly one effect.
- Two concurrent decrements of the last remaining unit.
- Parallel refund requests summing to more than the captured amount.
- Same-key idempotent request sent twice simultaneously, not sequentially.

**Verify the fix.** The test must run genuinely in parallel and assert the invariant on the *final persisted state*, not on response codes. Run it repeatedly (20+ iterations) — a race that fails one run in ten passes a single run. Assert no negative stock, no double credit, exactly one row.

---

## BL-6. Edge cases and hidden assumptions

**The shape.** The rule is right, the code is right, for the inputs someone imagined. Zero-item orders. A negative quantity producing a credit. A discount larger than the total. A refund on an already-refunded order. A date range ending before it starts. Midnight in a timezone that skipped an hour. A name with an apostrophe. A 10,000-item basket.

**Prevent.** Validate at the boundary with explicit ranges rather than types alone — `quantity: int` permits `-5`. Reject rather than clamp silently, unless the rule says clamp. Store timestamps in UTC with the originating zone kept separately when it matters to the rule ("orders before midnight local" needs the zone). State assumptions in the code where they are made, so the next reader can falsify them.

**Detect.** For each rule, list the values that make it degenerate: empty, zero, negative, one, maximum, duplicate, and just-past-the-boundary. Then find which of those the code actually rejects. Pay particular attention to arithmetic that is only valid for positive values, and to dates near month, year, and DST boundaries.

Test scenarios:
- Quantity `0` and `-1`; discount exceeding the total; refund exceeding capture.
- Date range where end precedes start; an event during a DST transition; 29 February.
- Unicode, apostrophes and very long strings in fields used for lookup or matching.
- A batch at the documented maximum, and one item beyond it.

**Verify the fix.** Assert the *specified* behavior for each degenerate input — rejection with a clear error, or the defined fallback. "It no longer crashes" is not the criterion; behaving as the rule says is.

---

## BL-7. Feature abuse — working as coded, defeating the business intent

**The shape.** No rule is technically violated and the outcome is still wrong: referral bonuses farmed with self-referrals, free trials restarted with `user+1@`, loyalty points accrued then the order cancelled, bulk endpoints used to enumerate the customer list, a resource held to block others. OWASP's guide lists exactly these — price manipulation on the summary page, resource locking while prices move, cancelling after points accrue.

**Prevent.** Write abuse cases alongside requirements: for each feature, one sentence on how someone profits by using it against intent. Make the accrual conditional on the irreversible event (points on settlement, not on order creation). Rate-limit and cap anything that grants value. Treat email normalization, device fingerprints and payment instruments as identity signals where "one per customer" is the rule.

**Detect.** For each value-granting feature, ask three questions: what does a user gain, how fast can they repeat it, and what stops them? Then walk the reversal path — what happens to granted value when the triggering action is undone? This is the highest-yield question in the pass and the one almost never tested.

Test scenarios:
- Complete the value-granting action, then reverse the trigger; assert the value is reversed too.
- Refer yourself; sign up twice with address aliases; restart a trial.
- Repeat the action at maximum rate and see where the cap engages.
- Hold a limited resource without completing, and check whether it is ever released (CWE-826, CWE-770).

**Verify the fix.** Assert the invariant the business cares about — net value granted, not the response of a single request. Include the reversal case explicitly, and confirm the cap or release actually triggers rather than merely existing in code.

---

## Testing methods that work on this class

Ordinary example-based tests are weak here because the author picks the examples, and the examples encode the same assumption the bug does. Three methods break that symmetry:

**Property-based testing.** Assert invariants over generated inputs instead of specific values ("total ≥ 0 for every basket", "sum of parts equals whole"). ~50× more mutation-catching per test than unit tests in a controlled study, with most catches on the first input. Tools: Hypothesis (Python), fast-check (JS/TS), jqwik (Java), gopter/rapid (Go), PropEr (Erlang), proptest (Rust), PHPUnit + Eris (PHP).

**Metamorphic testing.** When the correct output is unknown, assert relations between runs: reversing an operation restores the prior state; adding an item never decreases the total; applying a discount twice at half the rate is not the same as once at full rate. A survey of the field documents 295 distinct real faults found across 36 tools this way — it is the standard answer to the oracle problem, which is exactly the problem business logic presents.

**Model-based / state-machine testing.** Encode the intended state machine, generate transition sequences, and compare against implementation behavior. Directly targets CWE-841.

One recent result is worth knowing when deciding how much to automate here: an agent built on Claude Code that inferred properties from code and documentation and wrote Hypothesis tests found real bugs across 100 Python packages, with 56% of its reports valid and 86% valid among its top-scored ones — and reported bugs merged into NumPy and other projects. It is a preprint, not peer-reviewed, and its validity rate is also a useful calibration: even a good agentic pipeline produced a substantial minority of invalid reports, which is precisely why the evidence bar in SKILL.md exists.

## Business logic risk in AI-written code

Bug taxonomies for LLM-generated code put the dominant categories on the intent side rather than the syntax side: *misinterpretation*, *prompt-biased code*, *missing corner case*, *hallucinated object*, and *non-prompted consideration* — from a study of 333 bugs across three code models, validated with a practitioner survey. Every one of those produces code that runs and is wrong, which is the definition of this class.

The practical implication: AI-written code gets Pass BL *first*, not last, and the register is what it is checked against. Code generated from a prompt satisfies the prompt; the business rule is usually in neither.
