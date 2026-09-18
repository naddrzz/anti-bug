# Finding template (review)

The shape of a finding that survives a skeptical reader. Every field answers a
question they will ask. If a field cannot be filled, that is the signal the item
belongs in **Questions** rather than the findings table.

The difference from a repair run: there is no fix to prove this right later.
Whatever is written here is what the reader acts on, so each claim carries its
own evidence.

```
ID:          F-0NN
Title:       [what is wrong, in the reader's terms - not "bad code in auth.py"]
Severity:    critical | high | medium | low      (by blast radius, not irritation)
Category:    business-logic | error-handling | security | correctness |
             concurrency | data-integrity | performance | config | test-quality
Status:      reproduced | traced | unverified
Perspective: attacker | accountant | operator | hostile-user | dba |
             maintainer | new-hire            (which lens surfaced it)
Location:    path/to/file.ext:LINE-LINE        (a file name alone is not a location)
Rule:        R-0N                              (required for business-logic)

Impact:      Who is harmed, how badly, under what conditions. This decides
             severity and whether anyone acts.

Preconditions: What an attacker or user needs before this bites - authenticated?
             admin? local access? a specific data state? A finding needing local
             root is not the one reachable from the internet, and conflating
             them is how the Critical list stops being read.

Root cause:  Why the defect exists, not the line where it surfaces.
             "Null returned from findUser() is not checked" is a symptom;
             "findUser() signals absence with null while every caller assumes a
             record" is a cause - and points at all the other callers.

Evidence:    A reproduction, or a trace. Reproduction: the exact command and
             its real observed output. Trace: entry point -> transform ->
             failure site, file:line per hop, with the missing guard named.
             Evidence is what the reader re-runs to disagree with you.

Reproduction:
             $ [exact command]
             [actual observed output - never paraphrased, never predicted]

Expected:    [what should happen, and where that expectation comes from]
Actual:      [what does happen]

Occurrences: Every other place the same pattern appears. A defect found once is
             usually a habit. An empty list here should be surprising.

Recommended fix:
             The approach, the files it touches, and why this approach over the
             alternatives. Precise enough to act on without re-deriving the
             analysis - but not applied.

Acceptance:  How the developer will know it is actually fixed. "Fixed when a
             test asserts exactly one credit after 30 parallel redemptions"
             beats "add a constraint".

Fix effort:  S | M | L
Fix risk:    low | medium | high      (risk of the change, not of the bug)
```

## Worked example

```
ID:          F-003
Title:       Discount code can be redeemed repeatedly under concurrent requests
Severity:    critical
Category:    business-logic
Status:      reproduced
Perspective: attacker
Location:    src/billing/redeem.py:88-94
Rule:        R-01 (stated - docs/campaigns.md:14)

Impact:      A single-use discount can be redeemed as many times as requests
             land in parallel. On a $20,000 offer this is direct revenue loss
             proportional to the attacker's concurrency, and it needs no
             special access - any customer holding a valid code can do it.

Preconditions: An authenticated customer with one unredeemed code. No elevated
             access, no insider knowledge.

Root cause:  redeem() checks `already_redeemed()` and then writes the credit as
             two separate statements with no transaction and no unique
             constraint behind them. Between the check and the write, every
             concurrent request sees the same "not yet redeemed" state. The
             database has no constraint that would catch it either, so the
             application-level check is the only guard, and it is not atomic.

Evidence:    Reproduced locally against a seeded database.

Reproduction:
             $ python repro/f003_parallel_redeem.py --n 30
             issued: 30 requests for code SAVE20 (customer 118)
             succeeded: 30/30
             credits_applied: 30
             expected: 1

Expected:    Exactly one credit per customer per campaign (R-01)
Actual:      One credit per successful concurrent request

Occurrences: src/billing/promo.py:44   (same check-then-act, same table)
             src/billing/referral.py:71 (same shape, referral bonus)

Recommended fix:
             Add a unique constraint on (customer_id, campaign_id) in the
             redemptions table, and wrap the check and the write in one
             transaction using SELECT ... FOR UPDATE. Let the constraint be the
             arbiter rather than the application check - it holds under
             concurrency and survives future refactoring, which an `if` does
             not. Apply the same change at all three call sites. For the HTTP
             layer, an idempotency key would also collapse accidental retries,
             but the constraint is what closes this finding.

Acceptance:  A test issuing 30 parallel redemptions asserts exactly one row in
             redemptions and one credit on the account, and passes on repeated
             runs (20+) rather than once. Note that a first patch that only
             widens the check will still fail this test - the published Stripe
             case needed a second iteration for exactly that reason.

Fix effort:  S
Fix risk:    medium   (needs a migration; existing duplicate rows must be
                       reconciled before the unique constraint will apply)
```
