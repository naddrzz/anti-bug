# Agent notes

## Verify

```bash
python validate-skills.py
python -B -m unittest discover -v
python -m ruff check . --output-format concise
python -m mypy --ignore-missing-imports <one-script.py>
```

Ruff reports pre-existing E702/E741 style findings in the script trees. Compare against baseline before treating them as a regression gate. Mypy needs `types-PyYAML` installed to clear the `import yaml` warning in `validate-skills.py`; the script is designed to work without PyYAML.

## Layout

`anti-bug/` and `anti-bug-review/` at repo root are the canonical skill trees. `skills/anti-bug/` and `skills/anti-bug-review/` are mirror copies installed by `npx skills`. Both layouts ship — keep corresponding files byte-identical (script directories especially). `validate-skills.py` checks `*/SKILL.md` and `skills/*/SKILL.md`; keep it passing — broken frontmatter is silently skipped by every agent loader.

## Test conventions

`tests/test_regressions.py` is stdlib-only and loads hyphenated scripts via `importlib.util.spec_from_file_location`, so new regression tests stay under `tests/` and do not need pytest or package layout. Tests create temp repos and temp Git repositories; never require network or touch the checked-out repo's git config.

## Evidence artifacts

Anti-bug ledger output goes to `.anti-bug/` (gitignored) inside the reviewed repo by default, or an external workspace via `ANTI_BUG_ROOT` / `--out`. Do not commit generated `findings.json` or `review.json`.
