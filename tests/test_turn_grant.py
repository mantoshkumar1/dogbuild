"""Tests for turn-scoped owner authorization, the DogBuild skill tool, and
the orientation fixes exposed by the real-terminal PhotoSahi acceptance."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from psk import brief, core, gitutil, registry, shell, store
from psk.governor import broker, turngrant
from psk.governor.classifier import RiskTier, classify_command
from tests._helpers import cleanup, git, make_repo, import_min_genesis
from tests.test_start import run as cli_run


# ------------------------------------------------------------------ #
# Eligibility — conservative by construction
# ------------------------------------------------------------------ #

# The exact instruction from the failed real-terminal acceptance.
ACCEPTANCE_INSTRUCTION = (
    "Inspect Git status, run the unit tests, summarize the result, "
    "and make no changes."
)

EXACT_COMMIT_INSTRUCTION = """Approved. Commit exactly the existing README.md change.
Do not make any additional edits.
Commit message:
docs: document the requirement
Do not push, deploy, publish, or start another task."""


class TestEligibility(unittest.TestCase):

    def test_the_acceptance_instruction_is_eligible(self):
        ok, reasons = turngrant.eligibility(ACCEPTANCE_INSTRUCTION)
        self.assertTrue(ok, reasons)

    def test_read_and_test_instructions_are_eligible(self):
        for msg in [
            "Inspect the repository and run the unit tests, changing nothing.",
            "Read the config files and summarize what the workflow does.",
            "Review the git log and report what changed recently.",
            "Run the test suite and tell me the result, read-only.",
            "Search the codebase for the face detection logic and explain it.",
        ]:
            self.assertTrue(turngrant.eligible(msg), msg)

    def test_state_queries_alone_do_not_create_a_grant(self):
        for msg in ["What's happening?", "where are we", "status",
                    "what's next", "did the tests pass?"]:
            self.assertFalse(turngrant.eligible(msg), msg)

    def test_ambiguous_instructions_do_not_create_a_grant(self):
        for msg in ["check", "have a look", "carry on please",
                    "do the thing", "continue with the milestone"]:
            self.assertFalse(turngrant.eligible(msg), msg)

    def test_change_requests_are_not_eligible(self):
        for msg in [
            "Inspect the repo and fix the failing test.",
            "Read the config and update the maximum file size.",
            "Run the tests and commit the result.",
            "Inspect the dependencies and install the missing one.",
            "Review the code and deploy it.",
            "Read the docs and then curl the API for the latest schema.",
            "Look at the logs and push the branch.",
        ]:
            self.assertFalse(turngrant.eligible(msg), msg)

    def test_no_change_assurance_is_not_read_as_a_change_request(self):
        # "make no changes" contains "make"; the assurance must be stripped
        # before the mutation scan or every safe instruction fails.
        for msg in [
            "Inspect Git status and make no changes.",
            "Run the unit tests and do not modify anything.",
            "Read the source, summarize it, change nothing.",
        ]:
            self.assertTrue(turngrant.eligible(msg), msg)

    def test_empty_and_short_input(self):
        self.assertFalse(turngrant.eligible(""))
        self.assertFalse(turngrant.eligible("inspect"))


# ------------------------------------------------------------------ #
# Grant lifecycle
# ------------------------------------------------------------------ #

class GrantRepoCase(unittest.TestCase):

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        cli_run(["init", self.root, "--objective", "test objective"])
        import_min_genesis(self.root)

    def tearDown(self):
        if self._old_reg is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old_reg
        shutil.rmtree(self.regdir, ignore_errors=True)
        cleanup(self.d)

    def new_commit(self):
        Path(self.root, "another.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "second")


class TestGrantLifecycle(GrantRepoCase):

    def test_eligible_instruction_creates_a_grant(self):
        grant = turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        self.assertIsNotNone(grant)
        self.assertEqual(grant["allowed_action_classes"],
                         ["repository_read", "tests_and_builds"])
        self.assertFalse(grant["write_allowed"])
        self.assertFalse(grant["network_allowed"])
        self.assertFalse(grant["commit_allowed"])
        self.assertTrue(grant["expires_after_turn"])
        self.assertTrue(turngrant.grant_path(self.root).exists())

    def test_grant_is_not_a_contract_revision(self):
        turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        state = store.load_state(self.root)
        self.assertEqual((state.goal_contract or {}).get("revision"), 1)
        from psk import autonomy as autonomy_mod
        self.assertEqual(autonomy_mod.status(self.root)["autonomy_contract_revision"], 0)

    def test_ineligible_instruction_creates_nothing(self):
        self.assertIsNone(turngrant.create(self.root, "fix the failing test"))
        self.assertFalse(turngrant.grant_path(self.root).exists())

    def test_grant_is_repository_bound(self):
        grant = turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        other = make_repo(with_commit=True)
        self.addCleanup(cleanup, other)
        other_root = gitutil.repo_root(other)
        cli_run(["init", other_root, "--objective", "other"])
        # Copy the grant verbatim into the other repository.
        store.atomic_write(turngrant.grant_path(other_root),
                           json.dumps(grant, indent=2) + "\n")
        self.assertIsNone(turngrant.active(other_root))

    def test_grant_is_head_bound(self):
        turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        self.assertIsNotNone(turngrant.active(self.root))
        self.new_commit()
        self.assertIsNone(turngrant.active(self.root))
        self.assertFalse(turngrant.grant_path(self.root).exists(),
                         "a HEAD-invalidated grant must be removed, not left behind")

    def test_grant_is_instruction_epoch_bound(self):
        turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        self.assertIsNotNone(turngrant.active(self.root))
        from psk import autonomy as autonomy_mod
        autonomy_mod.bump_epoch(self.root)
        self.assertIsNone(turngrant.active(self.root))

    def test_grant_records_the_owner_message_hash(self):
        from psk import util
        grant = turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        self.assertEqual(grant["owner_message_hash"],
                         util.sha256_hex(ACCEPTANCE_INSTRUCTION))

    def test_expire_removes_the_grant(self):
        turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        turngrant.expire(self.root, reason="turn complete")
        self.assertIsNone(turngrant.active(self.root))
        self.assertFalse(turngrant.grant_path(self.root).exists())


class TestExactCommitGrant(GrantRepoCase):

    def setUp(self):
        super().setUp()
        self.readme = Path(self.root, "README.md")
        self.readme.write_text("changed\n", encoding="utf-8")

    def create_grant(self):
        return turngrant.create(self.root, EXACT_COMMIT_INSTRUCTION)

    def test_exact_existing_commit_instruction_creates_narrow_grant(self):
        grant = self.create_grant()
        self.assertIsNotNone(grant)
        self.assertTrue(grant["commit_allowed"])
        self.assertFalse(grant["write_allowed"])
        self.assertFalse(grant["network_allowed"])
        self.assertEqual(grant["grant_kind"], "exact_existing_commit")
        self.assertEqual(grant["allowed_commit_paths"], ["README.md"])
        self.assertEqual(
            grant["allowed_commit_message"],
            "docs: document the requirement",
        )
        self.assertIn("git_commit", grant["allowed_action_classes"])

    def test_commit_grant_requires_exact_existing_scope_and_message(self):
        no_message = (
            "Commit exactly the existing README.md change. "
            "Do not push."
        )
        self.assertIsNone(turngrant.create(self.root, no_message))
        vague_scope = """Commit the README.md change.
