"""Tests for the persistent `dogBuild>` shell."""

import json
import os
import shutil
import tempfile
import unittest

from psk import gitutil, registry, shell
from tests._helpers import cleanup, make_repo, import_min_genesis
from tests.test_start import run as cli_run


class FakeClaude:
    """Stand-in for ClaudeRunner — records what DogBuild would have sent."""

    def __init__(self, reply="ok", available=True):
        self.reply = reply
        self.sent = []
        self.executable = "/fake/claude" if available else None
        self.session_id = "fake-session"
        self.turns = 0

    def send(self, message):
        self.sent.append(message)
        self.turns += 1
        return True, self.reply


class ShellRepoCase(unittest.TestCase):
    """Base: a real git repo with DogBuild state."""

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

    def make_shell(self, claude=None, lines=None):
        out = []
        it = iter(lines or [])

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


# ------------------------------------------------------------------ #
# The prompt itself
# ------------------------------------------------------------------ #

class TestPrompt(unittest.TestCase):

    def test_prompt_capitalization_is_exact(self):
        self.assertEqual(shell.PROMPT, "dogBuild>")
        self.assertEqual(shell.PROMPT_STRING, "dogBuild> ")


class TestPromptLoop(ShellRepoCase):

    def test_prompt_is_shown_and_returns_after_each_turn(self):
        sh, out = self.make_shell(lines=["status", "help", "exit"])
        code = sh.run()
        self.assertEqual(code, 0)
        prompts = [o for o in out if o == shell.PROMPT_STRING]
        # One prompt per input line, including the one that exited.
        self.assertEqual(len(prompts), 3)

    def test_eof_exits_cleanly(self):
        sh, out = self.make_shell(lines=[])
        self.assertEqual(sh.run(), 0)
        self.assertIn("Leaving DogBuild", "\n".join(out))

    def test_blank_line_is_ignored(self):
        sh, _ = self.make_shell(lines=["", "   "])
        self.assertEqual(sh.run(), 0)

    def test_exit_words(self):
        for word in ("exit", "quit", "bye", "EXIT"):
            sh, _ = self.make_shell(lines=[word, "should-not-run"])
            claude = sh.claude
            sh.run()
            self.assertEqual(claude.sent, [], f"{word} did not exit")

    def test_a_failing_turn_does_not_kill_the_session(self):
        class Boom(FakeClaude):
            def send(self, message):
                raise RuntimeError("boom")

        sh, out = self.make_shell(claude=Boom(), lines=["do some work", "exit"])
        sh.run()
        self.assertIn("boom", "\n".join(out))
        self.assertIn("Leaving DogBuild", "\n".join(out))


# ------------------------------------------------------------------ #
# Banner
# ------------------------------------------------------------------ #

class TestBanner(ShellRepoCase):

    def test_banner_fields(self):
        fields, warnings = shell.load_live(self.root)
        banner = shell.render_banner(fields, warnings)
        self.assertIn("DogBuild", banner)
        for label in ("Project:", "Stage:", "Current milestone:",
                      "Last verified:", "Human needed:"):
            self.assertIn(label, banner)

    def test_human_needed_is_yes_or_no(self):
        fields, warnings = shell.load_live(self.root)
        banner = shell.render_banner(fields, warnings)
        line = [l for l in banner.splitlines() if "Human needed:" in l][0]
        self.assertTrue("Yes" in line or "No" in line, line)

    def test_banner_hides_historical_warnings_by_default(self):
        fields, _ = shell.load_live(self.root)
        banner = shell.render_banner(
            fields,
            ["The latest agent declaration references an older HEAD."],
        )
        self.assertNotIn("Warning:", banner)

    def test_banner_keeps_actionable_warnings(self):
        fields, _ = shell.load_live(self.root)
        banner = shell.render_banner(fields, ["could not read DogBuild state"])
        self.assertIn("Warning: could not read DogBuild state", banner)

    def test_banner_shows_no_active_milestone_plainly(self):
        fields, _ = shell.load_live(self.root)
        fields["milestone_status"] = "pending-next-milestone"
        banner = shell.render_banner(fields, [])
        self.assertIn("Current milestone:  None — no task selected", banner)

    def test_stage_is_derived_from_live_state(self):
        fields, _ = shell.load_live(self.root)
        self.assertIn(fields["product"], shell.derive_stage(fields))
        fields["plan_current_task"] = "task-1"
        self.assertIn("delivery", shell.derive_stage(fields))
        fields["plan_current_task"] = None
        self.assertIn("maintenance", shell.derive_stage(fields))


