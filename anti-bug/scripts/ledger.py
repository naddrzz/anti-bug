#!/usr/bin/env python3
"""Findings ledger for the anti-bug skill.

Holds three things on disk so a repository-wide sweep stays complete and
resumable: the business rules the code is judged against, the findings, and
the history of fix attempts with their measured outcomes. Findings live here
rather than in the conversation because long contexts degrade in the middle,
and a sweep overflows any window.

Stores .anti-bug/findings.json at the repo root.

Usage
  python ledger.py init
  python ledger.py rule --area checkout --text "Code redeemable once per customer" \
      --source "docs/campaigns.md:14" --confidence stated
  python ledger.py rules
  python ledger.py baseline --command "npm test" --output "142 passed, 3 failed" --status fail
  python ledger.py add --severity critical --category business-logic \
      --title "..." --location "src/a.py:88-94" --status confirmed [--rule R-01] \
      [--repro "..."] [--evidence "..."] [--root-cause "..."] [--siblings "b.py:12,c.py:40"]
  python ledger.py attempt F-003 --mechanism "..." --outcome fail \
      --measured "test still red: 2 of 30 succeed" --failure-class repairable [--note "..."]
  python ledger.py set F-003 --status fixed --fix-commit abc1234 --test "tests/x.py::y"
  python ledger.py list [--status confirmed] [--severity critical] [--category business-logic]
  python ledger.py stats
  python ledger.py report [> docs/anti-bug-report.md]
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
STATUSES = ["confirmed", "suspected", "false-positive", "needs-decision",
            "fixed", "deferred", "unverified"]
CATEGORIES = ["business-logic", "error-handling", "security", "correctness",
              "concurrency", "data-integrity", "performance", "config",
              "test-quality", "other"]
CONFIDENCE = ["stated", "inferred", "unknown"]
OUTCOMES = ["pass", "fail", "partial"]
# Why a fix attempt failed. The classification decides whether to retry the
# same mechanism (only 'repairable' or 'environmental' may be retried, and
# 'repairable' only once the actual defect is located in the code).
FAILURE_CLASSES = ["flawed-mechanism", "repairable", "environmental",
                   "needs-decision"]


def repo_root() -> Path:
    env = os.environ.get("ANTI_BUG_ROOT")
    if env:
        return Path(env).resolve()
    cur = Path.cwd().resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / ".git").exists() or (candidate / ".anti-bug").exists():
            return candidate
    return cur


def ledger_path() -> Path:
    return repo_root() / ".anti-bug" / "findings.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    p = ledger_path()
    if not p.exists():
        sys.exit(f"No ledger at {p}. Run: python ledger.py init")
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    data.setdefault("rules", [])
    data.setdefault("baseline", [])
    data.setdefault("findings", [])
    for f in data["findings"]:
        f["status"] = effective_status(data, f)
    return data


def save(data: dict) -> None:
    p = ledger_path()
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


def find(data: dict, fid: str) -> dict:
    fid = norm_id(fid)
    for f in data["findings"]:
        if norm_id(f["id"]) == fid:
            return f
    sys.exit(f"No finding {fid}")


def norm_id(raw: str) -> str:
    """R-1, R-01, R-001 and r-1 all name the same rule.

    Stored ids are zero-padded to three digits, but people write them the
    short way. Matching on the raw string means a cited rule silently fails
    to resolve, which disables the checks that depend on it - so normalize.
    """
    raw = (raw or "").strip().upper()
    m = re.match(r"^([A-Z]+)-?(\d+)$", raw)
    if not m:
        return raw
    return f"{m.group(1)}-{int(m.group(2)):03d}"


def get_rule(data: dict, rid: str):
    rid = norm_id(rid)
    for r in data["rules"]:
        if norm_id(r["id"]) == rid:
            return r
    return None


def effective_status(data: dict, finding: dict) -> str:
    status = finding["status"]
    if status not in ("confirmed", "fixed"):
        return status
    rid = finding.get("rule")
    rule = get_rule(data, rid) if rid else None
    if ((finding.get("category") == "business-logic" and not rid)
            or (rid and (rule is None or rule["confidence"] != "stated"))):
        return "needs-decision"
    if not any((finding.get(k) or "").strip() for k in ("repro", "evidence")):
        return "suspected"
    return status


# ---------------------------------------------------------------- commands

def cmd_init(a):
    p = ledger_path()
    if p.exists() and not a.force:
        d = load()
        print(f"Ledger already exists at {p} "
              f"({len(d['findings'])} findings, {len(d['rules'])} rules). "
              f"Use --force to reset.")
        return
    save({"schema": 2, "repo": str(repo_root()), "created": now(),
          "rules": [], "baseline": [], "findings": [], "notes": []})
    print(f"Initialized {p}")
    print("Next: record the business rules with `ledger.py rule` before Pass BL.")


def cmd_rule(a):
    d = load()
    rid = next_id(d["rules"], "R")
    d["rules"].append({"id": rid, "area": a.area, "text": a.text,
                       "source": a.source or "", "confidence": a.confidence,
                       "created": now()})
    save(d)
    if a.confidence != "stated":
        print(f"  note: {rid} is '{a.confidence}'. A finding that rests on it "
              f"cannot be 'confirmed' - it is 'needs-decision' until someone "
              f"confirms the rule.", file=sys.stderr)
    print(rid)


def cmd_rules(a):
    d = load()
    if not d["rules"]:
        print("(no business rules recorded - Pass BL needs these first)")
        return
    print(f"{'ID':<6} {'CONF':<9} {'AREA':<16} RULE")
    print("-" * 78)
    for r in d["rules"]:
        print(f"{r['id']:<6} {r['confidence']:<9} {r['area']:<16} {r['text']}")
        if r.get("source"):
            print(f"{'':<6} {'':<9} {'':<16}   source: {r['source']}")


def cmd_baseline(a):
    d = load()
    d["baseline"].append({"command": a.command, "output": a.output,
                          "status": a.status, "recorded": now()})
    save(d)
    print(f"Baseline recorded: {a.command} [{a.status}]")


def cmd_add(a):
    d = load()
    fid = next_id(d["findings"], "F")
    status = a.status
    warn = []

    if a.status == "confirmed" and not (a.repro or a.evidence):
        warn.append(f"{fid} marked confirmed with no repro and no evidence. "
                    f"Rule 1: that makes it 'suspected'.")
    if a.category == "business-logic" and not a.rule:
        warn.append(f"{fid} is business-logic with no --rule. Every BL finding "
                    f"cites a rule; without one it is an opinion about how the "
                    f"code ought to behave.")
    if a.rule:
        r = get_rule(d, a.rule)
        if r is None:
            warn.append(f"{fid} cites {norm_id(a.rule)}, which is not in the "
                        f"register. Record it with `ledger.py rule` first.")
        elif r["confidence"] != "stated" and a.status == "confirmed":
            status = "needs-decision"
            warn.append(f"{fid} rests on {r['id']} ({r['confidence']}), so it "
                        f"was recorded as 'needs-decision' rather than "
                        f"'confirmed'. Confirm the rule with the user first.")

    d["findings"].append({
        "id": fid, "severity": a.severity, "category": a.category,
        "title": a.title, "location": a.location, "status": status,
        "rule": norm_id(a.rule) if a.rule else "", "repro": a.repro or "",
        "evidence": a.evidence or "", "root_cause": a.root_cause or "",
        "siblings": [s.strip() for s in (a.siblings or "").split(",") if s.strip()],
        "impact": a.impact or "", "fix": "", "fix_commit": "",
        "tests": [], "attempts": [], "notes": "", "created": now(),
    })
    f = d["findings"][-1]
    f["status"] = effective_status(d, f)
    save(d)
    for w in warn:
        print(f"  warning: {w}", file=sys.stderr)
    print(fid)


def cmd_attempt(a):
    d = load()
    f = find(d, a.id)
    f.setdefault("attempts", []).append({
        "n": len(f.get("attempts", [])) + 1,
        "mechanism": a.mechanism, "outcome": a.outcome,
        "measured": a.measured, "failure_class": a.failure_class or "",
        "note": a.note or "", "recorded": now(),
    })
    f["updated"] = now()
    save(d)
    n = len(f["attempts"])
    print(f"{f['id']} attempt #{n} recorded [{a.outcome}]")

    if a.outcome == "fail":
        if a.failure_class == "flawed-mechanism":
            print("  -> flawed mechanism: do not retry this approach. "
                  "Change mechanism.", file=sys.stderr)
        elif a.failure_class == "repairable":
            print("  -> repairable: retry only after locating the actual "
                  "defect in the code, not guessing from the symptom, and "
                  "only with a specific fix in hand.", file=sys.stderr)
        elif a.failure_class == "needs-decision":
            print("  -> larger or riskier than planned: stop this item and "
                  "document it. A half-applied fix is worse than none.",
                  file=sys.stderr)
    fails = [x for x in f["attempts"] if x["outcome"] == "fail"]
    if a.outcome == "fail" and len(fails) >= 3:
        print(f"  -> {len(fails)} failed attempts on {f['id']}. If they cluster "
              f"around variations of one idea with flattening returns, that is "
              f"a local optimum: switch to a structurally different angle "
              f"instead of another marginal tweak.", file=sys.stderr)


def cmd_set(a):
    d = load()
    f = find(d, a.id)
    for field, val in [("severity", a.severity), ("category", a.category),
                       ("status", a.status), ("repro", a.repro),
                       ("evidence", a.evidence), ("root_cause", a.root_cause),
                       ("impact", a.impact), ("fix", a.fix),
                       ("fix_commit", a.fix_commit), ("notes", a.notes),
                       ("title", a.title), ("location", a.location)]:
        if val is not None:
            f[field] = val
    if a.rule:
        f["rule"] = norm_id(a.rule)
    if a.siblings:
        f["siblings"] = [s.strip() for s in a.siblings.split(",") if s.strip()]
    if a.test:
        f.setdefault("tests", []).append(a.test)
    if a.status == "fixed" and not f.get("tests"):
        print(f"  warning: {f['id']} marked fixed with no test recorded. "
              f"Rule 3: a fix without a failing-then-passing test is unproven.",
              file=sys.stderr)
    f["status"] = effective_status(d, f)
    f["updated"] = now()
    save(d)
    print(f"{f['id']} -> {f['status']}")


def _filter(d, status=None, severity=None, category=None):
    out = d["findings"]
    if status:
        out = [f for f in out if f["status"] == status]
    if severity:
        out = [f for f in out if f["severity"] == severity]
    if category:
        out = [f for f in out if f["category"] == category]
    return sorted(out, key=lambda f: (SEVERITIES.index(f["severity"]), f["id"]))


def cmd_list(a):
    d = load()
    rows = _filter(d, a.status, a.severity, a.category)
    if not rows:
        print("(no matching findings)")
        return
    for f in rows:
        rule = f.get("rule") or "-"
        print(f"{f['id']}  {f['severity']:8} {f['status']:14} "
              f"{f['category']:15} {rule:6} {f['location']:30} {f['title']}")


def cmd_stats(a):
    d = load()
    fs = d["findings"]
    print(f"Ledger: {ledger_path()}")
    print(f"Business rules: {len(d['rules'])} "
          f"({sum(1 for r in d['rules'] if r['confidence'] == 'stated')} stated, "
          f"{sum(1 for r in d['rules'] if r['confidence'] != 'stated')} inferred/unknown)")
    print(f"Total findings: {len(fs)}\n")

    print("By severity:")
    for s in SEVERITIES:
        n = sum(1 for f in fs if f["severity"] == s)
        if n:
            print(f"  {s:10} {n}")
    print("\nBy category:")
    for c in CATEGORIES:
        n = sum(1 for f in fs if f["category"] == c)
        if n:
            print(f"  {c:16} {n}")
    print("\nBy status:")
    for s in STATUSES:
        n = sum(1 for f in fs if f["status"] == s)
        if n:
            print(f"  {s:16} {n}")

    print()
    problems = False
    open_states = {"confirmed", "suspected", "unverified"}
    still_open = [f for f in fs if f["status"] in open_states]
    if still_open:
        problems = True
        print(f"UNRESOLVED ({len(still_open)}) - every finding needs a final "
              f"status before the report is written:")
        for f in still_open:
            print(f"  {f['id']} [{f['severity']}/{f['status']}] {f['title']}")

    no_test = [f for f in fs if f["status"] == "fixed" and not f.get("tests")]
    if no_test:
        problems = True
        print(f"\nFIXED WITHOUT A TEST ({len(no_test)}) - unproven fixes:")
        for f in no_test:
            print(f"  {f['id']} {f['title']}")

    bl_no_rule = [f for f in fs
                  if f["category"] == "business-logic" and not f.get("rule")]
    if bl_no_rule:
        problems = True
        print(f"\nBUSINESS-LOGIC FINDINGS WITH NO RULE ({len(bl_no_rule)}):")
        for f in bl_no_rule:
            print(f"  {f['id']} {f['title']}")

    if not d["rules"] and any(f["category"] == "business-logic" for f in fs):
        problems = True
        print("\nNo business rules registered, but business-logic findings "
              "exist. Pass BL needs the register first.")

    if not problems:
        print("All findings have a final status, every fix has a test, and "
              "every business-logic finding cites a rule.")


def _md_escape(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def cmd_report(a):
    d = load()
    fs = d["findings"]
    o = []
    w = o.append
    w("# Anti-Bug Report")
    w("")
    w(f"- Repository: `{d.get('repo','')}`")
    w(f"- Sweep started: {d.get('created','')}")
    w(f"- Last updated: {d.get('updated','')}")
    w("")

    counts = {s: sum(1 for f in fs if f["severity"] == s) for s in SEVERITIES}
    fixed = sum(1 for f in fs if f["status"] == "fixed")
    fp = sum(1 for f in fs if f["status"] == "false-positive")
    nd = sum(1 for f in fs if f["status"] == "needs-decision")
    dfr = sum(1 for f in fs if f["status"] == "deferred")
    w("## Executive summary")
    w("")
    w(f"{len(fs)} findings recorded: "
      + ", ".join(f"{counts[s]} {s}" for s in SEVERITIES if counts[s]) + ".")
    w("")
    w(f"Fixed: {fixed} | False positive: {fp} | Needs decision: {nd} | Deferred: {dfr}")
    w("")
    w("> Replace this line with the release-readiness verdict "
      "(Ready / Ready with conditions / Not ready) and the top three risks.")
    w("")

    if d.get("rules"):
        w("## Business rules register")
        w("")
        w("Findings in the business-logic category are judged against these. "
          "A rule marked `inferred` was derived from the code rather than "
          "stated by the business, and needs confirmation before any finding "
          "resting on it is treated as settled.")
        w("")
        w("| ID | Area | Rule | Source | Confidence |")
        w("|---|---|---|---|---|")
        for r in d["rules"]:
            w(f"| {r['id']} | {_md_escape(r['area'])} | {_md_escape(r['text'])} "
              f"| {_md_escape(r.get('source',''))} | {r['confidence']} |")
        w("")

    if d.get("baseline"):
        w("## Baseline")
        w("")
        w("| Command | Status | Output |")
        w("|---|---|---|")
        for b in d["baseline"]:
            w(f"| `{_md_escape(b['command'])}` | {b.get('status','')} "
              f"| {_md_escape(b.get('output',''))} |")
        w("")

    w("## Findings table")
    w("")
    w("| ID | Severity | Category | Rule | Location | Status | Title |")
    w("|---|---|---|---|---|---|---|")
    for f in _filter(d):
        w(f"| {f['id']} | {f['severity']} | {f['category']} "
          f"| {f.get('rule') or '-'} | `{_md_escape(f['location'])}` "
          f"| {f['status']} | {_md_escape(f['title'])} |")
    w("")

    w("## Detailed findings")
    w("")
    for f in _filter(d):
        w(f"### {f['id']} - {f['title']}")
        w("")
        line = (f"**Severity:** {f['severity']} | **Category:** {f['category']} "
                f"| **Status:** {f['status']}")
        if f.get("rule"):
            r = get_rule(d, f["rule"])
            line += f" | **Rule:** {f['rule']}"
            if r:
                line += f" ({r['confidence']})"
        w(line)
        w("")
        w(f"**Location:** `{f['location']}`")
        w("")
        for label, key in [("Impact", "impact"), ("Root cause", "root_cause"),
                           ("Evidence", "evidence"), ("Reproduction", "repro"),
                           ("Fix", "fix"), ("Notes", "notes")]:
            if f.get(key):
                w(f"**{label}:**")
                w("")
                w(f"{f[key]}")
                w("")
        if f.get("siblings"):
            w("**Other occurrences of the same pattern:**")
            w("")
            for s in f["siblings"]:
                w(f"- `{s}`")
            w("")
        if f.get("attempts"):
            w("**Fix attempts:**")
            w("")
            w("| # | Mechanism | Outcome | Measured | Failure class |")
            w("|---|---|---|---|---|")
            for at in f["attempts"]:
                w(f"| {at['n']} | {_md_escape(at['mechanism'])} "
                  f"| {at['outcome']} | {_md_escape(at.get('measured',''))} "
                  f"| {at.get('failure_class','') or '-'} |")
            w("")
        if f.get("tests"):
            w("**Tests:**")
            w("")
            for t in f["tests"]:
                w(f"- `{t}`")
            w("")
        if f.get("fix_commit"):
            w(f"**Commit:** `{f['fix_commit']}`")
            w("")

    not_fixed = [f for f in fs if f["status"] in
                 ("false-positive", "needs-decision", "deferred", "unverified")]
    if not_fixed:
        w("## Not fixed")
        w("")
        w("| ID | Status | Title | Reason / evidence |")
        w("|---|---|---|---|")
        for f in not_fixed:
            reason = f.get("notes") or f.get("evidence") or ""
            w(f"| {f['id']} | {f['status']} | {_md_escape(f['title'])} "
              f"| {_md_escape(reason)} |")
        w("")

    w("---")
    w("")
    w("Generated from `.anti-bug/findings.json` by the anti-bug skill. "
      "Append the narrative sections - smoke tests, baseline-vs-final "
      "comparison, follow-up actions - using `assets/report-template.md`.")
    print("\n".join(o))


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("rule", help="record a business rule")
    s.add_argument("--area", required=True)
    s.add_argument("--text", required=True)
    s.add_argument("--source")
    s.add_argument("--confidence", default="stated", choices=CONFIDENCE)
    s.set_defaults(fn=cmd_rule)

    s = sub.add_parser("rules"); s.set_defaults(fn=cmd_rules)

    s = sub.add_parser("baseline")
    s.add_argument("--command", required=True)
    s.add_argument("--output", required=True)
    s.add_argument("--status", default="recorded")
    s.set_defaults(fn=cmd_baseline)

    s = sub.add_parser("add")
    s.add_argument("--severity", required=True, choices=SEVERITIES)
    s.add_argument("--category", required=True, choices=CATEGORIES)
    s.add_argument("--title", required=True)
    s.add_argument("--location", required=True)
    s.add_argument("--status", default="suspected", choices=STATUSES)
    s.add_argument("--rule", help="business rule ID, e.g. R-01")
    s.add_argument("--repro"); s.add_argument("--evidence")
    s.add_argument("--root-cause", dest="root_cause")
    s.add_argument("--siblings"); s.add_argument("--impact")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("attempt", help="record a fix attempt and its outcome")
    s.add_argument("id")
    s.add_argument("--mechanism", required=True)
    s.add_argument("--outcome", required=True, choices=OUTCOMES)
    s.add_argument("--measured", required=True,
                   help="the observed result, not what the fix claims")
    s.add_argument("--failure-class", dest="failure_class",
                   choices=FAILURE_CLASSES)
    s.add_argument("--note")
    s.set_defaults(fn=cmd_attempt)

    s = sub.add_parser("set")
    s.add_argument("id")
    s.add_argument("--severity", choices=SEVERITIES)
    s.add_argument("--category", choices=CATEGORIES)
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--title"); s.add_argument("--location")
    s.add_argument("--rule")
    s.add_argument("--repro"); s.add_argument("--evidence")
    s.add_argument("--root-cause", dest="root_cause")
    s.add_argument("--impact"); s.add_argument("--fix")
    s.add_argument("--fix-commit", dest="fix_commit")
    s.add_argument("--test"); s.add_argument("--siblings"); s.add_argument("--notes")
    s.set_defaults(fn=cmd_set)

    s = sub.add_parser("list")
    s.add_argument("--status", choices=STATUSES)
    s.add_argument("--severity", choices=SEVERITIES)
    s.add_argument("--category", choices=CATEGORIES)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("stats"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("report"); s.set_defaults(fn=cmd_report)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