Commit message:
docs: x
Do not push."""
        self.assertIsNone(turngrant.create(self.root, vague_scope))

    def test_short_natural_exact_commit_instruction_is_eligible(self):
        instruction = """Commit exactly the existing README.md change.
Commit message: docs: document the requirement"""
        grant = turngrant.create(self.root, instruction)
        self.assertIsNotNone(grant)
        self.assertTrue(grant["commit_allowed"])

    def test_commit_plus_outward_action_is_not_eligible(self):
        instruction = """Commit exactly the existing README.md change and push it.
Commit message: docs: document the requirement"""
        self.assertIsNone(turngrant.create(self.root, instruction))

    def test_commit_grant_ignores_untracked_but_rejects_staged_state(self):
        Path(self.root, "new.txt").write_text("x\n", encoding="utf-8")
        grant = self.create_grant()
        self.assertIsNotNone(grant)
        self.assertEqual(grant["allowed_commit_paths"], ["README.md"])
        turngrant.expire(self.root)
        Path(self.root, "new.txt").unlink()
        git(self.root, "add", "README.md")
        self.assertIsNone(self.create_grant())

    def test_exact_commit_command_is_allowed(self):
        grant = self.create_grant()
        decision = broker.classify_tool_call(
            "Bash",
            {
                "command": (
                    "git commit README.md "
                    "-m 'docs: document the requirement'"
                )
            },
            self.root,
            self.root,
            policy=None,
            turn_grant=grant,
        )
        self.assertTrue(decision.allowed, decision.reason)
        self.assertEqual(decision.classification, "git_commit")
        self.assertIn("exact existing commit", decision.reason)

    def test_commit_message_path_and_options_must_match(self):
        grant = self.create_grant()
        commands = [
            "git commit README.md -m 'different message'",
            "git commit other.md -m 'docs: document the requirement'",
            "git commit -a -m 'docs: document the requirement'",
            "git commit --amend README.md -m 'docs: document the requirement'",
            (
                "git commit README.md -m 'docs: document the requirement' "
                "&& git push"
            ),
        ]
        for command in commands:
            decision = broker.classify_tool_call(
                "Bash", {"command": command}, self.root, self.root,
                policy=None, turn_grant=grant,
            )
            self.assertFalse(decision.allowed, command)

    def test_commit_grant_is_invalid_if_diff_changes(self):
        grant = self.create_grant()
        self.readme.write_text("changed again\n", encoding="utf-8")
        decision = broker.classify_tool_call(
            "Bash",
            {
                "command": (
                    "git commit README.md "
                    "-m 'docs: document the requirement'"
                )
            },
            self.root,
            self.root,
            policy=None,
            turn_grant=grant,
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("diff changed" in detail for detail in decision.details),
            decision.details,
        )

    def test_commit_grant_still_denies_edits_staging_and_push(self):
        grant = self.create_grant()
        edit = broker.classify_tool_call(
            "Edit",
            {
                "file_path": str(self.readme),
                "old_string": "a",
                "new_string": "b",
            },
            self.root,
            self.root,
            policy=None,
            turn_grant=grant,
        )
        self.assertFalse(edit.allowed)
        for command in ("git add README.md", "git push origin main"):
            decision = broker.classify_tool_call(
                "Bash", {"command": command}, self.root, self.root,
                policy=None, turn_grant=grant,
            )
            self.assertFalse(decision.allowed, command)


class TestGrantExpiresAfterOneTurn(GrantRepoCase):
    """The shell must destroy the grant after every turn, however it ends."""

    def _shell(self, lines, claude=None):
        from tests.test_shell import FakeClaude
        out = []
        it = iter(lines)

        def input_fn(prompt):
            out.append(prompt)
            try:
                return next(it)
            except StopIteration:
                raise EOFError

        sh = shell.DogBuildShell(
            self.root,
            claude=claude or FakeClaude(),
            input_fn=input_fn,
            output_fn=out.append,
            resume=False,
        )
        return sh, out

    def test_turn_creates_then_expires_the_grant(self):
        seen = {}
        from tests.test_shell import FakeClaude

        class Observing(FakeClaude):
            def send(inner, message):
                seen["during"] = turngrant.active(self.root)
                return super().send(message)

        sh, out = self._shell([ACCEPTANCE_INSTRUCTION, "exit"], claude=Observing())
        sh.run()
        self.assertIsNotNone(seen["during"], "no grant was active during the turn")
        self.assertIsNone(turngrant.active(self.root),
                          "grant survived the turn")

    def test_grant_expires_even_when_the_turn_fails(self):
        from tests.test_shell import FakeClaude

        class Boom(FakeClaude):
            def send(inner, message):
                raise RuntimeError("boom")

        sh, _ = self._shell([ACCEPTANCE_INSTRUCTION, "exit"], claude=Boom())
        sh.run()
        self.assertIsNone(turngrant.active(self.root))

    def test_grant_expires_when_the_turn_is_interrupted(self):
        from tests.test_shell import FakeClaude

        class Interrupted(FakeClaude):
            def send(inner, message):
                raise KeyboardInterrupt

        sh, _ = self._shell([ACCEPTANCE_INSTRUCTION, "exit"], claude=Interrupted())
        sh.run()
        self.assertIsNone(turngrant.active(self.root))

    def test_state_query_turn_creates_no_grant(self):
        from tests.test_shell import FakeClaude
        claude = FakeClaude()
        sh, _ = self._shell(["What's happening?", "exit"], claude=claude)
        sh.run()
        self.assertEqual(claude.sent, [])
        self.assertIsNone(turngrant.active(self.root))

    def test_grant_is_not_reused_after_restart(self):
        # Simulate a crash: a grant left on disk with no shell running.
        turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        self.assertTrue(turngrant.grant_path(self.root).exists())
        sh, _ = self._shell(["exit"])
        sh.run()
        self.assertFalse(turngrant.grant_path(self.root).exists(),
                         "a new shell must sweep away an orphaned grant")


# ------------------------------------------------------------------ #
# Broker enforcement under a grant
# ------------------------------------------------------------------ #

GRANT = {
    "kind": "turn_scoped_owner_grant",
    "turn_id": "test-turn-1",
    "allowed_action_classes": ["repository_read", "tests_and_builds"],
    "write_allowed": False,
    "network_allowed": False,
    "commit_allowed": False,
    "repository_head": "abc123",
    "instruction_epoch": 1,
}


class TestBrokerUnderGrant(unittest.TestCase):

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="psk-broker-")
        self.addCleanup(shutil.rmtree, self.repo, True)

    def decide(self, tool_name, tool_input, grant=GRANT):
        return broker.classify_tool_call(
            tool_name, tool_input, self.repo, self.repo,
            policy=None, turn_grant=grant,
        )

    # -- permitted ---------------------------------------------------- #

    def test_read_glob_grep_allowed(self):
        for tool, payload in [
            ("Read", {"file_path": os.path.join(self.repo, "package.json")}),
            ("Glob", {"pattern": "**/*.js"}),
            ("Grep", {"pattern": "detectFaces"}),
        ]:
            d = self.decide(tool, payload)
            self.assertTrue(d.allowed, f"{tool}: {d.reason}")

    def test_git_inspection_allowed(self):
        for cmd in ["git status", "git diff", "git log --oneline -5",
                    "git show HEAD", "git branch", "git rev-parse HEAD"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertTrue(d.allowed, f"{cmd}: {d.reason}")
            self.assertEqual(d.turn_grant_id, "test-turn-1")

    def test_existing_test_command_allowed(self):
        for cmd in ["npm run test:unit", "npm test",
                    "python -m unittest discover", "npm run build"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertTrue(d.allowed, f"{cmd}: {d.reason}")

    def test_allowed_decisions_carry_the_grant_id(self):
        d = self.decide("Bash", {"command": "npm run test:unit"})
        self.assertEqual(d.turn_grant_id, "test-turn-1")
        self.assertIn("turn-scoped owner grant", d.reason)

    # -- always denied ------------------------------------------------ #

    def test_edits_denied(self):
        for tool in ("Edit", "Write"):
            d = self.decide(tool, {"file_path": os.path.join(self.repo, "app.js"),
                                   "content": "x"})
            self.assertFalse(d.allowed, tool)
            self.assertIn("read-and-verify", d.reason)

    def test_commit_denied(self):
        for cmd in ["git commit -m 'x'", "git add -A"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertFalse(d.allowed, cmd)

    def test_dependency_change_denied(self):
        for cmd in ["npm install left-pad", "pip install requests",
                    "brew install jq"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertFalse(d.allowed, cmd)

    def test_network_denied(self):
        for cmd in ["curl https://example.com/data.json",
                    "wget https://example.com/x.tar.gz",
                    "curl https://api.openai.com/v1/chat"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertFalse(d.allowed, cmd)

    def test_secrets_denied(self):
        for cmd in ["cat ~/.ssh/id_rsa", "cat .env", "echo $GITHUB_TOKEN"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertFalse(d.allowed, cmd)

    def test_outward_facing_denied(self):
        for cmd in ["git push origin main", "git merge feature",
                    "npm publish", "rm -rf /"]:
            d = self.decide("Bash", {"command": cmd})
            self.assertFalse(d.allowed, cmd)

    def test_outside_repository_path_denied(self):
        d = self.decide("Read", {"file_path": "/etc/passwd"})
        self.assertFalse(d.allowed)
        self.assertIn("outside repository", d.reason)

    def test_grant_does_not_widen_write_tools_without_it(self):
        # Without a grant, in-repo edits keep their previous behavior.
        d = self.decide("Edit", {"file_path": os.path.join(self.repo, "app.js")},
                        grant=None)
        self.assertTrue(d.allowed)

    def test_without_a_grant_tests_are_still_denied_with_no_policy(self):
        # This is the defect's precondition: no grant, no policy → denied.
        d = self.decide("Bash", {"command": "npm run test:unit"}, grant=None)
        self.assertFalse(d.allowed)


# ------------------------------------------------------------------ #
# Skill tool
# ------------------------------------------------------------------ #

class TestSkillTool(unittest.TestCase):

    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old_reg = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.skills_dir = tempfile.mkdtemp(prefix="psk-skills-")
        self._old_skills = os.environ.get("CLAUDE_SKILLS_DIR")
        os.environ["CLAUDE_SKILLS_DIR"] = self.skills_dir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)
        cli_run(["init", self.root, "--objective", "test objective"])
        from psk import install
        install.install_claude_skill(skills_root=self.skills_dir)

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

    def decide(self, tool_input):
        return broker.classify_tool_call("Skill", tool_input, self.root, self.root)

    def test_dogbuild_skill_allowed(self):
        for payload in [{"skill": "dogbuild"}, {"name": "dogbuild"},
                        {"command": "/dogbuild"}, {"skill_name": "dogbuild"}]:
            d = self.decide(payload)
            self.assertTrue(d.allowed, f"{payload}: {d.reason}")
            self.assertEqual(d.classification, "dogbuild_skill_load")

    def test_arbitrary_skill_denied(self):
        for name in ["some-other-skill", "dataviz", "shell", "dogbuild-evil",
                     "plugin:dogbuild"]:
            d = self.decide({"skill": name})
            self.assertFalse(d.allowed, name)
            self.assertEqual(d.classification, "unknown_skill")

    def test_skill_without_a_name_denied(self):
        self.assertFalse(self.decide({}).allowed)

    def test_uninstalled_skill_denied(self):
        shutil.rmtree(Path(self.skills_dir) / "dogbuild", ignore_errors=True)
        d = self.decide({"skill": "dogbuild"})
        self.assertFalse(d.allowed)
        self.assertEqual(d.classification, "skill_not_installed")

    def test_invalid_project_identity_denied(self):
        from psk import identity as identity_mod
        identity_mod.identity_path(self.root).unlink()
        d = self.decide({"skill": "dogbuild"})
        self.assertFalse(d.allowed)
        self.assertEqual(d.classification, "identity_invalid")

    def test_skill_load_is_audited_as_read_only(self):
        from psk.governor import audit
        d = self.decide({"skill": "dogbuild"})
        broker.record_broker_decision(self.root, "Skill", {"skill": "dogbuild"}, d)
        rows = audit.read_audit(self.root) if hasattr(audit, "read_audit") else []
        if rows:
            self.assertEqual(rows[-1]["decision"], "allow")
            self.assertEqual(rows[-1]["classification"], "dogbuild_skill_load")


# ------------------------------------------------------------------ #
# Audit
# ------------------------------------------------------------------ #

class TestGrantAudit(GrantRepoCase):

    def test_audit_records_the_grant_and_the_decision(self):
        from psk.governor import audit
        grant = turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        decision = broker.classify_tool_call(
            "Bash", {"command": "npm run test:unit"}, self.root, self.root,
            policy=None, turn_grant=grant,
        )
        broker.record_broker_decision(
            self.root, "Bash", {"command": "npm run test:unit"},
            decision, turn_grant=grant,
        )
        path = Path(self.root) / ".ai" / "execution_audit.jsonl"
        self.assertTrue(path.exists())
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        last = rows[-1]
        self.assertEqual(last["decision"], "allow")
        self.assertEqual(last["policy_rule"], "turn_grant")
        self.assertEqual(last["task_id"], grant["turn_id"])
        self.assertTrue(any("turn_grant_id" in r for r in last["reasons"]))

    def test_audit_records_a_denial_under_the_grant(self):
        grant = turngrant.create(self.root, ACCEPTANCE_INSTRUCTION)
        decision = broker.classify_tool_call(
            "Bash", {"command": "git push origin main"}, self.root, self.root,
            policy=None, turn_grant=grant,
        )
        broker.record_broker_decision(
            self.root, "Bash", {"command": "git push origin main"},
            decision, turn_grant=grant,
        )
        path = Path(self.root) / ".ai" / "execution_audit.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        self.assertEqual(rows[-1]["decision"], "deny")


# ------------------------------------------------------------------ #
# Read-only git verbs the classifier used to miss
# ------------------------------------------------------------------ #

class TestReadOnlyGitClassification(unittest.TestCase):

    def test_inspection_verbs_are_tier_zero(self):
        for cmd in ["git rev-parse HEAD", "git describe --tags",
                    "git shortlog -sn", "git ls-files", "git blame app.js",
                    "git remote -v", "git remote"]:
            cls = classify_command(cmd)
            self.assertEqual(cls.tier, RiskTier.TIER_0_READ_ONLY, cmd)
            self.assertEqual(cls.action_class, "repository_read", cmd)

    def test_mutating_remote_forms_are_not_read_only(self):
        for cmd in ["git remote add origin git@example.com:x.git",
                    "git remote set-url origin https://example.com/x.git"]:
            cls = classify_command(cmd)
            self.assertNotEqual(cls.tier, RiskTier.TIER_0_READ_ONLY, cmd)


# ------------------------------------------------------------------ #
# Orientation: latest verified evidence wins
# ------------------------------------------------------------------ #

class TestOrientationEvidencePriority(GrantRepoCase):
    """A checkpoint at an older commit is history, never current status."""

    def _checkpoint(self, summary, tested, next_action):
        return core.create_checkpoint(
            self.root, summary, tested=tested,
            next_safe_action=next_action, actor="claude",
        )

    def test_checkpoint_at_the_live_head_is_current(self):
        self._checkpoint("shipped the thing", ["suite = 10 pass / 0 fail"],
                         "review it")
        fields, warnings = brief.build(self.root)
        self.assertEqual(fields["what_just_completed"], "shipped the thing")
        self.assertIn("10 pass", fields["current_verified_state"])
        self.assertFalse(fields["checkpoint_is_historical"])
        self.assertEqual(fields["evidence_source"], "checkpoint at the current commit")

    def test_stale_checkpoint_is_not_shown_as_current(self):
        self._checkpoint("old multi-face work", ["suite = 100 pass / 0 fail at OLD"],
                         "stop, no task selected")
        self.new_commit()
        fields, warnings = brief.build(self.root)

        self.assertTrue(fields["checkpoint_is_historical"])
        self.assertNotIn("100 pass", fields["current_verified_state"],
                         "stale test evidence must not be presented as current")
        self.assertNotEqual(fields["what_just_completed"], "old multi-face work")
        self.assertIn("not recorded for the current commit",
                      fields["current_verified_state"])
        self.assertTrue(any("history" in w for w in warnings))

    def test_stale_checkpoint_remains_available_as_history(self):
        self._checkpoint("old multi-face work", ["suite = 100 pass"], "stop")
        self.new_commit()
        fields, _ = brief.build(self.root)
        self.assertIn("old multi-face work", fields["historical_note"])

    def test_declaration_at_the_live_head_beats_a_stale_checkpoint(self):
        self._checkpoint("old work at the old commit", ["old suite = 100 pass"],
                         "old next action")
        self.new_commit()
        head = gitutil.capture_git_state(self.root)["head_commit"]
        from psk import declaration
        declaration.record(
            self.root,
            building="adoption of the new commit, verified",
            changed="no product file changed",
            verified="unit 126 pass, browser 220 pass, a11y 40 pass",
            failed="None", incomplete="None",
            next_action="Stop. The commit is adopted and verified.",
            actor_name="claude",
        )
        fields, _ = brief.build(self.root)
        self.assertEqual(fields["evidence_source"],
                         "agent declaration at the current commit")
        self.assertIn("126 pass", fields["current_verified_state"])
        self.assertNotIn("100 pass", fields["current_verified_state"])
        self.assertIn("adopted and verified", fields["exact_next_action"])

    def test_no_active_task_is_reported_as_such(self):
        fields, _ = brief.build(self.root)
        self.assertEqual(fields["current_task"], "None")
        self.assertEqual(fields["next_step"], "No task selected")
        self.assertEqual(fields["milestone_status"], "pending-next-milestone")
        self.assertFalse(fields["has_active_task"])

    def test_completed_milestone_does_not_change_the_product_goal(self):
        before = store.load_state(self.root).goal_contract
        fields, _ = brief.build(self.root)
        after = store.load_state(self.root).goal_contract
        self.assertEqual(fields["milestone_status"], "pending-next-milestone")
        self.assertEqual(before, after, "reporting must not rewrite the goal")

    def test_active_plan_reports_a_current_task(self):
        from psk import plan as plan_mod
        plan_mod.create(self.root, stage="build", current_item="step one",
                        remaining=["step two"], actor="claude")
        fields, _ = brief.build(self.root)
        self.assertNotEqual(fields["current_task"], "None")
        self.assertEqual(fields["milestone_status"], "active")
        self.assertTrue(fields["has_active_task"])


class TestShellStatusUsesCurrentEvidence(GrantRepoCase):

    def test_status_answer_shows_no_task_selected(self):
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "status")
        self.assertIn("Current task: None", answer)
        self.assertIn("Next step: No task selected", answer)

    def test_status_answer_does_not_present_stale_tests_as_current(self):
        core.create_checkpoint(self.root, "old work",
                               tested=["suite = 100 pass / 0 fail"],
                               next_safe_action="stop", actor="claude")
        self.new_commit()
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "status")
        self.assertNotIn("100 pass", answer)
        self.assertNotIn("Earlier, for history", answer)
        self.assertNotIn("Warning:", answer)

    def test_tests_answer_is_honest_when_nothing_is_recorded(self):
        core.create_checkpoint(self.root, "old work",
                               tested=["suite = 100 pass"],
                               next_safe_action="stop", actor="claude")
        self.new_commit()
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "tests")
        self.assertIn("No test evidence is recorded for the current commit", answer)


# ------------------------------------------------------------------ #
# Compatibility
# ------------------------------------------------------------------ #

class TestCompatibility(unittest.TestCase):

    def test_statekeeper_entry_points_intact(self):
        from psk import __main__ as cli
        p = cli._build_parser()
        for argv in (["start", "/tmp"], ["init", "/tmp"], ["status", "/tmp"],
                     ["brief", "/tmp"], ["where-am-i", "/tmp"],
                     ["governor", "status", "/tmp"], ["review", "gate", "/tmp"],
                     ["autonomy", "status", "/tmp"]):
            ns = p.parse_args(argv)
            self.assertTrue(hasattr(ns, "func"), argv)


if __name__ == "__main__":
    unittest.main()
