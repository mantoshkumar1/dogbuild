import shutil
import tempfile
import unittest
from pathlib import Path

from psk import __main__ as cli, install
from psk.errors import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestInstallAndSkill(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="psk-skills-"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # --- command compatibility ------------------------------------------- #
    def test_scripts_declare_dogbuild_and_statekeeper(self):
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "dogbuild"', pyproject)
        self.assertNotIn('name = "project-state-keeper"', pyproject)
        for line in ['statekeeper = "psk.__main__:main"',
                     'dogbuild = "psk.__main__:main"',
                     'psk = "psk.__main__:main"']:
            self.assertIn(line, pyproject, line)

    def test_parser_wires_install_and_whereami(self):
        p = cli._build_parser()
        ns = p.parse_args(["install", "claude", "--dry-run"])
        self.assertIs(ns.func, cli._cmd_install_claude)
        self.assertTrue(ns.dry_run)
        ns2 = p.parse_args(["where-am-i", "/tmp"])
        self.assertTrue(hasattr(ns2, "func"))

    # --- skill package content ------------------------------------------- #
    def test_skill_exists_with_required_behavior(self):
        skill = install.source_dir() / "SKILL.md"
        self.assertTrue(skill.is_file(), skill)
        txt = skill.read_text(encoding="utf-8")
        for needle in ["name: dogbuild",
                       "STATE_QUERY",                       # plain-English state query
                       "What's happening",
                       "STOP_STATE_CHANGED",                # forbidden-jargon guidance
                       "Deliver the smallest acceptable",   # delivery-first rule
                       "Live repository and test evidence", # latest-evidence rule
                       "where-am-i --json",                 # session-start behavior
                       "Goal Contract diff",                # goal-change guard
                       "recover from repository evidence"]:  # session continuity
            self.assertIn(needle, txt, needle)

    # --- installer ------------------------------------------------------- #
    def test_dry_run_writes_nothing(self):
        r = install.install_claude_skill(skills_root=str(self.root), dry_run=True)
        self.assertEqual(r["status"], "would_install")
        self.assertTrue(r["changed"])
        self.assertFalse((self.root / "dogbuild").exists())

    def test_first_install_copies_content(self):
        r = install.install_claude_skill(skills_root=str(self.root))
        self.assertEqual(r["status"], "installed")
        dest = self.root / "dogbuild" / "SKILL.md"
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.read_text(encoding="utf-8"),
                         (install.source_dir() / "SKILL.md").read_text(encoding="utf-8"))

    def test_repeat_install_is_idempotent(self):
        install.install_claude_skill(skills_root=str(self.root))
        r2 = install.install_claude_skill(skills_root=str(self.root))
        self.assertEqual(r2["status"], "up_to_date")
        self.assertEqual(r2["changed"], [])

    def test_preserves_unrelated_files(self):
        (self.root / "other-skill").mkdir(parents=True)
        (self.root / "other-skill" / "SKILL.md").write_text("keep me", encoding="utf-8")
        (self.root / "loose.txt").write_text("loose", encoding="utf-8")
        install.install_claude_skill(skills_root=str(self.root))
        self.assertEqual((self.root / "other-skill" / "SKILL.md").read_text(encoding="utf-8"),
                         "keep me")
        self.assertEqual((self.root / "loose.txt").read_text(encoding="utf-8"), "loose")
        self.assertTrue((self.root / "dogbuild" / "SKILL.md").is_file())

    def test_missing_source_handled_safely(self):
        orig = install.source_dir
        install.source_dir = lambda: self.root / "does-not-exist"
        try:
            with self.assertRaises(ValidationError):
                install.install_claude_skill(skills_root=str(self.root))
        finally:
            install.source_dir = orig


if __name__ == "__main__":
    unittest.main()
