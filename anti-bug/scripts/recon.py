#!/usr/bin/env python3
"""Phase 0 reconnaissance for the anti-bug skill.

Detects stack, entry points, test setup, config and risk surfaces so the
context-building phase starts from facts rather than assumptions. Read-only:
it never modifies the repository.

Usage:  python recon.py [path] [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", "out", "target",
             ".venv", "venv", "env", "__pycache__", ".next", ".nuxt", ".cache",
             "coverage", ".tox", ".mypy_cache", ".pytest_cache", ".gradle",
             "bin", "obj", ".idea", ".vscode", "Pods", ".terraform", ".anti-bug"}

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP",
    ".rs": "Rust", ".cs": "C#", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++",
    ".hpp": "C++", ".swift": "Swift", ".scala": "Scala", ".ex": "Elixir",
    ".exs": "Elixir", ".dart": "Dart", ".sql": "SQL", ".sh": "Shell",
    ".vue": "Vue", ".svelte": "Svelte",
}

MANIFESTS = {
    "package.json": ("Node/JS", "npm ci || npm install"),
    "pnpm-lock.yaml": ("Node/pnpm", "pnpm install --frozen-lockfile"),
    "yarn.lock": ("Node/yarn", "yarn install --immutable"),
    "requirements.txt": ("Python/pip", "pip install -r requirements.txt"),
    "pyproject.toml": ("Python", "pip install -e . (or poetry install / uv sync)"),
    "Pipfile": ("Python/pipenv", "pipenv install --dev"),
    "go.mod": ("Go", "go mod download"),
    "pom.xml": ("Java/Maven", "./mvnw -q verify"),
    "build.gradle": ("Java/Gradle", "./gradlew build"),
    "build.gradle.kts": ("Kotlin/Gradle", "./gradlew build"),
    "composer.json": ("PHP", "composer install"),
    "Gemfile": ("Ruby", "bundle install"),
    "Cargo.toml": ("Rust", "cargo build --all-targets"),
    "mix.exs": ("Elixir", "mix deps.get"),
    "pubspec.yaml": ("Dart/Flutter", "flutter pub get"),
}

ENTRY_HINTS = re.compile(
    r"(^|/)(main|index|app|server|cli|worker|manage|wsgi|asgi|program|bootstrap|"
    r"entrypoint|daemon|consumer|scheduler|cron)\.(py|js|ts|mjs|go|java|rb|php|rs|cs)$",
    re.I)

CONFIG_FILES = [
    ".env", ".env.example", ".env.local", ".env.production", "docker-compose.yml",
    "docker-compose.yaml", "Dockerfile", "Makefile", "Procfile", "vercel.json",
    "serverless.yml", "nginx.conf", "tsconfig.json", ".eslintrc", ".eslintrc.json",
    ".eslintrc.js", "eslint.config.js", "ruff.toml", "setup.cfg", "tox.ini",
    "mypy.ini", ".golangci.yml", "phpstan.neon", ".rubocop.yml",
]

CI_DIRS = [".github/workflows", ".gitlab-ci.yml", ".circleci", "Jenkinsfile",
           "azure-pipelines.yml", ".drone.yml", "bitbucket-pipelines.yml"]

RISK_PATTERNS = [
    ("hardcoded secret",
     re.compile(r"""(api[_-]?key|secret|password|passwd|token|private[_-]?key)\s*[=:]\s*["'][^"']{8,}["']""", re.I)),
    ("TLS verification disabled",
     re.compile(r"(verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true|NODE_TLS_REJECT_UNAUTHORIZED)")),
    ("wildcard CORS",
     re.compile(r"""(Access-Control-Allow-Origin["']?\s*[,:]\s*["']\*|origin\s*:\s*["']\*["']|cors\(\s*\))""", re.I)),
    ("empty catch / except pass",
     re.compile(r"(catch\s*\([^)]*\)\s*\{\s*\}|except[^:\n]*:\s*\n\s*pass\b)")),
    ("dangerous eval/exec",
     re.compile(r"(\beval\s*\(|\bexec\s*\(|new Function\s*\(|pickle\.loads|yaml\.load\s*\((?!.*Safe))")),
    ("shell=True / exec",
     re.compile(r"(shell\s*=\s*True|child_process\.exec\s*\(|os\.system\s*\()")),
    ("string-built SQL",
     re.compile(r"""(execute\s*\(\s*f["']|execute\s*\(\s*["'][^"']*["']\s*[+%]|query\s*\(\s*`[^`]*\$\{)""")),
    ("debug mode on",
     re.compile(r"(DEBUG\s*=\s*True|debug\s*:\s*true|app\.debug\s*=\s*True)")),
    ("TODO/FIXME in error path",
     re.compile(r"(catch|except|rescue)[^\n]{0,80}\n[^\n]{0,80}(TODO|FIXME|XXX|HACK)", re.I)),
]

