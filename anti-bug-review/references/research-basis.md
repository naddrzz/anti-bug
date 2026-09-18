# Research Basis

Every rule in SKILL.md traces to published empirical work. Read this when a judgement call needs grounding, when deciding how much to trust a signal, or when the user asks why the skill insists on something.

---

## 1. Why the evidence bar exists

**Sadowski et al., "Lessons from Building Static Analysis Tools at Google," CACM 61(4), 2018.**
Google measures *effective* false positives - findings where the developer took no action - rather than technical ones. Their thresholds: compiler-level checks must have effectively zero; code-review-level checks must stay under 10%. Beyond that, developers "develop a strong bias to ignore static analysis, and any false positives or poor reporting give them a justification for inaction." Findings surfaced at compile time were judged real problems 74% of the time versus 21% for findings in already-checked-in code, which is why timing matters as much as accuracy.
https://cacm.acm.org/research/lessons-from-building-static-analysis-tools-at-google/

**Johnson et al., "Why Don't Software Developers Use Static Analysis Tools to Find Bugs?" ICSE 2013.**
Interviews with 20 developers. The blockers: false-positive overload; output that fails to explain "what the problem is, why it is a problem, what they should be doing different"; poor workflow integration; and inability to customize. Notably, all 20 wanted *semi*-automated fixes rather than fully automatic ones, out of concern that automatic fixes introduce new problems - which is the argument for Phase 4's test-first, revert-checked procedure.
https://ieeexplore.ieee.org/document/6606613

**Implication:** report fewer, verified findings; explain impact, not just pattern; never dump raw scanner output as findings.

---

## 2. Why "plausible" is not "correct"

**Qi, Long, Achour, Rinard, "An Analysis of Patch Plausibility and Correctness for Generate-and-Validate Patch Generation Systems," ISSTA 2015.**
Of patches that passed the full test suite: GenProg produced correct patches for 2 of 105 defects (1.9%), RSRepair 2 of 24 (8.3%), AE 3 of 54 (5.6%). Decisively: 104 of 110 plausible GenProg patches, 37 of 44 RSRepair, and 22 of 27 AE patches were semantically equivalent to **deleting functionality**. When the team reran GenProg with a corrected harness and test suites augmented with defect-exposing cases, it produced no patches at all.
https://groups.csail.mit.edu/pac/patchgen/papers/kali-issta2015.pdf

**Implication:** rule 3 ("never weaken to go green"). The dominant failure mode of automated repair is deleting behavior until the oracle stops complaining. Any fix that removes a branch, widens a catch, or loosens an assertion must be treated as suspect by default.

---

## 3. Why the revert-check, not coverage

> **In a review there is no revert-check** - no fix exists to revert. Reproduction carries the whole evidential load instead, which is why the evidence bar in this skill is stricter than in a repair run: a wrong finding here reaches a human unfiltered. The study below still matters as the reason a passing suite is not evidence of correctness.

**Just, Jalali, Inozemtseva, Ernst, Holmes, Fraser, "Are Mutants a Valid Substitute for Real Faults in Software Testing?" FSE 2014.**
Mutation score correlates with real fault detection significantly better than statement coverage does. 73% of real faults are coupled to common mutation operators; of the uncoupled remainder, ~10% need stronger operators and ~17% are outside mutation's reach entirely (algorithmic rewrites, code deletion).
https://homes.cs.washington.edu/~mernst/pubs/mutation-effectiveness-fse2014.pdf

**Implication:** the cheapest sound check that a test actually covers a fix is a single targeted mutation - revert the fix and confirm the test fails. Coverage percentage answers a different, weaker question.

---

## 4. Why error handling comes first

**Yuan et al., "Simple Testing Can Prevent Most Critical Failures," OSDI 2014.**
198 randomly sampled real-world failures across Cassandra, HBase, HDFS, MapReduce, and Redis:
- **92%** of catastrophic failures resulted from incorrect handling of **non-fatal errors that were already explicitly signaled** in the software.
- **35%** came from three trivial patterns: empty or log-only handlers (25%), over-broad catches that abort the cluster (8%), handlers containing TODO/FIXME (2%).
- **98%** of failures were reproducible on three nodes or fewer; **84%** on two.
- Their checker (Aspirator), encoding just those three rules, found 500 new bugs and bad practices in nine systems; 143 were confirmed or fixed by developers.
https://www.usenix.org/system/files/conference/osdi14/osdi14-paper-yuan.pdf

**Implication:** Pass A leads the sweep, and its three signature greps are the first thing to run. Also: small reproductions are usually sufficient - do not assume a bug needs production scale to demonstrate.

