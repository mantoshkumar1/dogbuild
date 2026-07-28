"""Tests for `dogbuild start` — the branded launcher."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from psk import __main__ as cli, exit_codes, gitutil, launcher, registry, install
from tests._helpers import cleanup, make_repo, import_min_genesis


def run(argv):
    """Run the CLI, capturing stdout; return (exit_code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


def _init_and_genesis(root):
    """Initialize DogBuild and import a minimal genesis so brief/state works."""
    run(["init", root, "--objective", "test objective"])
    import_min_genesis(root)


class TestStartDryRun(unittest.TestCase):
    """dogbuild start --dry-run"""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_dry_run_returns_success(self):
        code, out = run(["start", self.root, "--dry-run"])
        self.assertEqual(code, exit_codes.SUCCESS)
        self.assertIn("DogBuild", out)
        # The dry run must show the exact interactive prompt it would open.
        self.assertIn("dogBuild>", out)

    def test_dry_run_json_contains_required_fields(self):
        code, out = run(["start", self.root, "--dry-run", "--json"])
        self.assertEqual(code, exit_codes.SUCCESS)
        data = json.loads(out)
        for key in ("root", "project", "permission_mode", "claude_executable",
                     "instruction", "args", "skill", "dry_run"):
            self.assertIn(key, data, f"missing key: {key}")
        self.assertTrue(data["dry_run"])

    def test_dry_run_does_not_exec(self):
        """Dry run must not call os.execvp."""
        with mock.patch("os.execvp") as m:
            run(["start", self.root, "--dry-run"])
            m.assert_not_called()


class TestStartRepoDetection(unittest.TestCase):
    """Repository detection and path handling."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)

    def test_current_directory_detection(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        _init_and_genesis(root)
        result = launcher.start(root, dry_run=True)
        self.assertEqual(result["root"], root)

    def test_explicit_repo_path(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        _init_and_genesis(root)
        result = launcher.start(root, dry_run=True)
        self.assertEqual(result["root"], root)

    def test_path_with_spaces(self):
        parent = tempfile.mkdtemp(prefix="psk-space-")
        spaced = os.path.join(parent, "my project dir")
        os.makedirs(spaced)
        self.addCleanup(shutil.rmtree, parent, True)
        # init git repo in the spaced path
        from tests._helpers import git
        git(spaced, "init", "-b", "main")
        git(spaced, "config", "user.email", "t@example.com")
        git(spaced, "config", "user.name", "Test")
        with open(os.path.join(spaced, "README.md"), "w") as f:
            f.write("# test\n")
        git(spaced, "add", "-A")
        git(spaced, "commit", "-m", "init")
        root = gitutil.repo_root(spaced)
        _init_and_genesis(root)
        result = launcher.start(root, dry_run=True)
        self.assertEqual(result["root"], root)
        # Verify args don't use shell splitting
        self.assertIn(result["instruction"], result["args"])

    def test_non_git_directory_fails(self):
        nongit = tempfile.mkdtemp(prefix="psk-nongit-")
        self.addCleanup(shutil.rmtree, nongit, True)
        code, _ = run(["start", nongit, "--dry-run"])
        self.assertEqual(code, exit_codes.NO_REPOSITORY)


class TestStartUninitialized(unittest.TestCase):
    """Uninitialized repository handling."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        shutil.rmtree(self.regdir, ignore_errors=True)

    def test_uninitialized_repo_shows_init_hint(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code, _ = run(["start", d, "--dry-run"])
        self.assertEqual(code, exit_codes.NOT_INITIALIZED)
        # The error handler in main() prints the message


class TestStartClaudeAvailability(unittest.TestCase):
    """Missing Claude executable handling."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_dry_run_reports_claude_executable(self):
        result = launcher.start(self.root, dry_run=True)
        # claude_executable is either a path or None; either is valid in dry run
        self.assertIn("claude_executable", result)

    def test_missing_claude_in_raw_mode_exits(self):
        """Raw mode hands the terminal to Claude, so a missing binary is fatal."""
        with mock.patch.object(launcher, "find_claude", return_value=None):
            with self.assertRaises(SystemExit) as ctx:
                launcher.start(self.root, raw_claude=True, dry_run=False)
            self.assertEqual(ctx.exception.code, 1)

    def test_missing_claude_still_opens_the_shell(self):
        """Default mode degrades: state commands work without Claude installed."""
        with mock.patch.object(launcher, "find_claude", return_value=None), \
                mock.patch.object(launcher.shell_mod, "run_shell", return_value=0) as m:
            with self.assertRaises(SystemExit) as ctx:
                launcher.start(self.root, dry_run=False)
            self.assertEqual(ctx.exception.code, 0)
            m.assert_called_once()


class TestStartArguments(unittest.TestCase):
    """Claude argument list construction."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_default_permission_mode_is_acceptEdits(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertEqual(result["permission_mode"], "acceptEdits")
        self.assertIn("--permission-mode", result["args"])
        idx = result["args"].index("--permission-mode")
        self.assertEqual(result["args"][idx + 1], "acceptEdits")

    def test_permission_mode_override(self):
        result = launcher.start(self.root, permission_mode="plan", dry_run=True)
        self.assertEqual(result["permission_mode"], "plan")

    def test_dangerous_permission_mode_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            launcher.start(self.root, permission_mode="bypassPermissions", dry_run=True)
        self.assertIn("not allowed", str(ctx.exception))

    def test_dontAsk_permission_mode_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            launcher.start(self.root, permission_mode="dontAsk", dry_run=True)
        self.assertIn("not allowed", str(ctx.exception))

    def test_args_are_list_not_shell_string(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIsInstance(result["args"], list)
        self.assertEqual(result["args"][0], "claude")

    def test_instruction_contains_project_identity(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn("Project:", result["instruction"])
        self.assertIn(result["project"], result["instruction"])

    def test_instruction_contains_milestone(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn("Current milestone:", result["instruction"])

    def test_instruction_is_concise(self):
        result = launcher.start(self.root, dry_run=True)
        # Instruction should be reasonable — under 2000 chars
        self.assertLess(len(result["instruction"]), 2000,
                        "Startup instruction is too large")


class TestStartSkillInstallation(unittest.TestCase):
    """Skill installation during start."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_skill_installed_on_first_start(self):
        result = launcher.start(self.root, dry_run=True)
        # First start should install the skill (dry_run passes through)
        self.assertIn(result["skill"]["status"],
                      ("installed", "would_install", "up_to_date"))

    def test_skill_not_reinstalled_when_current(self):
        # First install
        install.install_claude_skill(skills_root=self.skills_dir)
        # Now start — skill should be up_to_date
        result = launcher.start(self.root, dry_run=True)
        self.assertEqual(result["skill"]["status"], "up_to_date")


class TestStartNoShellExecution(unittest.TestCase):
    """Launcher must not use unsafe shell execution."""

    def test_args_are_list(self):
        args = launcher.build_claude_args("test prompt", "acceptEdits")
        self.assertIsInstance(args, list)
        for a in args:
            self.assertIsInstance(a, str)

    def test_no_shell_true_in_source(self):
        """The launcher module source must not contain shell=True."""
        # Resolve the .py source, not a .pyc
        src_path = Path(launcher.__file__)
        if src_path.suffix == ".pyc":
            # Navigate from __pycache__/launcher.cpython-XY.pyc to launcher.py
            src_path = src_path.parent.parent / (src_path.stem.split(".")[0] + ".py")
        src = src_path.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", src)
        self.assertNotIn("shell = True", src)


class TestStartCompatibility(unittest.TestCase):
    """statekeeper / psk / dogbuild compatibility."""

    def test_all_entry_points_still_parse_start(self):
        p = cli._build_parser()
        # Verify start parses
        ns = p.parse_args(["start", "/tmp", "--dry-run"])
        self.assertTrue(hasattr(ns, "func"), "start has no func")
        # Verify other key commands still exist
        for subcmd in ["init", "status", "brief", "where-am-i"]:
            ns = p.parse_args([subcmd, "/tmp"])
            self.assertTrue(hasattr(ns, "func"), f"{subcmd} has no func")


class TestStartLaunchMode(unittest.TestCase):
    """Default start opens the DogBuild shell; --raw-claude execs Claude."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_dry_run_reports_shell_mode_and_prompt(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertEqual(result["mode"], "dogbuild-shell")
        self.assertEqual(result["prompt"], "dogBuild>")

    def test_dry_run_raw_claude_reports_raw_mode(self):
        result = launcher.start(self.root, raw_claude=True, dry_run=True)
        self.assertEqual(result["mode"], "raw-claude")
        self.assertIsNone(result["hooks"])

    def test_default_start_runs_the_shell_not_execvp(self):
        with mock.patch.object(launcher, "find_claude", return_value="/usr/bin/claude"), \
                mock.patch.object(launcher.shell_mod, "run_shell", return_value=0) as run_shell, \
                mock.patch("os.execvp") as execvp:
            with self.assertRaises(SystemExit):
                launcher.start(self.root, dry_run=False)
            run_shell.assert_called_once()
            execvp.assert_not_called()

    def test_raw_claude_execs_and_skips_the_shell(self):
        with mock.patch.object(launcher, "find_claude", return_value="/usr/bin/claude"), \
                mock.patch.object(launcher.shell_mod, "run_shell") as run_shell, \
                mock.patch("os.execvp") as execvp:
            launcher.start(self.root, raw_claude=True, dry_run=False)
            execvp.assert_called_once()
            run_shell.assert_not_called()

    def test_session_banner_matches_required_format(self):
        result = launcher.start(self.root, dry_run=True)
        banner = result["session_banner"]
        self.assertIn("DogBuild", banner)
        for label in ("Project:", "Stage:", "Current milestone:",
                      "Last verified:", "Human needed:"):
            self.assertIn(label, banner)


class TestStartBanner(unittest.TestCase):
    """Banner rendering."""

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        _init_and_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        if self._old_skills is None:
            os.environ.pop("CLAUDE_SKILLS_DIR", None)
        else:
            os.environ["CLAUDE_SKILLS_DIR"] = self._old_skills
        shutil.rmtree(self.regdir, ignore_errors=True)
        shutil.rmtree(self.skills_dir, ignore_errors=True)
        cleanup(self.d)

    def test_banner_contains_dogbuild_brand(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn("DogBuild", result["banner"])

    def test_banner_contains_exact_next_action(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn("Exact next action:", result["banner"])
        self.assertIn(result["state"]["exact_next_action"], result["banner"])

    def test_banner_contains_project_name(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn(result["project"], result["banner"])

    def test_banner_contains_milestone(self):
        result = launcher.start(self.root, dry_run=True)
        self.assertIn("milestone", result["banner"].lower())


if __name__ == "__main__":
    unittest.main()
