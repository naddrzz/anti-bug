import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import mock

os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

REPO = Path(__file__).resolve().parent.parent
ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

VALIDATOR_PATH = REPO / "validate-skills.py"
SKILL_MDS = [
    REPO / "anti-bug" / "SKILL.md",
    REPO / "anti-bug-review" / "SKILL.md",
    REPO / "skills" / "anti-bug" / "SKILL.md",
    REPO / "skills" / "anti-bug-review" / "SKILL.md",
]
REPAIR_LEDGERS = [
    REPO / "anti-bug" / "scripts" / "ledger.py",
    REPO / "skills" / "anti-bug" / "scripts" / "ledger.py",
]
REVIEW_LEDGERS = [
    REPO / "anti-bug-review" / "scripts" / "ledger.py",
    REPO / "skills" / "anti-bug-review" / "scripts" / "ledger.py",
]
INTEGRITY_SCRIPTS = [
    REPO / "anti-bug-review" / "scripts" / "integrity.py",
    REPO / "skills" / "anti-bug-review" / "scripts" / "integrity.py",
]
RECON_SCRIPTS = [
    REPO / "anti-bug" / "scripts" / "recon.py",
    REPO / "anti-bug-review" / "scripts" / "recon.py",
    REPO / "skills" / "anti-bug" / "scripts" / "recon.py",
    REPO / "skills" / "anti-bug-review" / "scripts" / "recon.py",
]
HOTSPOT_SCRIPTS = [
    REPO / "anti-bug" / "scripts" / "hotspots.py",
    REPO / "anti-bug-review" / "scripts" / "hotspots.py",
    REPO / "skills" / "anti-bug" / "scripts" / "hotspots.py",
    REPO / "skills" / "anti-bug-review" / "scripts" / "hotspots.py",
]

_MODULES = {}


def load_module(path):
    key = str(path)
    if key not in _MODULES:
        spec = spec_from_file_location("loaded_" + str(abs(hash(key))), key)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        _MODULES[key] = mod
    return _MODULES[key]


def run_capture(fn, *args, **kwargs):
    out, err = io.StringIO(), io.StringIO()
    exc = None
    with redirect_stdout(out), redirect_stderr(err):
        try:
            fn(*args, **kwargs)
        except (SystemExit, OSError) as e:
            exc = e
    return exc, out.getvalue(), err.getvalue()


def failed(exc):
    if exc is None:
        return False
    if isinstance(exc, SystemExit):
        return bool(exc.code)
    return True


def rel(p):
    return Path(p).relative_to(REPO).as_posix()


class ValidatorEvidenceTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.validator = load_module(VALIDATOR_PATH)

    def test_all_skill_frontmatter(self):
        for p in SKILL_MDS:
            with self.subTest(skill=rel(p)):
                self.assertEqual(self.validator.check(p), [])

    def test_frontmatter_yaml_parses(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for p in SKILL_MDS:
            with self.subTest(skill=rel(p)):
                m = self.validator.FM.match(p.read_text(encoding="utf-8"))
                self.assertIsNotNone(m)
                try:
                    data = yaml.safe_load(m.group(1))
                except yaml.YAMLError as e:
                    self.fail(f"frontmatter does not parse: {e}")
                self.assertIsInstance(data, dict)
                self.assertTrue(data.get("name"))
                self.assertTrue(data.get("description"))

    def test_validator_discovers_root_skills(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good = root / "skills" / "good"
            bad = root / "bad"
            good.mkdir(parents=True)
            bad.mkdir(parents=True)
            (good / "SKILL.md").write_bytes(
                b"---\nname: good\ndescription: A fine skill\n---\n# Good\n")
            (bad / "SKILL.md").write_bytes(
                b"---\nname: bad\ndescription: invalid: value\n---\n# Bad\n")
            out = io.StringIO()
            with mock.patch.object(self.validator, "__file__",
                                   str(root / "validate-skills.py")), \
                    redirect_stdout(out):
                rc = self.validator.main()
            self.assertEqual(rc, 1)
            self.assertIn(str(Path("bad") / "SKILL.md"), out.getvalue())


class RepairLedgerEvidenceTests(unittest.TestCase):

    def _add_ns(self, **kw):
        base = dict(severity="high", category="correctness", title="t",
                    location="a.py:1", status="confirmed", rule=None, repro=None,
                    evidence=None, root_cause=None, siblings=None, impact=None)
        base.update(kw)
        return Namespace(**base)

    def _set_ns(self, fid, **kw):
        base = dict(id=fid, severity=None, category=None, status=None,
                    repro=None, evidence=None, root_cause=None, impact=None,
                    fix=None, fix_commit=None, notes=None, title=None,
                    location=None, rule=None, siblings=None, test=None)
        base.update(kw)
        return Namespace(**base)

    def _init(self, mod):
        run_capture(mod.cmd_init, Namespace(force=False))

    def _rule(self, mod, confidence):
        run_capture(mod.cmd_rule, Namespace(area="area", text="text",
                                            source="", confidence=confidence))

    def _findings(self, root):
        p = root / ".anti-bug" / "findings.json"
        return json.loads(p.read_text(encoding="utf-8"))["findings"]

    def test_confirmed_requires_evidence(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        run_capture(mod.cmd_add, self._add_ns())
                        run_capture(mod.cmd_add, self._add_ns(repro="   "))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "suspected")
                    self.assertEqual(fs[1]["status"], "suspected")

    def test_set_cannot_promote_inferred_rule(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        self._rule(mod, "inferred")
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="R-1"))
                        fs = self._findings(root)
                        self.assertEqual(fs[0]["status"], "needs-decision")
                        run_capture(mod.cmd_set, self._set_ns(
                            "F-001", status="confirmed"))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "needs-decision")

    def test_changing_rule_revalidates_status(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        self._rule(mod, "inferred")
                        self._rule(mod, "stated")
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="R-2"))
                        run_capture(mod.cmd_set, self._set_ns(
                            "F-001", rule="R-1"))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "needs-decision")

    def test_missing_rule_not_confirmed(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output"))
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="R-999"))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "needs-decision")
                    self.assertEqual(fs[1]["status"], "needs-decision")

    def test_stated_rule_allows_confirmed(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        self._rule(mod, "stated")
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="R-1"))
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="r1"))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "confirmed")
                    self.assertEqual(fs[1]["status"], "confirmed")

    def test_fixed_on_inferred_rule_cannot_persist(self):
        for path in REPAIR_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    with mock.patch.dict(os.environ,
                                         {"ANTI_BUG_ROOT": str(root)}):
                        self._init(mod)
                        self._rule(mod, "inferred")
                        run_capture(mod.cmd_add, self._add_ns(
                            category="business-logic", repro="cmd output",
                            rule="R-1"))
                        run_capture(mod.cmd_set, self._set_ns(
                            "F-001", status="fixed", test="tests/x.py::y"))
                        fs = self._findings(root)
                    self.assertEqual(fs[0]["status"], "needs-decision")