---

## 5. Why concurrency hunting looks for pairs

**Lu, Park, Seo, Zhou, "Learning from Mistakes: A Comprehensive Study on Real World Concurrency Bug Characteristics," ASPLOS 2008.**
105 real concurrency bugs from MySQL, Apache, Mozilla, OpenOffice:
- 69% of non-deadlock bugs are **atomicity violations**, 32% **order violations**.
- **96%** manifest with interference between only **two threads**.
- **66%** of non-deadlock bugs involve a **single variable**; 97% of deadlocks involve at most two resources.
- **92%** reliably manifest if a partial order among **no more than four memory accesses** is enforced.
https://www.cs.columbia.edu/~junfeng/09fa-e6998/papers/concurrency-bugs.pdf

**Implication:** Pass D targets check-then-act and read-modify-write on single shared variables between two actors, which covers the large majority, rather than attempting general interleaving analysis.

---

## 6. Why flaky tests get triaged before code gets blamed

**Luo, Hariri, Eloussi, Marinov, "An Empirical Analysis of Flaky Tests," FSE 2014.**
201 commits fixing flaky tests across 51 Apache projects; 161 classified: async wait **45%**, concurrency **20%**, test-order dependency **12%**, resource leak 7%, network 6%, time 3%, I/O 2%, randomness 2%, floating point 2%, unordered collections 1%. **78% of flaky tests were flaky the first time they were written.** Fixes: async wait resolved by waitFor in 57% of cases (sleep increases in 27%, which mostly only reduce flakiness); order dependency fixed by setUp/tearDown cleanup in 74%.
https://mir.cs.illinois.edu/lamyaa/publications/fse14.pdf

**Implication:** an intermittent failure is more likely a defective test than a defective product - but 20% of the time it is a real race, so classify rather than retry.

---

## 7. Why hotspots guide but do not bound the sweep

**Walkinshaw & Minku, "Are 20% of Files Responsible for 80% of Defects?" ESEM 2018.**
Counting each file touched in a fix, the top 20% of files are involved in ~80% of fixes (mean 80.53%, median 78.49%). But counting *distinct bugs*, the median proportion of files needed to cover 80% of bugs is **32%** (range 20-47%), only **66%** of projects follow a power law, and for multi-file fixes fewer than half of the co-edited files are in the top 20%. Frequently-fixed files may simply be highly connected rather than defective.
https://minkull.github.io/publications/WalkinshawESEM2018.pdf

**Implication:** start at hotspots, then widen. A sweep that only reads the top 20% will miss the file where the actual defect lives while fixing the file that merely had to change around it.

---

## 8. Why Phase 0 is not optional

**Bacchelli & Bird, "Expectations, Outcomes, and Challenges of Modern Code Review," ICSE 2013.**
44% of developers and managers rank finding defects as the top motivation for review, but of 570 actual review comments only **14%** concerned defects, versus **29%** code improvements - and the defects found were mostly "uncomplicated logical errors." The identified bottleneck is **understanding**: finding defects requires the most complete understanding of any review outcome, and reviewers in unfamiliar code produce measurably shallower feedback. One participant: "With code I am familiar with I have more to say... What I have to say is deeper."
https://sback.it/publications/icse2013.pdf

**Implication:** Phase 0 exists because depth of finding is a direct function of context. Skipping it produces the 29% - style opinions - instead of the 14% that matters.

---

## 9. Why review happens in small batches

**Cisco / SmartBear code review case study (Cohen et al.), ~2,500 reviews, 3.2M LOC.**
Defect detection density falls sharply as review size and speed rise; the widely-cited operating points are ≤200-400 LOC per review session, an inspection rate under ~300-500 LOC/hour, and sessions under 60-90 minutes. Author preparation - annotating the change before review - correlates with markedly fewer defects found, likely because the act of explaining surfaces them first.
https://smartbear.com/learn/code-review/best-practices-for-peer-code-review/

**Implication:** Phase 2 batching, and writing each finding to the ledger immediately rather than accumulating.

---

## 10. Why findings live on disk

**Liu et al., "Lost in the Middle: How Language Models Use Long Contexts," TACL 12, 2024.**
Model performance is highest when relevant information sits at the beginning or end of the input context and degrades substantially when it sits in the middle - a U-shaped curve that persists in models explicitly built for long contexts.
https://aclanthology.org/2024.tacl-1.9/

**Implication:** the ledger. A repository sweep generates more material than any window holds well, and the middle of it is exactly where a Critical finding would be forgotten.

---

## 11. Why localization gets its own discipline

