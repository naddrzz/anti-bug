#!/usr/bin/env python3
"""Rank files by defect risk using git history, for the anti-bug skill.

Files that change often AND appear often in bug-fix commits are where defects
cluster. Empirically the top ~20% of files by fix-frequency are involved in
roughly 80% of bug-fix commits - but only about a third of files are needed to
cover 80% of *distinct* bugs, and only two thirds of projects follow that
distribution at all (Walkinshaw & Minku, ESEM 2018). So this is a starting
order, never a boundary: it tells you where to look first, not where to stop.

Usage:  python hotspots.py [path] [--since 1.year] [--top 30] [--json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Commit-subject words that mark a bug fix. English by default; repositories
# whose history is written in another language should pass --fix-words, since
# an unmatched vocabulary scores every file as having zero fix commits and
# quietly flattens the ranking rather than failing loudly.
FIX_WORDS = ("fix", "bug", "patch", "hotfix", "regression", "crash", "error",
             "fail", "broken", "issue", "revert", "defect", "repair")

CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".kt", ".rb",
            ".php", ".rs", ".cs", ".c", ".cpp", ".h", ".hpp", ".swift", ".scala",
            ".ex", ".exs", ".vue", ".svelte", ".sql", ".mjs", ".cjs"}

SKIP = ("node_modules/", "vendor/", "dist/", "build/", ".min.", "package-lock",
        "pnpm-lock", "yarn.lock", "/migrations/", "__snapshots__/")


def git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        sys.exit("git not found on PATH.")
    except subprocess.TimeoutExpired:
        sys.exit("git timed out - try a shorter --since window.")
    if r.returncode != 0:
        sys.exit(f"git failed: {r.stderr.strip()[:300]}")
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--since", default="1.year")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--fix-words", dest="fix_words",
                    help="comma-separated words marking a bug-fix commit, "
                         "replacing the English defaults (e.g. for a repo "
                         "whose commit messages are in another language)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = Path(a.path).resolve()
    if not (root / ".git").exists():
        sys.exit(f"No git repository at {root}. Skip this step and rank by "
                 f"blast radius from the Context Summary instead.")

    fix_words = tuple(w.strip().lower() for w in a.fix_words.split(",")
                      if w.strip()) if a.fix_words else FIX_WORDS

    log = git(root, "log", f"--since={a.since}", "--name-only",
              "--pretty=format:%x00%H%x1f%an%x1f%s")

    churn, fixes, authors = Counter(), Counter(), defaultdict(set)
    fix_commits, total_commits = 0, 0

    for block in log.split("\x00"):
        block = block.strip("\n")
        if not block:
            continue
        head, _, body = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        _, author, subject = parts[0], parts[1], parts[2]
        total_commits += 1
        is_fix = any(w in subject.lower() for w in fix_words)
        if is_fix:
            fix_commits += 1
        for line in body.splitlines():
            f = line.strip()
            if not f or any(s in f for s in SKIP):
                continue
            if Path(f).suffix.lower() not in CODE_EXT:
                continue
            churn[f] += 1
            authors[f].add(author)
            if is_fix:
                fixes[f] += 1

    if not churn:
        sys.exit(f"No code file changes found since {a.since}. "
                 f"Try --since 5.years, or the history may be shallow "
                 f"(git fetch --unshallow).")

    rows = []
    for f, c in churn.items():
        fx = fixes[f]
        try:
            lines = sum(1 for _ in (root / f).open(encoding="utf-8", errors="ignore"))
        except OSError:
            lines = 0          # deleted or renamed since
        # fix commits weigh triple: a file that changes a lot because the
        # feature is evolving is not the same risk as one that changes a lot
        # because it keeps breaking.
        score = (fx * 3 + c) * (1 + min(lines, 3000) / 3000)
        rows.append({"file": f, "changes": c, "fixes": fx,
                     "authors": len(authors[f]), "lines": lines,
                     "score": round(score, 1)})

    rows.sort(key=lambda r: -r["score"])
    top = rows[:a.top]

    if a.json:
        print(json.dumps({"since": a.since, "commits": total_commits,
                          "fix_commits": fix_commits, "files": top}, indent=2))
        return

    print(f"ANTI-BUG HOTSPOTS  {root}")
    print(f"window: since {a.since} | {total_commits} commits "
          f"({fix_commits} look like fixes)\n")
    print(f"{'score':>7}  {'chg':>4} {'fix':>4} {'auth':>4} {'lines':>6}  file")
    print("-" * 78)
    for r in top:
        print(f"{r['score']:>7}  {r['changes']:>4} {r['fixes']:>4} "
              f"{r['authors']:>4} {r['lines']:>6}  {r['file']}")

    cutoff = max(1, len(rows) // 5)
    covered = sum(r["fixes"] for r in rows[:cutoff])
    total_fixes = sum(r["fixes"] for r in rows) or 1
    print(f"\nTop 20% of touched files ({cutoff} of {len(rows)}) account for "
          f"{covered / total_fixes:.0%} of fix-commit touches.")
    print("Start here, then widen. Files that change often may be highly")
    print("connected rather than defective, and the file holding the actual")
    print("defect is often one that rarely changes.")
    print("\nAlso worth reading regardless of score:")
    print("  - files with many authors and few tests (shared, unowned)")
    print("  - the newest code (less production exposure)")
    print("  - anything in the blast-radius ranking from Phase 0")


if __name__ == "__main__":
    main()
