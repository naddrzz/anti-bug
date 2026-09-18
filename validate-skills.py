#!/usr/bin/env python3
"""Validate every SKILL.md in this repository.

This exists because a SKILL.md can look perfectly correct to a human and still
be rejected by the loader. The failure that prompted it: an unquoted YAML
scalar containing ": " (colon followed by space), which YAML reads as the start
of a nested mapping. The file rendered fine on GitHub, read fine in an editor,
and every agent silently skipped it.

Run locally:  python validate-skills.py
Exit code 0 = all skills load. Non-zero = at least one would be skipped.

Uses PyYAML when available and falls back to a targeted check otherwise, so it
is useful even on a machine with nothing installed.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REQUIRED = ("name", "description")
FM = re.compile(r"^---\n(.*?)\n---", re.S)

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def plain_scalar_problems(block: str) -> list[str]:
    """Catch the specific YAML footguns that break frontmatter without PyYAML.

    Only the ones that actually bite a single-line `key: value` frontmatter:
    a colon+space inside an unquoted value, and an unquoted value opening with
    a YAML indicator character.
    """
    problems = []
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if not value or value[0] in "\"'|>[{":
            continue  # quoted, block scalar, or flow collection - parser's job
        hit = re.search(r":\s", value)
        if hit:
            near = value[max(0, hit.start() - 40):hit.start() + 25]
            problems.append(
                f"{key}: unquoted value contains ': ' at offset {hit.start()} "
                f"-> YAML reads this as a nested mapping and skips the file.\n"
                f"      ...{near}...\n"
                f"      Fix: rephrase without the colon, or quote the value."
            )
        if value[0] in "&*!%@`":
            problems.append(f"{key}: unquoted value starts with the YAML "
                            f"indicator {value[0]!r}; quote it.")
    return problems


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    if not m:
        return ["no YAML frontmatter block (file must start with ---)"]
    block = m.group(1)

    errors = plain_scalar_problems(block)
    if errors:
        return errors

    if HAVE_YAML:
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError as e:
            return [f"YAML parse error: {str(e).splitlines()[0]}"]
        if not isinstance(data, dict):
            return ["frontmatter is not a mapping"]
        for key in REQUIRED:
            v = data.get(key)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"missing or empty required key: {key}")
        if not errors and not re.fullmatch(r"[a-z0-9-]+", data["name"]):
            errors.append(f"name {data['name']!r} should be lowercase kebab-case")
    else:
        for key in REQUIRED:
            if not re.search(rf"^{key}:\s*\S", block, re.M):
                errors.append(f"missing required key: {key}")
    return errors


def main() -> int:
    root = Path(__file__).parent
    files = sorted(set(root.glob("*/SKILL.md")) | set(root.glob("skills/*/SKILL.md")))
    if not files:
        print("No skills found under */SKILL.md or skills/*/SKILL.md", file=sys.stderr)
        return 1

    if not HAVE_YAML:
        print("note: PyYAML not installed - running structural checks only "
              "(pip install pyyaml for full validation)\n")

    failed = 0
    for f in files:
        rel = f.relative_to(root)
        errs = check(f)
        if errs:
            failed += 1
            print(f"FAIL  {rel}")
            for e in errs:
                print(f"      {e}")
        else:
            print(f"ok    {rel}")

    print()
    if failed:
        print(f"{failed} of {len(files)} skills would be skipped by a loader.")
        return 1
    print(f"All {len(files)} skills load cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
