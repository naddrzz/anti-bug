# Code Review Report - [Project]

Structure for the review document. Sections marked *[generated]* come from
`python scripts/ledger.py report`; the rest is written around them. It must
stand alone for someone who never saw the session, so resolve every "[...]" and
delete what does not apply rather than leaving a heading empty.

Write it to the review workspace, not into the repository.

---

## 1. Verdict

*Lead with this. A review that ends without a recommendation has handed the
decision back unmade.*

**Ready | Ready with conditions | Not ready**

- If *ready with conditions*: name the conditions, each tied to a finding ID.
- Top 3 risks, one sentence each, naming the impact rather than the code smell.
- Counts: findings by severity; how many reproduced, traced, unverified.

## 2. Scope and method

What the reader needs in order to trust the rest:

- What was reviewed (paths, modules, commit SHA) and what was deliberately excluded
- How deeply: which passes ran, and **which perspectives were used** - an unread
  lens is a class of defect nobody looked for
- What was executed versus read: build, tests, linters, scanners - and anything
  that could not run, with the reason
- Time spent or bounded, if that shaped coverage
- Review mode: read-only, in place or on a copy

## 3. Not assessed *[generated]*

The boundary of this review, stated plainly. "No section" and "nothing was
skipped" read the same and mean different things.

## 4. Project context

Condensed Context Summary: purpose and users, stack and versions, architecture
and main data flow, integrations, auth model, and the blast-radius ranking that
drove the sweep order. Include the assumptions made where information was
missing - the next reader needs to know which conclusions rest on them.

## 5. Business rules register *[generated]*

Flag every rule marked `inferred` explicitly: derived from the code rather than
stated by the business, so any finding resting on one is a question for a
product owner, not a settled defect.

## 6. Environment and tooling *[generated]*

Commands run and their real output, including pre-existing failures. A suite
that was already red is itself a finding about the project's state.

## 7. Findings *[generated]*

Ordered by severity, then by fix effort - the top of the table is what to do
first.

## 8. Detailed findings *[generated]*

Each with impact, root cause, evidence, reproduction, other occurrences,
recommended fix, acceptance criteria, effort and risk.

## 9. Questions *[generated]*

Unproven items and anything resting on an inferred rule, phrased as questions
for whoever knows the intent. Keeping these separate from findings is what
protects the findings table's credibility.

## 10. Observations *[generated]*

True but not defects: dead code, inconsistencies, upgrade opportunities.

## 11. Integrity *[generated - paste the check output]*

```
[output of: python scripts/integrity.py check --repo <path>]
```

A reviewer's claim to have changed nothing is exactly the kind of unverifiable
assertion this review refuses to accept from anyone else, so it is proven here
rather than asserted. If the check is not clean, every entry needs an
explanation in this section.

## 12. Prioritized action list

The reader's next move, in order. Severity alone is half a decision; this table
is the other half.

| # | Finding | Action | Effort | Risk | Why now |
|---|---|---|---|---|---|
| 1 | F-003 | | S | medium | |
| 2 | | | | | |

Mark which items need a decision from someone other than the engineer picking
this up, and which need verification in staging before they can be called done.

## 13. If this codebase is to be repaired

One short paragraph on sequencing: what to fix first, what needs a decision
before anyone starts, and what should be re-reviewed after the fixes land.