**Xia, Deng, Dunn, Zhang, "Demystifying LLM-Based Software Engineering Agents," FSE 2025 (Agentless).**
On SWE-bench Verified, file-level localization accuracy of 69.7% coexists with a 32% issue-resolution rate - correct localization is necessary but far from sufficient, and each subsequent narrowing step loses ground truth (81.3% file-level down to 59.33% after edit-level localization). Reproduction tests for patch selection raised results from 81 to 96 fixes; the same pipeline could theoretically reach 42% with better patch ranking alone. Identified agent failure modes: sub-optimal exploration over long tool-use chains, and limited ability to self-reflect and filter misleading information.
https://lingming.cs.illinois.edu/publications/fse2025.pdf

**Implication:** hierarchical localization (file → function → line), and reproduction-test-first in Phase 4 - the single highest-leverage step for distinguishing a real fix from a plausible one.

---

## 12. Why every claim needs an artifact

**"What Breaks When LLMs Code? Characterizing Operational Safety Failures of Agentic Code Assistants," 2026.**
547 real incidents, 33 risk types across 7 dimensions. Constraint and instruction violation **40.4%**; destructive operations **24.5%** (including an agent deleting 3,421 lines of working code while adding 555 non-functional ones); authorization bypass 18.3%. Previously undocumented classes: **deception 15.7%** (falsely claiming actions were completed), **fabrication 9.7%** (forging terminal logs or commit histories), **false assurance 9.1%** (presenting unvalidated code as verified). Nearly 60% of incidents caused High or Critical damage. Recommended controls include read-before-write verification, task-scoped permissions, **verifiable status reporting tied to observable artifacts**, and safe-halt mechanisms that reward escalating uncertainty over simulating success.
https://arxiv.org/html/2605.30777v1

**Implication:** rule 4, and the *Needs decision* state. Reporting "I could not run this" is an explicitly designed-for outcome, not a failure.

---

## 13. Why AI-written code gets the security pass

**Pearce, Ahmad, Tan, Dolan-Gavitt, Karri, "Asleep at the Keyboard? Assessing the Security of GitHub Copilot's Code Contributions," IEEE S&P 2022.**
89 scenarios across 18 CWEs, 1,689 generated programs; **~40% vulnerable** overall (477 of 1,084 in the primary analysis, 44%). Worst classes: path traversal (60% vulnerable, all top-ranked suggestions vulnerable), OS command injection, null dereference (all three scenarios vulnerable at top rank), and insufficiently protected credentials (MD5 suggested for password hashing).
https://arxiv.org/abs/2108.09293

**Package hallucination / "slopsquatting."** Models invent plausible package names at measurable rates; attackers register them. Any new dependency must be verified to exist on the real registry before it is added.
https://socket.dev/blog/slopsquatting-how-ai-hallucinations-are-fueling-a-new-class-of-supply-chain-attacks

---

## 14. Why business logic is its own pass

**MITRE, CWE-840: Business Logic Errors (category).**
Defined by the fact that judging these requires "domain-specific knowledge or 'business rules'" and that they "do not produce clear errors or undefined behavior at the code level," which is what makes them invisible to code analysis. Members include CWE-283 Unverified Ownership, CWE-639 Authorization Bypass Through User-Controlled Key, CWE-708 Incorrect Ownership Assignment, CWE-770 Allocation of Resources Without Limits, CWE-826 Premature Release of Resource, CWE-837 Improper Enforcement of a Single Unique Action, CWE-841 Improper Enforcement of Behavioral Workflow.
https://cwe.mitre.org/data/definitions/840.html

**OWASP Web Security Testing Guide, 4.10 Business Logic Testing.**
Independently reaches the same conclusion from the testing side: "Automated tools find it hard to understand context, hence it's up to a person to perform these kinds of tests," and business logic testing "remains a manual art relying on the skills of the tester." Tests WSTG-BUSL-01 through 10 cover data validation, request forgery, integrity checks, process timing, use-count limits, workflow circumvention, application misuse defenses, unexpected and malicious file upload, and payment functionality. Its worked examples are price manipulation on the summary page, resource locking while prices move, and loyalty points accrued then cancelled.
https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/10-Business_Logic_Testing/README

**PortSwigger Web Security Academy, Business logic vulnerabilities.**
Third independent source, with the most useful framing: these arise when developers "fail to anticipate unusual application states" and therefore fail to handle them safely, and they "won't be exposed by normal use of the application." Prevention guidance centers on domain understanding, avoiding implicit assumptions, and documenting assumptions and component side effects.
https://portswigger.net/web-security/logic-flaws

**Implication:** Pass BL exists, runs first, and requires the Business Rules Register - because the only oracle for this class is a written rule, and all three sources agree no tool supplies one.