# ------------------------------------------------------------------ #
# State queries — must never call Claude
# ------------------------------------------------------------------ #

class TestStateQueryClassification(unittest.TestCase):

    def test_status_questions(self):
        for q in ["What's happening?", "whats happening", "What is happening?",
                  "where are we", "Where am I?", "status", "what's the status",
                  "How is it going?"]:
            self.assertEqual(shell.classify_state_query(q), "status", q)

    def test_next_questions(self):
        for q in ["what's next?", "What is the next step?", "next",
                  "what should we do next"]:
            self.assertEqual(shell.classify_state_query(q), "next", q)

    def test_test_questions(self):
        for q in ["did the tests pass?", "tests", "do tests pass",
                  "what are the test results"]:
            self.assertEqual(shell.classify_state_query(q), "tests", q)

    def test_remaining_questions(self):
        for q in ["what's left?", "what remains", "what is outstanding"]:
            self.assertEqual(shell.classify_state_query(q), "remaining", q)

    def test_human_questions(self):
        for q in ["is a human decision needed?", "do you need me",
                  "human approval"]:
            self.assertEqual(shell.classify_state_query(q), "human", q)

    def test_real_work_is_not_a_state_query(self):
        for q in [
            "Inspect the current repository and tell me the smallest safe next action.",
            "fix the failing test",
            "add a --json flag to status",
            "what's next — and implement it",
            "run the unit tests",
            "refactor the parser",
        ]:
            self.assertIsNone(shell.classify_state_query(q), q)

    def test_long_input_is_not_a_state_query(self):
        self.assertIsNone(shell.classify_state_query("what's happening " * 20))


class TestStateQueryAnswers(ShellRepoCase):

    def test_state_query_does_not_invoke_claude(self):
        claude = FakeClaude()
        sh, out = self.make_shell(claude=claude, lines=["What's happening?", "exit"])
        sh.run()
        self.assertEqual(claude.sent, [], "Claude was invoked for a state query")
        text = "\n".join(out)
        self.assertIn("Milestone:", text)
        self.assertIn("Next step:", text)

    def test_answer_is_plain_english_not_jargon(self):
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "status")
        for jargon in ("goal_contract", "exact_next_action", "STOP_VETO", "{"):
            self.assertNotIn(jargon, answer)

    def test_tests_answer_is_honest_about_freshness(self):
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "tests")
        self.assertIn("last verified record", answer)

    def test_human_answer(self):
        fields, warnings = shell.load_live(self.root)
        answer = shell.answer_state_query(fields, warnings, "human")
        self.assertTrue(answer.startswith("Yes") or answer.startswith("No"))


# ------------------------------------------------------------------ #
# Built-in commands
# ------------------------------------------------------------------ #