class ReviewLedgerEvidenceTests(unittest.TestCase):

    def _add_ns(self, out, **kw):
        base = dict(out=out, severity="high", category="correctness", title="t",
                    location="a.py:1", status="reproduced", rule=None,
                    perspective=None, repro=None, evidence=None,
                    root_cause=None, impact=None, recommendation="fix it",
                    effort=None, fix_risk=None, occurrences=None, notes=None)
        base.update(kw)
        return Namespace(**base)

    def _set_ns(self, out, fid, **kw):
        base = dict(out=out, id=fid, severity=None, category=None, status=None,
                    title=None, location=None, repro=None, evidence=None,
                    root_cause=None, impact=None, recommendation=None,
                    effort=None, fix_risk=None, perspective=None,
                    occurrences=None, notes=None, rule=None)
        base.update(kw)
        return Namespace(**base)

    def _init(self, mod, td):
        repo = Path(td) / "repo"
        out = Path(td) / "repo-review"
        repo.mkdir()
        run_capture(mod.cmd_init, Namespace(repo=str(repo), out=str(out),
                                            force=False))
        return repo, out

    def _rule(self, mod, out, confidence):
        run_capture(mod.cmd_rule, Namespace(out=str(out), area="area",
                                            text="text", source="",
                                            confidence=confidence))

    def _state(self, out):
        return json.loads((out / "review.json").read_text(encoding="utf-8"))

    def test_inferred_rule_not_proven(self):
        for path in REVIEW_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    _, out = self._init(mod, td)
                    self._rule(mod, out, "inferred")
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), category="business-logic", repro="cmd out",
                        rule="R-1"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), repro="   "))
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["status"], "unverified")
                    self.assertEqual(fs[1]["status"], "unverified")

    def test_set_revalidates_rule(self):
        for path in REVIEW_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    _, out = self._init(mod, td)
                    self._rule(mod, out, "inferred")
                    self._rule(mod, out, "stated")
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), category="business-logic", status="traced",
                        evidence="trace note", rule="R-2"))
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["status"], "traced")
                    run_capture(mod.cmd_set, self._set_ns(
                        str(out), "F-001", rule="R-1"))
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["status"], "unverified")
                    run_capture(mod.cmd_set, self._set_ns(
                        str(out), "F-001", status="reproduced"))
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["status"], "unverified")

    def test_missing_rule_not_proven(self):
        for path in REVIEW_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    _, out = self._init(mod, td)
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), category="business-logic", repro="cmd out"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), category="business-logic", repro="cmd out",
                        rule="R-999"))
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["status"], "unverified")
                    self.assertEqual(fs[1]["status"], "unverified")

    def test_unverified_only_in_questions(self):
        for path in REVIEW_LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    _, out = self._init(mod, td)
                    self._rule(mod, out, "inferred")
                    self._rule(mod, out, "stated")
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), status="unverified",
                        title="Unproven candidate"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), category="business-logic", status="reproduced",
                        repro="cmd out", rule="R-2", title="Proven keeper"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), status="traced", evidence="trace note",
                        title="Traced keeper"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), status="withdrawn", title="Withdrawn item"))
                    run_capture(mod.cmd_add, self._add_ns(
                        str(out), status="unverified", title="Legacy propped"))
                    state = self._state(out)
                    for f in state["findings"]:
                        if f["title"] == "Legacy propped":
                            f["status"] = "reproduced"
                            f["rule"] = "R-001"
                    (out / "review.json").write_text(
                        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
                    run_capture(mod.cmd_question, Namespace(
                        out=str(out), about="", text="open q", why=""))
                    _, report, _ = run_capture(mod.cmd_report,
                                             Namespace(out=str(out)))
                    table = report.split("## Findings\n", 1)[1] \
                                  .split("## Detailed findings", 1)[0]
                    detailed = report.split("## Detailed findings", 1)[1] \
                                     .split("\n## ", 1)[0]
                    questions = report.split("## Questions", 1)[1] \
                                      .split("\n## ", 1)[0]
                    self.assertNotIn("Unproven candidate", table)
                    self.assertNotIn("Unproven candidate", detailed)
                    self.assertIn("Unproven candidate", questions)
                    self.assertNotIn("Legacy propped", table)
                    self.assertNotIn("Legacy propped", detailed)
                    self.assertIn("Legacy propped", questions)
                    self.assertIn("Proven keeper", table)
                    self.assertIn("Traced keeper", table)
                    self.assertNotIn("Withdrawn item", table)
                    fs = self._state(out)["findings"]
                    self.assertEqual(fs[0]["id"], "F-001")
                    self.assertEqual(fs[0]["status"], "unverified")


class IntegrityEvidenceTests(unittest.TestCase):

    def _ns(self, repo, out):
        return Namespace(repo=str(repo), out=str(out) if out else None)

    def _repo_with(self, td, name="repo", content=b"data"):
        repo = Path(td) / name
        out = Path(td) / (name + "-review")
        repo.mkdir()
        (repo / "f.txt").write_bytes(content)
        return repo, out

    def test_large_same_size_edit_detected(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path), variant="patched-max"):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo, out = self._repo_with(td)
                    big = repo / "big.bin"
                    big.write_bytes(b"A" * 32)
                    with mock.patch.object(mod, "MAX_BYTES", 16):
                        run_capture(mod.cmd_snapshot, self._ns(repo, out))
                        big.write_bytes(b"B" * 32)
                        exc, o, _ = run_capture(mod.cmd_check,
                                                self._ns(repo, out))
                    self.assertTrue(failed(exc))
                    self.assertNotIn("byte-identical", o)
        with self.subTest(script=rel(INTEGRITY_SCRIPTS[1]), variant="real-64mib"):
            mod = load_module(INTEGRITY_SCRIPTS[1])
            with tempfile.TemporaryDirectory() as td:
                repo, out = self._repo_with(td)
                big = repo / "big.bin"
                with big.open("wb") as fh:
                    fh.seek(64 * 1024 * 1024)
                    fh.write(b"x")
                run_capture(mod.cmd_snapshot, self._ns(repo, out))
                with big.open("r+b") as fh:
                    fh.write(b"Y")
                exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
            self.assertTrue(failed(exc))
            self.assertNotIn("byte-identical", o)

    def test_unreadable_not_clean(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo, out = self._repo_with(td)
                    with mock.patch.object(
                            mod, "digest",
                            lambda p: ("unreadable", p.stat().st_size)):
                        e1, _, _ = run_capture(mod.cmd_snapshot,
                                               self._ns(repo, out))
                        e2, _, _ = run_capture(mod.cmd_check,
                                               self._ns(repo, out))
                    self.assertTrue(failed(e1) or failed(e2))

    def test_walk_error_not_clean(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo, out = self._repo_with(td)

                    def fake_walk(top, onerror=None):
                        if onerror is not None:
                            onerror(PermissionError(13, "Permission denied"))
                        return iter(())

                    with mock.patch.object(mod.os, "walk", fake_walk):
                        e1, _, _ = run_capture(mod.cmd_snapshot,
                                               self._ns(repo, out))
                        e2, o2, _ = run_capture(mod.cmd_check,
                                                self._ns(repo, out))
                    self.assertTrue(failed(e1) or failed(e2))

    def test_wrong_repository_rejected(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo_a, out = self._repo_with(td, "repo-a", b"same")
                    repo_b = Path(td) / "repo-b"
                    repo_b.mkdir()
                    (repo_b / "f.txt").write_bytes(b"same")
                    run_capture(mod.cmd_snapshot, self._ns(repo_a, out))
                    exc, o, _ = run_capture(mod.cmd_check,
                                            self._ns(repo_b, out))
                    self.assertTrue(failed(exc))

    def test_missing_repository_rejected(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo_a = Path(td) / "repo-a"
                    out = Path(td) / "ws"
                    repo_a.mkdir()
                    run_capture(mod.cmd_snapshot, self._ns(repo_a, out))
                    exc, _, _ = run_capture(
                        mod.cmd_check,
                        self._ns(Path(td) / "does-not-exist", out))
                    self.assertTrue(failed(exc))

    def test_legacy_skipped_manifest_not_clean(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo = Path(td) / "repo"
                    out = Path(td) / "ws"
                    repo.mkdir()
                    out.mkdir()
                    (repo / "big.bin").write_bytes(b"Z" * 32)
                    (out / "integrity.json").write_text(json.dumps({
                        "repo": str(repo), "taken": "t", "file_count": 1,
                        "files": {"big.bin": {"sha256": "skipped-large",
                                              "bytes": 32}},
                    }), encoding="utf-8")
                    with mock.patch.object(mod, "MAX_BYTES", 16):
                        exc, o, _ = run_capture(mod.cmd_check,
                                                self._ns(repo, out))
                    self.assertTrue(failed(exc))
                    self.assertNotIn("byte-identical", o)

    def test_clean_and_drift_controls(self):
        for path in INTEGRITY_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    repo, out = self._repo_with(td)
                    volatile = repo / "node_modules"
                    volatile.mkdir()
                    vfile = volatile / "pkg.js"
                    vfile.write_bytes(b"v1")
                    run_capture(mod.cmd_snapshot, self._ns(repo, out))
                    exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
                    self.assertIsNone(exc)
                    self.assertIn("CLEAN", o)
                    vfile.write_bytes(b"v2")
                    exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
                    self.assertIsNone(exc)
                    self.assertTrue(
                        re.search(r"excluded|skipped|ignored|volatile", o,
                                  re.I))
                    (repo / "f.txt").write_bytes(b"diff")
                    exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
                    self.assertTrue(failed(exc))
                    self.assertIn("NOT CLEAN", o)
                    (repo / "f.txt").write_bytes(b"data")
                    (repo / "new.txt").write_bytes(b"n")
                    exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
                    self.assertTrue(failed(exc))
                    (repo / "new.txt").unlink()
                    (repo / "f.txt").unlink()
                    exc, o, _ = run_capture(mod.cmd_check, self._ns(repo, out))
                    self.assertTrue(failed(exc))


class IntegrityWorkspaceTests(unittest.TestCase):

    def test_inside_workspace_refused_before_write(self):
        for path in INTEGRITY_SCRIPTS:
            mod = load_module(path)
            for variant in ("same", "nested", "env"):
                with self.subTest(script=rel(path), variant=variant):
                    with tempfile.TemporaryDirectory() as td:
                        repo = Path(td) / "app"
                        repo.mkdir()
                        (repo / "f.txt").write_text("x", encoding="utf-8")
                        out = {"same": str(repo),
                               "nested": str(repo / "new-nested"),
                               "env": None}[variant]
                        envpatch = ({"ANTI_BUG_REVIEW_OUT": str(repo / "envws")}
                                    if variant == "env" else {})
                        with mock.patch.dict(os.environ, envpatch):
                            exc, _, _ = run_capture(
                                mod.cmd_snapshot,
                                Namespace(repo=str(repo), out=out))
                        self.assertTrue(failed(exc))
                        self.assertEqual(
                            list(repo.rglob("integrity.json")), [])
                        self.assertFalse((repo / "new-nested").exists())
                        self.assertFalse((repo / "envws").exists())
            with self.subTest(script=rel(path), variant="sibling"):
                with tempfile.TemporaryDirectory() as td:
                    repo = Path(td) / "app"
                    repo.mkdir()
                    (repo / "f.txt").write_text("x", encoding="utf-8")
                    exc, _, _ = run_capture(
                        mod.cmd_snapshot,
                        Namespace(repo=str(repo),
                                  out=str(Path(td) / "app-review")))
                    self.assertIsNone(exc)


class ReconTests(unittest.TestCase):

    def _run(self, path, root):
        r = subprocess.run([sys.executable, str(path), str(root), "--json"],
                           capture_output=True, text=True, env=ENV)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_ci_and_git_exclusion(self):
        for path in RECON_SCRIPTS:
            with self.subTest(script=rel(path)):
                mod_root = tempfile.TemporaryDirectory()
                self.addCleanup(mod_root.cleanup)
                root = Path(mod_root.name)
                wf = root / ".github" / "workflows"
                wf.mkdir(parents=True)
                (wf / "ci.yml").write_text("name: ci\n", encoding="utf-8")
                gl = root / ".gitlab" / "ci"
                gl.mkdir(parents=True)
                (gl / "pipeline.yml").write_text("stages: []\n",
                                               encoding="utf-8")
                gobj = root / ".git" / "objects"
                gobj.mkdir(parents=True)
                (gobj / "ignored.py").write_text("x=1\n", encoding="utf-8")
                data = self._run(path, root)
                self.assertEqual(data["file_count"], 2)
                self.assertIn(".github/workflows/ci.yml", data["ci"])
                self.assertTrue(data["has_git"])

    def test_config_dot_env_scanned(self):
        for path in RECON_SCRIPTS:
            with self.subTest(script=rel(path)):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    (root / ".env").write_text("DEBUG=True\n", encoding="utf-8")
                    (root / ".env.example").write_text("DEBUG=True\n",
                                                     encoding="utf-8")
                    data = self._run(path, root)
                    hits = {h["location"].rsplit(":", 1)[0]
                            for h in data["risk_hits"]
                            if h["pattern"] == "debug mode on"}
                    self.assertIn(".env", hits)
                    self.assertIn(".env.example", hits)


class HotspotsTests(unittest.TestCase):

    def test_nonascii_and_spaced_filenames(self):
        for path in HOTSPOT_SCRIPTS:
            with self.subTest(script=rel(path)):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    subprocess.run(["git", "-C", td, "init", "-q"],
                                   check=True, env=ENV)
                    for name in ("café.py", "ordinary.py", "spaced name.py"):
                        (root / name).write_text("x=1\n", encoding="utf-8")
                    subprocess.run(["git", "-C", td, "add", "-A"],
                                   check=True, env=ENV)
                    subprocess.run(
                        ["git", "-C", td, "-c", "user.name=Test",
                         "-c", "user.email=test@example.invalid",
                         "commit", "-qm", "fix regression"],
                        check=True, env=ENV)
                    r = subprocess.run(
                        [sys.executable, str(path), td, "--json",
                         "--since=10.years"],
                        capture_output=True, text=True, env=ENV)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    data = json.loads(r.stdout)
                    self.assertEqual(data["commits"], 1)
                    self.assertEqual(data["fix_commits"], 1)
                    names = [f["file"] for f in data["files"]]
                    for want in ("café.py", "ordinary.py", "spaced name.py"):
                        self.assertIn(want, names)
                    for f in data["files"]:
                        if f["file"] in ("café.py", "ordinary.py",
                                         "spaced name.py"):
                            self.assertEqual(f["changes"], 1)
                            self.assertEqual(f["fixes"], 1)
                            self.assertEqual(f["lines"], 1)

    def test_multiple_commits_and_empty_message(self):
        for path in HOTSPOT_SCRIPTS:
            with self.subTest(script=rel(path)):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    subprocess.run(["git", "-C", td, "init", "-q"],
                                   check=True, env=ENV)
                    (root / "alpha.py").write_text("x=1\n", encoding="utf-8")
                    (root / "beta.py").write_text("y=1\n", encoding="utf-8")
                    subprocess.run(["git", "-C", td, "add", "-A"],
                                   check=True, env=ENV)
                    subprocess.run(
                        ["git", "-C", td, "-c", "user.name=Test",
                         "-c", "user.email=test@example.invalid",
                         "commit", "-qm", "initial"], check=True, env=ENV)
                    (root / "alpha.py").write_text("x=1\nx=2\n",
                                                   encoding="utf-8")
                    subprocess.run(["git", "-C", td, "add", "-A"],
                                   check=True, env=ENV)
                    subprocess.run(
                        ["git", "-C", td, "-c", "user.name=Test",
                         "-c", "user.email=test@example.invalid",
                         "commit", "-qm", "fix alpha"],
                        check=True, env=ENV)
                    subprocess.run(
                        ["git", "-C", td, "-c", "user.name=Test",
                         "-c", "user.email=test@example.invalid",
                         "commit", "-q", "--allow-empty",
                         "--allow-empty-message", "-m", ""],
                        check=True, env=ENV)
                    r = subprocess.run(
                        [sys.executable, str(path), td, "--json",
                         "--since=10.years"],
                        capture_output=True, text=True, env=ENV)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    data = json.loads(r.stdout)
                    self.assertEqual(data["commits"], 3)
                    self.assertEqual(data["fix_commits"], 1)
                    files = {f["file"]: f for f in data["files"]}
                    self.assertEqual(files["alpha.py"]["changes"], 2)
                    self.assertEqual(files["alpha.py"]["fixes"], 1)
                    self.assertEqual(files["beta.py"]["changes"], 1)
                    self.assertEqual(files["beta.py"]["fixes"], 0)


class LedgerPersistenceTests(unittest.TestCase):

    LEDGERS = ([("repair", p) for p in REPAIR_LEDGERS]
               + [("review", p) for p in REVIEW_LEDGERS])

    def _save(self, kind, mod, p, data):
        if kind == "repair":
            with mock.patch.object(mod, "ledger_path", lambda: p):
                mod.save(data)
        else:
            mod.save(data, p)

    def test_failed_serialization_preserves_file(self):
        for kind, path in self.LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "ledger.json"
                    self._save(kind, mod, p,
                               {"schema": 1, "findings": [], "note": "ok"})
                    before = p.read_bytes()
                    with self.assertRaises(TypeError):
                        self._save(kind, mod, p, {"bad": {1, 2, 3}})
                    self.assertEqual(p.read_bytes(), before)

    def test_failed_commit_preserves_file(self):
        for kind, path in self.LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "ledger.json"
                    self._save(kind, mod, p,
                               {"schema": 1, "findings": [], "note": "ok"})
                    before = p.read_bytes()
                    with mock.patch.object(mod.os, "replace",
                                           side_effect=OSError("disk full")):
                        with self.assertRaises(OSError):
                            self._save(kind, mod, p,
                                       {"schema": 1, "findings": [],
                                        "note": "v2"})
                    self.assertEqual(p.read_bytes(), before)
                    self.assertEqual(
                        sorted(f.name for f in Path(td).iterdir()),
                        ["ledger.json"])

    def test_partial_write_failure_preserves_file(self):
        real_open = Path.open

        class FailingWriter:
            def __init__(self, handle):
                self._handle = handle

            def __enter__(self):
                self._handle.__enter__()
                return self

            def __exit__(self, *exc):
                return self._handle.__exit__(*exc)

            def write(self, s):
                self._handle.write(s[:5])
                self._handle.flush()
                raise OSError("simulated disk full")

            def __getattr__(self, name):
                return getattr(self._handle, name)

        def patched_open(this, mode="r", *args, **kwargs):
            handle = real_open(this, mode, *args, **kwargs)
            if any(c in mode for c in "wax+"):
                return FailingWriter(handle)
            return handle

        for kind, path in self.LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "ledger.json"
                    self._save(kind, mod, p,
                               {"schema": 1, "findings": [], "note": "ok"})
                    before = p.read_bytes()
                    with mock.patch.object(Path, "open", patched_open):
                        with self.assertRaises(OSError):
                            self._save(kind, mod, p,
                                       {"schema": 1, "findings": [],
                                        "note": "v2"})
                    self.assertEqual(p.read_bytes(), before)
                    self.assertEqual(
                        sorted(f.name for f in Path(td).iterdir()),
                        ["ledger.json"])

    def test_save_roundtrips_unicode(self):
        for kind, path in self.LEDGERS:
            with self.subTest(script=rel(path)):
                mod = load_module(path)
                with tempfile.TemporaryDirectory() as td:
                    p = Path(td) / "ledger.json"
                    data = {"schema": 1, "findings": [],
                            "note": "héllo wörld — 漢字"}
                    self._save(kind, mod, p, data)
                    loaded = json.loads(p.read_text(encoding="utf-8"))
                    self.assertEqual(loaded["note"], data["note"])


class LayoutInventoryTests(unittest.TestCase):
    """Static inventory rules: the two shipped layouts stay byte-equivalent,
    and validator glob coverage includes every directory containing a SKILL.md
    entry point. These guard the siblings fixed under F-001/F-006/F-008 from
    drifting apart again."""

    @staticmethod
    def _tree_files(rel_dir):
        base = REPO / rel_dir
        return sorted(p.relative_to(base) for p in base.rglob("*")
                      if p.is_file())

    def test_root_skill_equals_skills_copy(self):
        for name in ("anti-bug", "anti-bug-review"):
            with self.subTest(skill=name):
                root_md = REPO / name / "SKILL.md"
                skills_md = REPO / "skills" / name / "SKILL.md"
                self.assertEqual(root_md.read_bytes(), skills_md.read_bytes())

    def test_script_dirs_byte_equivalent(self):
        for name in ("anti-bug", "anti-bug-review"):
            with self.subTest(skill=name):
                root_dir = REPO / name / "scripts"
                skills_dir = REPO / "skills" / name / "scripts"
                self.assertEqual(self._tree_files(root_dir),
                                 self._tree_files(skills_dir))
                for rel in self._tree_files(root_dir):
                    self.assertEqual((root_dir / rel).read_bytes(),
                                     (skills_dir / rel).read_bytes())

    def test_every_skill_md_is_validator_reachable(self):
        for p in REPO.rglob("SKILL.md"):
            rel_p = p.relative_to(REPO)
            parent = rel_p.parent
            matches = (len(parent.parts) == 1
                       or (len(parent.parts) == 2
                           and parent.parts[0] == "skills"))
            self.assertTrue(
                matches,
                f"{rel_p} sits outside validate-skills.py glob coverage "
                "(*/SKILL.md, skills/*/SKILL.md) and would not be checked")

    def test_referenced_scripts_exist_and_siblings_match(self):
        for md_name in ("anti-bug", "anti-bug-review"):
            md = REPO / "skills" / md_name / "SKILL.md"
            text = md.read_text(encoding="utf-8")
            for script in sorted(set(re.findall(r"scripts/(\w+\.py)", text))):
                for base in (REPO / md_name / "scripts",
                             REPO / "skills" / md_name / "scripts"):
                    self.assertTrue((base / script).is_file(),
                                    f"{base / script} referenced by {md} "
                                    "is missing")


if __name__ == "__main__":
    unittest.main()