---

## 15. A documented business-logic incident

**HackerOne / Stripe, unlimited discount redemption (disclosed report).**
A $20,000 fee discount was redeemed roughly 30 times by issuing parallel requests with Turbo Intruder, producing about $600,000 of fee-free transaction volume from a single offer. The detail that matters for Phase 5: **the first patch was incomplete** - a race condition still permitted multiple redemptions, and a second iteration was needed. An obvious fix to a concurrency bug frequently does not close it, which is why the verification step demands repeated parallel runs asserting final persisted state.
https://www.hackerone.com/blog/how-business-logic-vulnerability-led-unlimited-discount-redemption

**Stripe API documentation, idempotent requests** (vendor engineering documentation, used as the prevention pattern).
The server stores the status code and body of the first request for a given idempotency key and returns the same result for repeats, including errors; keys are client-generated, high-entropy, and compared against the original parameters to catch accidental reuse. This is the standard answer to CWE-837 for anything retried over a network.
https://docs.stripe.com/api/idempotent_requests

---

## 16. Testing methods that actually work on logic bugs

**Goldstein et al. / Coblenz et al., "An Empirical Evaluation of Property-Based Testing in Python," OOPSLA 2025 (PACMPL).**
Per test, property-based tests caught mutations roughly **50x** more often than unit tests; controlling for coverage, the odds ratio was 51.91. Exception-raising properties were 113x more likely to catch a mutation, inclusion properties 36.4x, type-checking properties 19.4x - and those three categories were only 10% of the corpus. **55%** of caught mutations were caught by a single input and 86% within Hypothesis's default 100, so the effect comes from thinking in properties rather than from input volume.
https://dl.acm.org/doi/10.1145/3764068

**Segura, Fraser, Sanchez, Ruiz-Cortes, "A Survey on Metamorphic Testing," IEEE TSE, 2016.**
Documents **295 distinct real faults** found across 36 tools in 23 real-world programs using metamorphic relations, with results in compilers (GCC, LLVM), search engines and commercial systems. It is the standard answer to the oracle problem - which is precisely the problem business logic presents, since the correct output is defined by a rule rather than computable from the input.
https://eprints.whiterose.ac.uk/id/eprint/110335/1/segura16-tse.pdf

**Agentic property-based testing across the Python ecosystem, 2025 (arXiv preprint - NOT peer-reviewed).**
An agent built on Claude Code inferred properties from code and documentation, wrote Hypothesis tests, and ran them across 100 packages / 933 modules: 56% of its 984 reports were valid bugs, rising to 86% among top-scored reports; five were reported upstream (including NumPy and Hugging Face tokenizers) with three patches merged. Useful in both directions - it shows the approach works, and its validity rate shows that even a good agentic pipeline produces a substantial minority of invalid reports, which is the argument for the evidence bar.
https://arxiv.org/html/2510.09907v1

---

## 17. Business-logic risk specific to AI-written code

**Tambon et al., "Bugs in Large Language Models Generated Code: An Empirical Study," Empirical Software Engineering, 2025.**
333 bugs across CodeGen, PanGu-Coder and Codex, with a taxonomy validated by a survey of 50+ practitioners. The categories are dominated by intent failures rather than syntax: *Misinterpretations*, *Prompt-biased code*, *Missing Corner Case*, *Hallucinated Object*, *Non-Prompted Consideration*, alongside *Silly Mistake*, *Wrong Input Type*, *Wrong Attribute*, *Incomplete Generation* and *Syntax Error*. Every intent-side category produces code that runs and is wrong - the definition of a business-logic bug.
https://link.springer.com/article/10.1007/s10664-025-10614-4

**Implication:** AI-authored code gets Pass BL first, checked against the register. Code generated from a prompt satisfies the prompt; the business rule is usually in neither the prompt nor the code.

---

## 18. Standards for verification and root cause

**NIST SP 800-218, Secure Software Development Framework (SSDF) v1.1.**
Practices used directly here: **PW.7** "Review and/or Analyze Human-Readable Code to Identify Vulnerabilities and Verify Compliance with Security Requirements"; **PW.8** "Test Executable Code to Identify Vulnerabilities and Verify Compliance with Security Requirements"; **PW.9** secure settings by default; and **RV.3** "Analyze Vulnerabilities to Identify Their Root Causes," whose stated purpose is to "help reduce the frequency of vulnerabilities in the future." RV.3 is the standards-level statement of rule 2: root cause plus every sibling, not the reported line.
https://csrc.nist.gov/projects/ssdf

---

## 19. Agent-specific practice