class TestBuiltins(ShellRepoCase):

    def _say(self, line):
        claude = FakeClaude()
        sh, out = self.make_shell(claude=claude, lines=[line, "exit"])
        sh.run()
        return "\n".join(out), claude

    def test_help_lists_commands(self):
        text, claude = self._say("help")
        for cmd in ("help", "status", "next", "plan", "parked", "review",
                    "refresh", "mode", "clear", "exit"):
            self.assertIn(cmd, text)
        self.assertEqual(claude.sent, [])

    def test_every_builtin_runs_without_claude(self):
        for cmd in shell.DogBuildShell.BUILTINS:
            text, claude = self._say(cmd)
            self.assertEqual(claude.sent, [], f"`{cmd}` invoked Claude")

    def test_review_is_honest_about_manual_chatgpt_transport(self):
        text, _ = self._say("review")
        self.assertIn("ChatGPT", text)
        self.assertIn("manual", text.lower())
        self.assertIn("dogbuild review request", text)

    def test_mode_names_the_layers(self):
        text, _ = self._say("mode")
        self.assertIn("DogBuild", text)
        self.assertIn("Claude Code", text)
        self.assertIn("ChatGPT", text)

    def test_parked_reports_when_empty(self):
        text, _ = self._say("parked")
        self.assertIn("parked", text.lower())


# ------------------------------------------------------------------ #
# Claude-backed turns
# ------------------------------------------------------------------ #

class TestClaudeTurns(ShellRepoCase):

    def test_non_state_input_goes_to_claude_and_returns_to_prompt(self):
        claude = FakeClaude(reply="I inspected the repo. Nothing changed.")
        sh, out = self.make_shell(
            claude=claude,
            lines=["Inspect the repository and tell me the smallest safe next action.",
                   "exit"],
        )
        sh.run()
        self.assertEqual(len(claude.sent), 1)
        text = "\n".join(out)
        self.assertIn("I inspected the repo.", text)
        self.assertEqual(out.count(shell.PROMPT_STRING), 2)

    def test_every_claude_turn_gets_fresh_authoritative_context(self):
        claude = FakeClaude()
        sh, _ = self.make_shell(
            claude=claude,
            lines=["Inspect Git status and make no changes.", "exit"],
        )
        sh.run()
        self.assertEqual(len(claude.sent), 1)
        message = claude.sent[0]
        fields, _ = shell.load_live(self.root)
        self.assertIn("[DogBuild live context — authoritative for this turn]", message)
        self.assertIn(fields["current_verified_state"], message)
        self.assertIn("[Owner request]", message)
        self.assertIn("Inspect Git status and make no changes.", message)
        self.assertIn("ignore the older claim", message)

    def test_session_pointer_is_written_after_a_turn(self):
        claude = FakeClaude()
        sh, _ = self.make_shell(claude=claude, lines=["do the work", "exit"])
        sh.run()
        saved = shell.load_session(self.root)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["session_id"], "fake-session")

    def test_pauses_instead_of_dispatching_when_a_human_is_needed(self):
        claude = FakeClaude()
        sh, out = self.make_shell(claude=claude, lines=["do the work", "exit"])
        real_refresh = sh.refresh

        def blocked():
            real_refresh()
            sh.fields["human_decision_needed"] = "yes"
            sh.fields["human_decision_reason"] = "a reviewer VETO blocks the action"

        sh.refresh = blocked
        sh.run()
        text = "\n".join(out)
        self.assertEqual(claude.sent, [], "work was dispatched while blocked")
        self.assertIn("paused", text.lower())
        self.assertIn("ChatGPT", text)
        self.assertIn("No work was sent to Claude", text)


# ------------------------------------------------------------------ #
# ClaudeRunner argument construction (no shell, no dangerous flags)
# ------------------------------------------------------------------ #