TEXT_EXT = set(LANG_BY_EXT) | {".json", ".yml", ".yaml", ".toml", ".ini", ".env",
                               ".cfg", ".conf", ".xml", ".tf", ".gradle"}


def walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git")]
        for fn in filenames:
            yield Path(dirpath) / fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-risk", type=int, default=40)
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.is_dir():
        sys.exit(f"Not a directory: {root}")

    langs = Counter()
    loc = Counter()
    files = []
    manifests, configs, entries, tests, migrations, ci = [], [], [], [], [], []
    risks = []

    for p in walk(root):
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError:
            continue
        files.append(rel)
        ext = p.suffix.lower()

        if p.name in MANIFESTS:
            manifests.append(rel)
        if p.name in CONFIG_FILES or p.name.startswith(".env"):
            configs.append(rel)
        if any(rel.startswith(c) or p.name == c for c in CI_DIRS):
            ci.append(rel)
        if ENTRY_HINTS.search(rel):
            entries.append(rel)
        low = rel.lower()
        if re.search(r"(^|/)(tests?|spec|__tests__|e2e)(/|$)", low) or \
           re.search(r"[._-](test|spec)\.[a-z]+$", low) or \
           re.search(r"(^|/)test_[^/]+\.py$", low):
            tests.append(rel)
        if re.search(r"(^|/)(migrations?|migrate|db/migrate|alembic)(/|$)", low):
            migrations.append(rel)

        if ext in LANG_BY_EXT:
            langs[LANG_BY_EXT[ext]] += 1
            try:
                n = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
                loc[LANG_BY_EXT[ext]] += n
            except OSError:
                pass

        if ext in TEXT_EXT and len(risks) < args.max_risk * 4:
            try:
                if p.stat().st_size > 2_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for label, rx in RISK_PATTERNS:
                m = rx.search(text)
                if m:
                    line = text[:m.start()].count("\n") + 1
                    risks.append({"pattern": label, "location": f"{rel}:{line}"})

    install_cmds = []
    for m in manifests:
        name = Path(m).name
        if name in MANIFESTS:
            install_cmds.append(MANIFESTS[name][1])

    result = {
        "root": str(root),
        "file_count": len(files),
        "languages": [{"language": k, "files": v, "loc": loc[k]}
                      for k, v in langs.most_common()],
        "manifests": sorted(set(manifests)),
        "install_commands": sorted(set(install_cmds)),
        "entry_points": sorted(set(entries))[:40],
        "config_files": sorted(set(configs))[:40],
        "ci": sorted(set(ci))[:20],
        "test_files": len(tests),
        "test_sample": sorted(tests)[:15],
        "migrations": sorted(set(migrations))[:20],
        "risk_hits": risks[:args.max_risk],
        "has_git": (root / ".git").exists(),
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return

    def head(t):
        print(f"\n{t}\n" + "-" * len(t))

    print(f"ANTI-BUG RECON  {root}")
    print(f"{len(files)} files scanned (build/vendor dirs skipped)")

    head("Languages")
    if result["languages"]:
        for l in result["languages"][:10]:
            print(f"  {l['language']:<12} {l['files']:>5} files  {l['loc']:>8} lines")
    else:
        print("  none detected")

    head("Manifests / install")
    for m in result["manifests"] or ["  (none found)"]:
        print(f"  {m}")
    if result["install_commands"]:
        print("  suggested:")
        for c in result["install_commands"]:
            print(f"    $ {c}")

    head("Entry points (verify by reading - heuristic)")
    for e in result["entry_points"] or ["  (none matched the heuristic - look for frameworks' own conventions)"]:
        print(f"  {e}")

    head("Tests")
    print(f"  {result['test_files']} test files")
    for t in result["test_sample"]:
        print(f"  {t}")
    if result["test_files"] == 0:
        print("  NOTE: no tests found. Every fix will need a test written from scratch,")
        print("  and the revert-check in Phase 4 becomes the only proof a fix works.")

    head("Config / secrets surface")
    for c in result["config_files"] or ["  (none found)"]:
        print(f"  {c}")

    head("CI")
    for c in result["ci"] or ["  (none found)"]:
        print(f"  {c}")

    if result["migrations"]:
        head("Migrations")
        for m in result["migrations"]:
            print(f"  {m}")

    head(f"Risk-pattern hits ({len(result['risk_hits'])} shown)")
    if result["risk_hits"]:
        for r in result["risk_hits"]:
            print(f"  [{r['pattern']}] {r['location']}")
        print("\n  These are LEADS, not findings. Open each one and confirm the data")
        print("  is actually attacker-reachable before it enters the ledger as confirmed.")
    else:
        print("  none matched")

    head("Next")
    print("  1. Read the README, architecture docs and manifests listed above.")
    print("  2. Trace one request end to end through an entry point.")
    print("  3. Rank areas by blast radius (money, auth, PII, deletion).")
    print("  4. python scripts/hotspots.py   (if git history exists)")
    print("  5. python scripts/ledger.py init")


if __name__ == "__main__":
    main()