**Anthropic, "Building verification loops in Claude Code with skills."**
A verification loop is the agent checking its own work against deterministic signals - type checkers, tests, custom validations - and fixing before proceeding, rather than deferring to human review. Guidance: encode the checks in the skill itself, write them "the way you'd hand it to a new teammate on day one," and progress from standalone checks to embedded, chained, and PR-integrated ones. This is the vendor-documented pattern that Phases 4 and 5 implement.
https://claude.com/blog/building-verification-loops-in-claude-code-with-skills

**OWASP GenAI Security Project, Top 10 for Agentic Applications (2026).**
A peer-reviewed framework for risks in autonomous agent systems; the named risks confirmed in the announcement include **Agent Behavior Hijacking**, **Tool Misuse and Exploitation**, and **Identity and Privilege Abuse**, with mitigations centered on real-time intent controls, tool governance, and preventing cascading failures across autonomous systems. The full list was not verifiable from the public announcement page at the time of writing, so only these three are cited.
https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/

**Zheng et al., "Dream-RSI: Recursive Self-Improvement through Evolving Worlds," Google / Google DeepMind, 2026 (preprint - NOT peer-reviewed).**
Source of the ledger's attempt-history design and the retry discipline. Relevant findings and operational rules:
- Completed discovery history works as a **replay simulator** rather than as static context: alternative strategies can be evaluated by reading stored outcomes instead of re-running the expensive agent (pp. 2, 4, 12).
- **Explicit directional guidance consistently underperformed** its unguided counterpart under equal budgets; imposing strong semantic priors "over-constrains the search space and impedes diverse exploration" (p. 11, sec 5.1). This is why the skill explains reasoning rather than issuing long directive lists.
- Exploration effort adapts: compute is conserved while results improve and increased when progress plateaus (p. 11, sec 5.2).
- Operational prompt rules adopted here: read every prior attempt in full before proposing a new one, and **"trust the measured result over what the proposal claims about itself"**; for a failure, distinguish "a flawed core idea" from "a good idea let down by a bug," and retry the latter "only once you've actually located the bug in the code (not just guessed from the proposal), and only with a specific fix in hand"; resist another small tweak when attempts cluster with flattening returns; "don't claim it compiles, is correct, or beats SOTA until it's actually evaluated"; and "never execute pkill, kill, killall, or terminate unrelated processes" (pp. 18-19).
- Classify a failure before closing a line of work - hard-unrecoverable, repairable implementation failure, weak-but-underexplored, or repeatedly unpromising - and "do not infer algorithmic failure from one such error"; a later success reopens what an earlier failure closed (p. 20).
- Policy selection is bounded so the next policy is never worse than the current on the fixed history (p. 6) - the formal shape of "accept only if no worse than baseline on every recorded check."
https://dream-rsi.com | https://github.com/zhengkid/Dream-RSI

---

## 20. Why each pass gets a named perspective

**Basili et al., "The Empirical Investigation of Perspective-Based Reading," Empirical Software Engineering, 1996.**
Reviewers assigned a specific viewpoint - designer, tester, user - outperformed reviewers using their usual general technique. On generic documents PBR teams achieved significantly better coverage, a **30% improvement**, with individual detection rates of 32.14% versus 24.64%; NASA documents showed a statistically significant team improvement (p=0.0390). The mechanism: "the union of the perspectives provides extensive coverage of the document, yet each reader is responsible for a narrowly focused view," which yields deeper analysis per reader and less overlap between them.
https://www.cs.umd.edu/~mvz/handouts/emp_pbr.pdf

A replication focused on individual reviewer effectiveness appeared in Empirical Software Engineering (2006), and the technique's lineage continues through checklist-based versus ad-hoc reading comparisons; the consistent direction is that a structured, focused reading beats an unstructured one.
https://link.springer.com/article/10.1007/s10664-006-5967-6

**Implication:** Phase 2 assigns a perspective per pass and records it on each finding, and `ledger.py stats` reports which lenses were never used - an unread perspective is a class of defect nobody looked for, and saying so is more honest than an unqualified "reviewed".

---

## 21. Standards used as worklists

- **CWE Top 25 (2025)**, MITRE - https://cwe.mitre.org/top25/archive/2025/2025_cwe_top25.html
- **OWASP Top 10 (2021)** - https://owasp.org/Top10/2021/
- **Zeller & Hildebrandt, "Simplifying and Isolating Failure-Inducing Input," TSE 28(2), 2002** - delta debugging; the systematic way to shrink a reproduction to its minimal failing form. https://www.st.cs.uni-saarland.de/publications/files/zeller-tse-2002.pdf
