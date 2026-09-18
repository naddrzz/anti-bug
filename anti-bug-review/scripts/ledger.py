#!/usr/bin/env python3
"""Review ledger for the anti-bug-review skill.

Holds the business rules the code is judged against, the findings with their
evidence and recommendations, the open questions, and what could not be
assessed. Findings live on disk rather than in the conversation because long
contexts degrade in the middle and a sweep overflows any window.

The workspace is OUTSIDE the reviewed repository - a read-only review that
writes its own notes into the tree it is measuring has already broken its
contract. Default: <repo>/../<repo-name>-review, overridable with --out or
$ANTI_BUG_REVIEW_OUT.

Usage
  python ledger.py init --repo <path> [--out <workspace>]
  python ledger.py rule --area checkout --text "..." --source "docs/x.md:14" --confidence stated
  python ledger.py env --command "pytest -q" --output "142 passed, 3 failed" --status fail
  python ledger.py add --severity critical --category business-logic \
      --title "..." --location "src/a.py:88-94" --status reproduced [--rule R-01] \
      [--perspective attacker] --repro "..." --evidence "..." \
      --recommendation "..." [--effort S] [--fix-risk medium] [--occurrences "b.py:12"]
  python ledger.py question --about "src/auth.py:40" --text "Intended, or an oversight?"
  python ledger.py note --text "Dead module src/legacy/ - no callers" [--about src/legacy/]
  python ledger.py gap --area "payment webhooks" --reason "no sandbox credentials"
  python ledger.py list / stats / report
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SEVERITIES = ["critical", "high", "medium", "low"]
# A review has no fix step, so status records how strongly the finding was
# established - not what was done about it.
STATUSES = ["reproduced", "traced", "unverified", "withdrawn"]
CATEGORIES = ["business-logic", "error-handling", "security", "correctness",
              "concurrency", "data-integrity", "performance", "config",
              "test-quality", "other"]
CONFIDENCE = ["stated", "inferred", "unknown"]
EFFORT = ["S", "M", "L"]
RISK = ["low", "medium", "high"]
# Perspective-based reading: a reviewer with a named viewpoint finds more than
# one reading generally, and distinct viewpoints overlap less.
PERSPECTIVES = ["attacker", "accountant", "operator", "hostile-user",
                "dba", "maintainer", "new-hire", "general"]

STATE_FILE = "review.json"


def _norm_id(raw: str) -> str:
    """R-1, R-01, R-001 and r-1 all name the same item."""
    raw = (raw or "").strip().upper()
    m = re.match(r"^([A-Z]+)-?(\d+)$", raw)
    return f"{m.group(1)}-{int(m.group(2)):03d}" if m else raw


def workspace_for(repo: Path, out: str | None) -> Path:
    if out:
        return Path(out).resolve()
    env = os.environ.get("ANTI_BUG_REVIEW_OUT")
    if env:
        return Path(env).resolve()
    return (repo.parent / f"{repo.name}-review").resolve()


def find_state(out: str | None) -> Path:
    """Locate review.json: explicit --out, env var, or search upward."""
    if out:
        return Path(out).resolve() / STATE_FILE
    env = os.environ.get("ANTI_BUG_REVIEW_OUT")
    if env:
        return Path(env).resolve() / STATE_FILE
    cur = Path.cwd().resolve()
    for d in [cur, *cur.parents]:
        if (d / STATE_FILE).exists():
            return d / STATE_FILE
        sibling = d.parent / f"{d.name}-review" / STATE_FILE
        if sibling.exists():
            return sibling
    return cur / STATE_FILE


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(a) -> tuple[dict, Path]:
    p = find_state(getattr(a, "out", None))
    if not p.exists():
        sys.exit(f"No review ledger at {p}. Run: ledger.py init --repo <path>")
    data = json.loads(p.read_text(encoding="utf-8"))
    for k in ("rules", "env", "findings", "questions", "notes", "gaps"):
        data.setdefault(k, [])
    for f in data["findings"]:
        f["status"] = effective_status(data, f)
    return data, p


def save(data: dict, p: Path) -> None:
    data["updated"] = now()
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp",
                                dir=p.parent)
    os.close(fd)
    temp = Path(name)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, p)
    finally:
        temp.unlink(missing_ok=True)


def next_id(items: list, prefix: str) -> str:
    nums = [int(i["id"].split("-")[1]) for i in items
            if i.get("id", "").startswith(prefix + "-")]
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def get_rule(data: dict, rid: str):
    rid = _norm_id(rid)
    for r in data["rules"]:
        if _norm_id(r["id"]) == rid:
            return r
    return None


def md(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


# ---------------------------------------------------------------- commands

def cmd_init(a):
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        sys.exit(f"Not a directory: {repo}")
    ws = workspace_for(repo, a.out)
    try:
        ws.relative_to(repo)
        sys.exit(f"Refusing to put the workspace inside the repository ({ws}). "
                 f"A read-only review must not write into the tree it reviews. "
                 f"Pass --out with a path outside {repo}.")
    except ValueError:
        pass
    ws.mkdir(parents=True, exist_ok=True)
    p = ws / STATE_FILE
    if p.exists() and not a.force:
        d = json.loads(p.read_text(encoding="utf-8"))
        print(f"Review ledger already exists at {p} "
              f"({len(d.get('findings', []))} findings). Use --force to reset.")
        return
    save({"schema": 1, "repo": str(repo), "workspace": str(ws),
          "created": now(), "rules": [], "env": [], "findings": [],
          "questions": [], "notes": [], "gaps": []}, p)
    print(f"Workspace: {ws}")
    print(f"Ledger:    {p}")
    print("The repository itself stays untouched. Next:")
    print(f"  python integrity.py snapshot --repo {repo} --out {ws}")
    print("  ledger.py rule ...   (business rules, before Pass BL)")


def cmd_rule(a):
    d, p = load(a)
    rid = next_id(d["rules"], "R")
    d["rules"].append({"id": rid, "area": a.area, "text": a.text,
                       "source": a.source or "", "confidence": a.confidence,
                       "created": now()})
    save(d, p)
    if a.confidence != "stated":
        print(f"  note: {rid} is '{a.confidence}'. A finding resting on it "
              f"belongs in Questions, not the findings table - testing code "
              f"against a rule inferred from that code proves only that the "
              f"code agrees with itself.", file=sys.stderr)
    print(rid)


def cmd_env(a):
    d, p = load(a)
    d["env"].append({"command": a.command, "output": a.output,
                     "status": a.status, "recorded": now()})
    save(d, p)
    print(f"Recorded: {a.command} [{a.status}]")


def derive_status(claimed: str, repro: str | None, evidence: str | None):
    """Status follows the evidence that is actually present, not the claim.

    A single ladder rather than a chain of independent downgrades: when two
    rules each branch on the caller's original claim, the weaker downgrade
    overwrites the stronger one and an unproven finding ends up looking
    traced - which is the exact failure this skill exists to catch.
    """
    if claimed == "withdrawn":
        return claimed, None
    if (repro or "").strip():
        return claimed, None
    if (evidence or "").strip():
        if claimed == "reproduced":
            return "traced", ("was downgraded to 'traced': 'reproduced' means "
                              "a command or test with real output, recorded "
                              "in --repro.")
        return claimed, None
    if claimed in ("reproduced", "traced"):
        return "unverified", (f"claims '{claimed}' with no repro and no "
                              f"evidence, so it was recorded as 'unverified'. "
                              f"Rule 1: unproven items go in Questions, not "
                              f"the findings table.")
    return claimed, None


def effective_status(data: dict, finding: dict) -> str:
    status, _ = derive_status(finding["status"], finding.get("repro"), finding.get("evidence"))
    if status not in ("reproduced", "traced"):
        return status
    rid = finding.get("rule")
    rule = get_rule(data, rid) if rid else None
    if ((finding.get("category") == "business-logic" and not rid)
            or (rid and (rule is None or rule["confidence"] != "stated"))):
        return "unverified"
    return status


def cmd_add(a):
    d, p = load(a)
    fid = next_id(d["findings"], "F")
    warn = []
    status, why = derive_status(a.status, a.repro, a.evidence)
    if why:
        warn.append(f"{fid} {why}")
    if not a.recommendation:
        warn.append(f"{fid} has no --recommendation. Rule 4: a review that "
                    f"names a problem without a proposed fix hands the reader "
                    f"half a decision.")
    if a.category == "business-logic" and not a.rule:
        warn.append(f"{fid} is business-logic with no --rule. Without a rule "
                    f"it is an opinion about how the code ought to behave.")
    if a.rule:
        r = get_rule(d, a.rule)
        if r is None:
            warn.append(f"{fid} cites {_norm_id(a.rule)}, which is not in the "
                        f"register. Record it with `ledger.py rule` first.")
        elif r["confidence"] != "stated":
            warn.append(f"{fid} rests on {r['id']} ({r['confidence']}). "
                        f"Confirm the rule with the user, or move this to "
                        f"Questions before the report goes out.")

    d["findings"].append({
        "id": fid, "severity": a.severity, "category": a.category,
        "title": a.title, "location": a.location, "status": status,
        "rule": _norm_id(a.rule) if a.rule else "",
        "perspective": a.perspective or "general",
        "repro": a.repro or "", "evidence": a.evidence or "",
        "root_cause": a.root_cause or "", "impact": a.impact or "",
        "recommendation": a.recommendation or "",
        "effort": a.effort or "", "fix_risk": a.fix_risk or "",
        "occurrences": [s.strip() for s in (a.occurrences or "").split(",") if s.strip()],
        "notes": a.notes or "", "created": now(),
    })
    f = d["findings"][-1]
    f["status"] = effective_status(d, f)
    save(d, p)
    for w in warn:
        print(f"  warning: {w}", file=sys.stderr)
    print(fid)


def cmd_set(a):
    d, p = load(a)
    fid = _norm_id(a.id)
    f = next((x for x in d["findings"] if _norm_id(x["id"]) == fid), None)
    if f is None:
        sys.exit(f"No finding {fid}")
    for field, val in [("severity", a.severity), ("category", a.category),
                       ("status", a.status), ("title", a.title),
                       ("location", a.location), ("repro", a.repro),
                       ("evidence", a.evidence), ("root_cause", a.root_cause),
                       ("impact", a.impact), ("recommendation", a.recommendation),
                       ("effort", a.effort), ("fix_risk", a.fix_risk),
                       ("perspective", a.perspective), ("notes", a.notes)]:
        if val is not None:
            f[field] = val
    if a.rule:
        f["rule"] = _norm_id(a.rule)
    if a.occurrences:
        f["occurrences"] = [s.strip() for s in a.occurrences.split(",") if s.strip()]

    # Re-derive against whatever evidence the finding now carries, so a status
    # cannot be promoted past what is actually recorded.
    status, why = derive_status(f["status"], f.get("repro"), f.get("evidence"))
    if why:
        print(f"  warning: {f['id']} {why}", file=sys.stderr)
    f["status"] = status
    f["status"] = effective_status(d, f)
    f["updated"] = now()
    save(d, p)
    print(f"{f['id']} -> {f['status']}")


def cmd_question(a):
    d, p = load(a)
    qid = next_id(d["questions"], "Q")
    d["questions"].append({"id": qid, "about": a.about or "", "text": a.text,
                           "why": a.why or "", "created": now()})
    save(d, p)
    print(qid)


def cmd_note(a):
    d, p = load(a)
    nid = next_id(d["notes"], "N")
    d["notes"].append({"id": nid, "about": a.about or "", "text": a.text,
                       "created": now()})
    save(d, p)
    print(nid)


def cmd_gap(a):
    d, p = load(a)
    gid = next_id(d["gaps"], "G")
    d["gaps"].append({"id": gid, "area": a.area, "reason": a.reason,
                      "created": now()})
    save(d, p)
    print(gid)


def _sorted(fs):
    order = {"S": 0, "M": 1, "L": 2, "": 3}
    return sorted(fs, key=lambda f: (SEVERITIES.index(f["severity"]),
                                     order.get(f.get("effort", ""), 3), f["id"]))


def cmd_list(a):
    d, _ = load(a)
    fs = d["findings"]
    if a.severity:
        fs = [f for f in fs if f["severity"] == a.severity]
    if a.category:
        fs = [f for f in fs if f["category"] == a.category]
    if a.status:
        fs = [f for f in fs if f["status"] == a.status]
    if not fs:
        print("(no matching findings)")
        return
    for f in _sorted(fs):
        print(f"{f['id']}  {f['severity']:8} {f['status']:11} "
              f"{f['category']:15} {f.get('effort','-') or '-':1}/"
              f"{f.get('fix_risk','-') or '-':6} {f['location']:30} {f['title']}")


def cmd_stats(a):
    d, p = load(a)
    fs = d["findings"]
    print(f"Ledger:    {p}")
    print(f"Repository: {d.get('repo','')}")
    print(f"Rules: {len(d['rules'])} "
          f"({sum(1 for r in d['rules'] if r['confidence'] == 'stated')} stated) | "
          f"Findings: {len(fs)} | Questions: {len(d['questions'])} | "
          f"Observations: {len(d['notes'])} | Not assessed: {len(d['gaps'])}\n")

    for label, key, vals in (("severity", "severity", SEVERITIES),
                             ("status", "status", STATUSES),
                             ("category", "category", CATEGORIES)):
        rows = [(v, sum(1 for f in fs if f[key] == v)) for v in vals]
        rows = [(v, n) for v, n in rows if n]
        if rows:
            print(f"By {label}:")
            for v, n in rows:
                print(f"  {v:16} {n}")
            print()

    used = sorted({f.get("perspective", "general") for f in fs})
    unused = [x for x in PERSPECTIVES if x not in used and x != "general"]
    print(f"Perspectives used: {', '.join(used) or 'none'}")
    if unused:
        print(f"  not yet used: {', '.join(unused)} - each unread lens is a "
              f"class of defect nobody looked for.")
    print()

    problems = False
    unproven = [f for f in fs if f["status"] == "unverified"]
    if unproven:
        problems = True
        print(f"UNVERIFIED IN THE FINDINGS TABLE ({len(unproven)}) - move these "
              f"to Questions or prove them before the report goes out:")
        for f in unproven:
            print(f"  {f['id']} [{f['severity']}] {f['title']}")
        print()

    no_rec = [f for f in fs if not f.get("recommendation")]
    if no_rec:
        problems = True
        print(f"NO RECOMMENDATION ({len(no_rec)}):")
        for f in no_rec:
            print(f"  {f['id']} {f['title']}")
        print()

    no_cost = [f for f in fs if not f.get("effort") or not f.get("fix_risk")]
    if no_cost:
        problems = True
        print(f"NO EFFORT/RISK ({len(no_cost)}) - severity alone is half a "
              f"decision:")
        for f in no_cost:
            print(f"  {f['id']} {f['title']}")
        print()

    bl_no_rule = [f for f in fs
                  if f["category"] == "business-logic" and not f.get("rule")]
    if bl_no_rule:
        problems = True
        print(f"BUSINESS-LOGIC FINDINGS WITH NO RULE ({len(bl_no_rule)}):")
        for f in bl_no_rule:
            print(f"  {f['id']} {f['title']}")
        print()

    if not d["gaps"]:
        print("No 'not assessed' entries recorded. If the review genuinely "
              "covered everything, say so explicitly in the report; if it did "
              "not, record the gaps with `ledger.py gap`.")
    if not problems:
        print("Every finding is proven, has a recommendation, and carries "
              "effort and risk.")


def cmd_report(a):
    d, _ = load(a)
    fs = [f for f in d["findings"] if f["status"] in ("reproduced", "traced")]
    uncertain = [f for f in d["findings"] if f["status"] == "unverified"]
    o = []
    w = o.append

    w("# Code Review Report")
    w("")
    w(f"- Repository: `{d.get('repo','')}`")
    w(f"- Review started: {d.get('created','')}")
    w(f"- Last updated: {d.get('updated','')}")
    w("- Mode: **read-only** - verify repository changes using the Integrity section below")
    w("")

    counts = {s: sum(1 for f in fs if f["severity"] == s) for s in SEVERITIES}
    w("## Verdict")
    w("")
    w("> **Ready / Ready with conditions / Not ready** - replace this line "
      "with the verdict and name the conditions.")
    w("")
    w(f"{len(fs)} findings: "
      + ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s])
      + f". {len(d['questions']) + len(uncertain)} open questions, {len(d['notes'])} observations, "
      + f"{len(d['gaps'])} areas not assessed.")
    w("")
    n_repro = sum(1 for f in fs if f["status"] == "reproduced")
    n_traced = sum(1 for f in fs if f["status"] == "traced")
    proven = n_repro + n_traced
    # This sentence goes into a document a person reads; "1 were reproduced"
    # is the kind of seam that makes a report look machine-dumped.
    w(f"Of the findings, {n_repro} {'was' if n_repro == 1 else 'were'} "
      f"reproduced and {n_traced} traced through the code "
      f"({proven} of {len(fs)} proven).")
    w("")

    if d["gaps"]:
        w("## Not assessed")
        w("")
        w("Stated so the reader knows the boundary of this review.")
        w("")
        w("| ID | Area | Why |")
        w("|---|---|---|")
        for g in d["gaps"]:
            w(f"| {g['id']} | {md(g['area'])} | {md(g['reason'])} |")
        w("")

    if d["rules"]:
        w("## Business rules register")
        w("")
        w("Business-logic findings are judged against these. A rule marked "
          "`inferred` was derived from the code rather than stated by the "
          "business, and needs confirmation before any finding resting on it "
          "is treated as settled.")
        w("")
        w("| ID | Area | Rule | Source | Confidence |")
        w("|---|---|---|---|---|")
        for r in d["rules"]:
            w(f"| {r['id']} | {md(r['area'])} | {md(r['text'])} "
              f"| {md(r.get('source',''))} | {r['confidence']} |")
        w("")

    if d["env"]:
        w("## Environment and tooling")
        w("")
        w("| Command | Status | Output |")
        w("|---|---|---|")
        for e in d["env"]:
            w(f"| `{md(e['command'])}` | {e.get('status','')} "
              f"| {md(e.get('output',''))} |")
        w("")

    w("## Findings")
    w("")
    w("Ordered by severity, then by how cheap the fix is - so the top of this "
      "table is what to do first.")
    w("")
    w("| ID | Sev | Category | Rule | Location | Status | Effort | Risk | Title |")
    w("|---|---|---|---|---|---|---|---|---|")
    for f in _sorted(fs):
        w(f"| {f['id']} | {f['severity']} | {f['category']} "
          f"| {f.get('rule') or '-'} | `{md(f['location'])}` | {f['status']} "
          f"| {f.get('effort') or '-'} | {f.get('fix_risk') or '-'} "
          f"| {md(f['title'])} |")
    w("")

    w("## Detailed findings")
    w("")
    for f in _sorted(fs):
        w(f"### {f['id']} - {f['title']}")
        w("")
        line = (f"**Severity:** {f['severity']} | **Category:** {f['category']} "
                f"| **Status:** {f['status']} | **Perspective:** "
                f"{f.get('perspective','general')}")
        if f.get("effort") or f.get("fix_risk"):
            line += (f" | **Fix effort:** {f.get('effort') or '-'} "
                     f"| **Fix risk:** {f.get('fix_risk') or '-'}")
        if f.get("rule"):
            r = get_rule(d, f["rule"])
            line += f" | **Rule:** {f['rule']}"
            if r:
                line += f" ({r['confidence']})"
        w(line)
        w("")
        w(f"**Location:** `{f['location']}`")
        w("")
        for label, key in (("Impact", "impact"), ("Root cause", "root_cause"),
                           ("Evidence", "evidence"), ("Reproduction", "repro"),
                           ("Recommended fix", "recommendation"),
                           ("Notes", "notes")):
            if f.get(key):
                w(f"**{label}:**")
                w("")
                w(f[key])
                w("")
        if f.get("occurrences"):
            w("**Other occurrences of the same pattern:**")
            w("")
            for s in f["occurrences"]:
                w(f"- `{s}`")
            w("")

    if d["questions"] or uncertain:
        w("## Questions")
        w("")
        w("Unproven, or resting on a rule that was inferred rather than "
          "stated. These need an answer from someone who knows the intent; "
          "they are not defects yet.")
        w("")
        for f in _sorted(uncertain):
            w(f"- **{f['id']}** (`{f['location']}`) - {f['title']}: "
              "can the evidence and any cited business rule be confirmed?")
            for key in ("rule", "repro", "evidence", "notes"):
                if f.get(key):
                    w(f"  - {key}: {md(f[key])}")
        for q in d["questions"]:
            w(f"- **{q['id']}**"
              + (f" (`{q['about']}`)" if q.get("about") else "")
              + f" - {q['text']}"
              + (f" _{q['why']}_" if q.get("why") else ""))
        w("")

    if d["notes"]:
        w("## Observations")
        w("")
        w("True, but not defects - context for whoever works here next.")
        w("")
        for n in d["notes"]:
            w(f"- **{n['id']}**"
              + (f" (`{n['about']}`)" if n.get("about") else "")
              + f" - {n['text']}")
        w("")

    w("## Integrity")
    w("")
    w("```")
    w("Paste the output of `integrity.py check --repo <path>` here.")
    w("```")
    w("")
    w("---")
    w("")
    w("Generated by the anti-bug-review skill. Append scope, method and the "
      "prioritized action list using `assets/report-template.md`.")
    print("\n".join(o))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--out", help="workspace dir (outside the repo)")
        return s

    s = common(sub.add_parser("init"))
    s.add_argument("--repo", required=True)
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = common(sub.add_parser("rule"))
    s.add_argument("--area", required=True); s.add_argument("--text", required=True)
    s.add_argument("--source")
    s.add_argument("--confidence", default="stated", choices=CONFIDENCE)
    s.set_defaults(fn=cmd_rule)

    s = common(sub.add_parser("env"))
    s.add_argument("--command", required=True); s.add_argument("--output", required=True)
    s.add_argument("--status", default="recorded")
    s.set_defaults(fn=cmd_env)

    s = common(sub.add_parser("add"))
    s.add_argument("--severity", required=True, choices=SEVERITIES)
    s.add_argument("--category", required=True, choices=CATEGORIES)
    s.add_argument("--title", required=True); s.add_argument("--location", required=True)
    s.add_argument("--status", default="unverified", choices=STATUSES)
    s.add_argument("--rule"); s.add_argument("--perspective", choices=PERSPECTIVES)
    s.add_argument("--repro"); s.add_argument("--evidence")
    s.add_argument("--root-cause", dest="root_cause"); s.add_argument("--impact")
    s.add_argument("--recommendation")
    s.add_argument("--effort", choices=EFFORT)
    s.add_argument("--fix-risk", dest="fix_risk", choices=RISK)
    s.add_argument("--occurrences"); s.add_argument("--notes")
    s.set_defaults(fn=cmd_add)

    s = common(sub.add_parser("set"))
    s.add_argument("id")
    s.add_argument("--severity", choices=SEVERITIES)
    s.add_argument("--category", choices=CATEGORIES)
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--title"); s.add_argument("--location")
    s.add_argument("--rule"); s.add_argument("--perspective", choices=PERSPECTIVES)
    s.add_argument("--repro"); s.add_argument("--evidence")
    s.add_argument("--root-cause", dest="root_cause"); s.add_argument("--impact")
    s.add_argument("--recommendation")
    s.add_argument("--effort", choices=EFFORT)
    s.add_argument("--fix-risk", dest="fix_risk", choices=RISK)
    s.add_argument("--occurrences"); s.add_argument("--notes")
    s.set_defaults(fn=cmd_set)

    s = common(sub.add_parser("question"))
    s.add_argument("--text", required=True); s.add_argument("--about")
    s.add_argument("--why")
    s.set_defaults(fn=cmd_question)

    s = common(sub.add_parser("note"))
    s.add_argument("--text", required=True); s.add_argument("--about")
    s.set_defaults(fn=cmd_note)

    s = common(sub.add_parser("gap"))
    s.add_argument("--area", required=True); s.add_argument("--reason", required=True)
    s.set_defaults(fn=cmd_gap)

    s = common(sub.add_parser("list"))
    s.add_argument("--severity", choices=SEVERITIES)
    s.add_argument("--category", choices=CATEGORIES)
    s.add_argument("--status", choices=STATUSES)
    s.set_defaults(fn=cmd_list)

    common(sub.add_parser("stats")).set_defaults(fn=cmd_stats)
    common(sub.add_parser("report")).set_defaults(fn=cmd_report)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