class TestClaudeRunner(unittest.TestCase):

    def _runner(self, **kw):
        return shell.ClaudeRunner("/tmp", executable="/bin/claude", **kw)

    def test_first_turn_starts_a_session(self):
        r = self._runner(system_prompt="ctx")
        args = r.build_args("hello")
        self.assertEqual(args[0], "/bin/claude")
        self.assertIn("--print", args)
        self.assertIn("--session-id", args)
        self.assertIn(r.session_id, args)
        self.assertIn("--append-system-prompt", args)
        self.assertEqual(args[-1], "hello")

    def test_later_turns_resume_the_same_session(self):
        r = self._runner()
        r.turns = 1
        args = r.build_args("again")
        self.assertIn("--resume", args)
        self.assertIn(r.session_id, args)
        self.assertNotIn("--session-id", args)

    def test_recovered_session_resumes_immediately(self):
        r = self._runner(session_id="prior-id", resume=True)
        self.assertIn("--resume", r.build_args("hi"))

    def test_permission_mode_is_passed_through(self):
        r = self._runner(permission_mode="plan")
        args = r.build_args("hi")
        self.assertEqual(args[args.index("--permission-mode") + 1], "plan")

    def test_no_dangerous_flags(self):
        args = self._runner().build_args("hi")
        for flag in ("--dangerously-skip-permissions",
                     "--allow-dangerously-skip-permissions"):
            self.assertNotIn(flag, args)

    def test_args_are_a_list_of_strings(self):
        args = self._runner().build_args("a prompt with spaces & $(danger)")
        self.assertIsInstance(args, list)
        for a in args:
            self.assertIsInstance(a, str)
        self.assertEqual(args[-1], "a prompt with spaces & $(danger)")

    def test_no_shell_true_in_source(self):
        from pathlib import Path
        src = Path(shell.__file__).with_suffix(".py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", src)

    def test_missing_claude_is_reported_not_raised(self):
        r = shell.ClaudeRunner("/tmp", executable="")
        r.executable = None
        ok, text = r.send("hi")
        self.assertFalse(ok)
        self.assertIn("not installed", text)

    def test_nonzero_exit_is_reported(self):
        calls = []

        def failing(args):
            calls.append(args)
            return 1, "", "something broke"

        r = self._runner(runner=failing)
        ok, text = r.send("hi")
        self.assertFalse(ok)
        self.assertIn("something broke", text)
        self.assertEqual(len(calls), 1)

    def test_stale_recovered_session_falls_back_to_a_fresh_one(self):
        seen = []

        def runner(args):
            seen.append(args)
            if len(seen) == 1:
                return 1, "", "No conversation found with session ID: prior-id"
            return 0, "recovered fine", ""

        r = self._runner(session_id="prior-id", resume=True, runner=runner)
        ok, text = r.send("hi")
        self.assertTrue(ok)
        self.assertEqual(text, "recovered fine")
        self.assertIn("--session-id", seen[1])
        self.assertNotEqual(r.session_id, "prior-id")


# ------------------------------------------------------------------ #
# Session recovery
# ------------------------------------------------------------------ #

class TestSessionRecovery(ShellRepoCase):

    def test_save_then_load_roundtrip(self):
        shell.save_session(self.root, "abc-123", 4)
        saved = shell.load_session(self.root)
        self.assertEqual(saved["session_id"], "abc-123")
        self.assertEqual(saved["turns"], 4)

    def test_missing_pointer_is_none(self):
        self.assertIsNone(shell.load_session(self.root))

    def test_corrupt_pointer_is_ignored(self):
        path = shell.session_path(self.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        self.assertIsNone(shell.load_session(self.root))

    def test_shell_recovers_a_prior_session(self):
        shell.save_session(self.root, "prior-abc", 2)
        sh = shell.DogBuildShell(self.root, input_fn=lambda p: "exit",
                                 output_fn=lambda s: None, resume=True)
        self.assertTrue(sh.recovered)
        self.assertEqual(sh.claude.session_id, "prior-abc")

    def test_new_session_ignores_the_pointer(self):
        shell.save_session(self.root, "prior-abc", 2)
        sh = shell.DogBuildShell(self.root, input_fn=lambda p: "exit",
                                 output_fn=lambda s: None, resume=False)
        self.assertFalse(sh.recovered)
        self.assertNotEqual(sh.claude.session_id, "prior-abc")


if __name__ == "__main__":
    unittest.main()
