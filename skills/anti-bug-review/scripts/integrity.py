#!/usr/bin/env python3
"""Prove the review changed nothing.

A reviewer's claim to have left the codebase untouched is exactly the kind of
unverifiable assertion this skill refuses to accept from anyone else. So
snapshot the tree before reading it and check afterwards; the check output goes
in the report.

Usage
  python integrity.py snapshot --repo <path> [--out <workspace>]
  python integrity.py check    --repo <path> [--out <workspace>]

The manifest is written to the workspace, never inside the repository, so
taking the snapshot does not itself modify what it measures. Default workspace
is <repo>/../<repo-name>-review, overridable with --out or $ANTI_BUG_REVIEW_OUT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Directories whose contents legitimately change while reviewing (build output,
# caches, installed dependencies). Tracking them would bury a real edit to
# source under thousands of irrelevant diffs.
VOLATILE = {".git", "node_modules", "vendor", "dist", "build", "out", "target",
            ".venv", "venv", "env", "__pycache__", ".next", ".nuxt", ".cache",
            "coverage", ".tox", ".mypy_cache", ".pytest_cache", ".gradle",
            ".terraform", ".parcel-cache", ".turbo", "bin", "obj"}

MAX_BYTES = 64 * 1024 * 1024   # skip hashing anything larger; record size only


def workspace(repo: Path, out: str | None) -> Path:
    if out:
        return Path(out).resolve()
    env = os.environ.get("ANTI_BUG_REVIEW_OUT")
    if env:
        return Path(env).resolve()
    return (repo.parent / f"{repo.name}-review").resolve()


def inside(child: Path, parent: Path) -> bool:
    """True when child sits within parent.

    Compare resolved path parts, not string prefixes: "/srv/app-review"
    starts with "/srv/app" as text while being a sibling on disk, and a
    false warning here trains the reader to ignore real ones.
    """
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def manifest_path(repo: Path, out: str | None) -> Path:
    return workspace(repo, out) / "integrity.json"


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in VOLATILE]
        for fn in filenames:
            yield Path(dirpath) / fn


def digest(p: Path) -> tuple[str, int]:
    try:
        size = p.stat().st_size
    except OSError:
        return ("unreadable", -1)
    if size > MAX_BYTES:
        return ("skipped-large", size)
    h = hashlib.sha256()
    try:
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ("unreadable", size)
    return (h.hexdigest(), size)


def scan(repo: Path) -> dict:
    files = {}
    for p in walk(repo):
        try:
            rel = p.relative_to(repo).as_posix()
        except ValueError:
            continue
        d, size = digest(p)
        files[rel] = {"sha256": d, "bytes": size}
    return files


def cmd_snapshot(a):
    repo = Path(a.repo).resolve()
    if not repo.is_dir():
        sys.exit(f"Not a directory: {repo}")
    ws = workspace(repo, a.out)
    ws.mkdir(parents=True, exist_ok=True)
    mp = manifest_path(repo, a.out)

    files = scan(repo)
    mp.write_text(json.dumps({
        "repo": str(repo), "taken": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_count": len(files), "files": files,
    }, indent=2), encoding="utf-8")

    print(f"Snapshot: {len(files)} files under {repo}")
    print(f"Manifest: {mp}")
    if inside(ws, repo):
        print("  WARNING: the workspace is inside the repository. Move it out "
              "with --out, or the review writes into what it is measuring.",
              file=sys.stderr)


def cmd_check(a):
    repo = Path(a.repo).resolve()
    mp = manifest_path(repo, a.out)
    if not mp.exists():
        sys.exit(f"No snapshot at {mp}. Run `integrity.py snapshot` first - "
                 f"without one, 'nothing was changed' is unprovable.")

    before = json.loads(mp.read_text(encoding="utf-8"))["files"]
    after = scan(repo)

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after)
                      if before[k]["sha256"] != after[k]["sha256"])

    total = len(added) + len(removed) + len(modified)
    print(f"Integrity check against {mp}")
    print(f"  files tracked : {len(before)}")
    print(f"  added         : {len(added)}")
    print(f"  removed       : {len(removed)}")
    print(f"  modified      : {len(modified)}")
    print()

    if total == 0:
        print("CLEAN - the repository is byte-identical to the snapshot.")
        print("Paste this block into the report's integrity section.")
        return

    print("NOT CLEAN - the review modified the repository. Every entry below "
          "needs an explanation in the report, or reverting.")
    for label, items in (("added", added), ("removed", removed),
                         ("modified", modified)):
        for f in items[:40]:
            print(f"  {label:9} {f}")
        if len(items) > 40:
            print(f"  {label:9} ... and {len(items) - 40} more")
    sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("snapshot", cmd_snapshot), ("check", cmd_check)):
        s = sub.add_parser(name)
        s.add_argument("--repo", required=True)
        s.add_argument("--out", help="workspace directory (must be outside the repo)")
        s.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
