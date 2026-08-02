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
# Delegated-response marker
# ------------------------------------------------------------------ #

class TestDelegatedResponseMarker(ShellRepoCase):
    """Founder evidence: the start of a delegated answer was unfindable.

    In a crowded terminal a delegated response can arrive after pages of tool
    output, so it needs a visible start marker. Built-in and state answers sit
    directly under the prompt and must stay unmarked.
    """

    def test_delegated_response_is_preceded_by_the_marker(self):
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        self.assertIn(shell.DELEGATED_RESPONSE_HEADER, out)

    def test_marker_comes_immediately_before_the_response(self):
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        index = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(out[index + 1], sh.claude.reply)

    def test_marker_identifies_the_product(self):
        self.assertIn("dogBuild", shell.DELEGATED_RESPONSE_HEADER)

    def test_both_boundaries_are_labelled_in_plain_text(self):
        """Clarity must not depend on colour, styling, or glyph rendering."""
        self.assertIn("dogBuild response", shell.DELEGATED_RESPONSE_HEADER)
        self.assertIn("end of dogBuild response", shell.DELEGATED_RESPONSE_FOOTER)
        for rule in (shell.DELEGATED_RESPONSE_HEADER,
                     shell.DELEGATED_RESPONSE_FOOTER):
            self.assertNotIn("\x1b", rule, "boundary must carry no escape codes")

    def test_a_delegated_turn_emits_no_ansi_escape_codes(self):
        """Non-colour terminals must lose nothing.

        The boundaries carry their meaning as words, so no styling is emitted
        at all. That also keeps piped and logged output free of escape
        sequences. `clear` deliberately emits a screen-wipe sequence, but that
        is a screen control rather than styling and no delegated turn uses it.
        """
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        for line in out:
            self.assertNotIn("\x1b", line, f"escape code in: {line!r}")

    def test_boundaries_are_findable_by_plain_substring_search(self):
        """What the owner would grep for in a captured terminal log."""
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        transcript = "\n".join(out)
        self.assertIn("dogBuild response", transcript)
        self.assertIn("end of dogBuild response", transcript)

    def test_exactly_one_working_indicator_per_delegated_turn(self):
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        self.assertEqual(out.count(shell.WORKING_INDICATOR), 1)

    def test_one_indicator_per_turn_across_several_turns(self):
        """Exactly one per delegated turn — not one per session, not two."""
        sh, out = self.make_shell(lines=["do some work", "do more work", "exit"])
        sh.run()
        self.assertEqual(out.count(shell.WORKING_INDICATOR), 2)

    def test_one_indicator_on_a_failed_turn(self):
        class Failing(FakeClaude):
            def send(self, message):
                return False, "Claude Code exited with an error"

        sh, out = self.make_shell(claude=Failing(), lines=["do some work", "exit"])
        sh.run()
        self.assertEqual(out.count(shell.WORKING_INDICATOR), 1)

    def test_one_indicator_on_an_interrupted_turn(self):
        class Interrupted(FakeClaude):
            def send(self, message):
                raise KeyboardInterrupt

        sh, out = self.make_shell(claude=Interrupted(),
                                  lines=["do some work", "exit"])
        sh.run()
        self.assertEqual(out.count(shell.WORKING_INDICATOR), 1)

    def test_no_working_indicator_without_delegation(self):
        sh, out = self.make_shell(lines=["status", "what's happening?", "exit"])
        sh.run()
        self.assertEqual(out.count(shell.WORKING_INDICATOR), 0)

    def test_response_is_closed_by_a_matching_rule(self):
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        index = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(out[index + 2], shell.DELEGATED_RESPONSE_FOOTER)
        self.assertEqual(len(shell.DELEGATED_RESPONSE_FOOTER),
                         len(shell.DELEGATED_RESPONSE_HEADER))

    def test_a_blank_line_separates_the_working_indicator_from_the_response(self):
        """Requirement 2: the indicator must not run into the response."""
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        index = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(out[index - 1], "")
        # The line above the blank is the working indicator, not the response.
        self.assertIn("working", out[index - 2])

    def test_a_blank_line_separates_the_response_from_the_next_prompt(self):
        """Requirement 3: the next prompt must not abut the closing rule."""
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        footer = out.index(shell.DELEGATED_RESPONSE_FOOTER)
        self.assertEqual(out[footer + 1], "")
        self.assertEqual(out[footer + 2], shell.PROMPT_STRING)

    def test_nothing_but_the_response_sits_inside_the_boundaries(self):
        """No indicator, authorization notice, or audit line may leak inside.

        The bracketed region is the delegated answer and nothing else, so the
        owner can read or copy it without picking DogBuild's own bookkeeping
        out of the middle.
        """
        sh, out = self.make_shell(lines=["do some work", "exit"])
        sh.run()
        header = out.index(shell.DELEGATED_RESPONSE_HEADER)
        footer = out.index(shell.DELEGATED_RESPONSE_FOOTER)
        self.assertEqual(out[header + 1:footer], [sh.claude.reply])
        self.assertNotIn(shell.WORKING_INDICATOR, out[header:footer + 1])

    def test_a_failed_delegated_turn_is_bracketed(self):
        """An error is an outcome too, and needs the same boundaries."""
        class Failing(FakeClaude):
            def send(self, message):
                return False, "Claude Code exited with an error"

        sh, out = self.make_shell(claude=Failing(), lines=["do some work", "exit"])
        sh.run()
        header = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(out[header + 1], "Claude Code exited with an error")
        self.assertEqual(out[header + 2], shell.DELEGATED_RESPONSE_FOOTER)

    def test_an_interrupted_turn_is_bracketed(self):
        class Interrupted(FakeClaude):
            def send(self, message):
                raise KeyboardInterrupt

        sh, out = self.make_shell(claude=Interrupted(),
                                  lines=["do some work", "exit"])
        sh.run()
        header = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertIn("interrupted", out[header + 1])
        self.assertEqual(out[header + 2], shell.DELEGATED_RESPONSE_FOOTER)

    def test_a_response_containing_a_rule_does_not_confuse_the_boundaries(self):
        """The owner must still find the real end of a response.

        A delegated answer can legitimately contain a horizontal rule of its
        own, so the closing boundary has to remain the last line, not the
        first dashed line encountered.
        """
        class Ruled(FakeClaude):
            def send(self, message):
                return True, "before\n" + "-" * 60 + "\nafter"

        sh, out = self.make_shell(claude=Ruled(), lines=["do some work", "exit"])
        sh.run()
        header = out.index(shell.DELEGATED_RESPONSE_HEADER)
        footer = out.index(shell.DELEGATED_RESPONSE_FOOTER)
        self.assertLess(header, footer)
        body = out[header + 1:footer]
        self.assertIn("before", "\n".join(body))
        self.assertIn("after", "\n".join(body))
        self.assertNotIn(shell.DELEGATED_RESPONSE_FOOTER, body)

    def test_the_prompt_always_returns_after_a_blank_line(self):
        """Whatever the turn did, `dogBuild>` comes back on a fresh line.

        Delegated, built-in and state answers take different paths out of
        handle(), so prompt placement is asserted for each rather than for the
        delegated path alone.
        """
        for line in ("do some work", "status", "what's happening?"):
            sh, out = self.make_shell(lines=[line, "exit"])
            sh.run()
            prompts = [i for i, o in enumerate(out) if o == shell.PROMPT_STRING]
            self.assertGreaterEqual(len(prompts), 2, line)
            self.assertEqual(out[prompts[1] - 1], "",
                             f"{line}: prompt did not return on a fresh line")

    def test_the_prompt_returns_cleanly_after_a_failed_turn(self):
        class Failing(FakeClaude):
            def send(self, message):
                return False, "Claude Code exited with an error"

        sh, out = self.make_shell(claude=Failing(), lines=["do some work", "exit"])
        sh.run()
        prompts = [i for i, o in enumerate(out) if o == shell.PROMPT_STRING]
        self.assertEqual(out[prompts[1] - 1], "")
        self.assertEqual(out[prompts[1] - 2], shell.DELEGATED_RESPONSE_FOOTER)

    def test_ordinary_content_is_returned_byte_for_byte(self):
        """Only impostor lines may be touched; everything else is untouched."""
        for text in ("ok", "a\nb\nc", "-" * 60, "── not a real boundary",
                     "  indented\n\nblank line above", "trailing spaces   "):
            self.assertEqual(shell.escape_boundary_lines(text), text, text)

    def test_a_quoted_header_line_is_visibly_prefixed(self):
        quoted = f"before\n{shell.DELEGATED_RESPONSE_HEADER}\nafter"
        escaped = shell.escape_boundary_lines(quoted).splitlines()
        self.assertEqual(escaped[0], "before")
        self.assertEqual(escaped[1],
                         shell.QUOTED_LINE_PREFIX + shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(escaped[2], "after")

    def test_a_quoted_footer_line_is_visibly_prefixed(self):
        quoted = f"before\n{shell.DELEGATED_RESPONSE_FOOTER}\nafter"
        escaped = shell.escape_boundary_lines(quoted).splitlines()
        self.assertEqual(escaped[1],
                         shell.QUOTED_LINE_PREFIX + shell.DELEGATED_RESPONSE_FOOTER)

    def test_padding_variants_are_also_escaped(self):
        """A rule of a different width still reads as a boundary to the eye."""
        for line in (f"── {shell.DELEGATED_RESPONSE_LABEL} ───",
                     f"── {shell.DELEGATED_RESPONSE_END_LABEL} ─────────"):
            escaped = shell.escape_boundary_lines(line)
            self.assertTrue(escaped.startswith(shell.QUOTED_LINE_PREFIX), line)

    def test_the_escape_prefix_is_plain_text(self):
        self.assertNotIn("\x1b", shell.QUOTED_LINE_PREFIX)
        self.assertTrue(shell.QUOTED_LINE_PREFIX.strip())

    def test_escaping_is_idempotent_in_effect(self):
        """An already-prefixed line is no longer boundary-shaped."""
        once = shell.escape_boundary_lines(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(shell.escape_boundary_lines(once), once)

    def test_a_response_quoting_both_boundaries_is_still_unambiguous(self):
        """Owner-review case: both rules appear as standalone response lines.

        Asserted against the rendered transcript rather than the list of write
        calls, because the terminal shows lines: a multi-line response is one
        write but many lines, and it is the lines the owner scans.

        Against the pre-fix code this fails. The emitted boundaries were the
        same fixed strings the response quotes, so each appeared twice in the
        transcript and neither the start nor the end of the answer could be
        located.
        """
        quoted = "\n".join([
            "intro",
            shell.DELEGATED_RESPONSE_HEADER,
            "middle",
            shell.DELEGATED_RESPONSE_FOOTER,
            "outro",
        ])

        class Quoting(FakeClaude):
            def send(self, message):
                return True, quoted

        sh, out = self.make_shell(claude=Quoting(), lines=["do some work", "exit"])
        sh.run()

        transcript = "\n".join(out).splitlines()
        header = shell.DELEGATED_RESPONSE_HEADER
        footer = shell.DELEGATED_RESPONSE_FOOTER

        # Exactly one real opening and one real closing boundary, and they are
        # the fixed strings the owner can grep for.
        self.assertEqual(transcript.count(header), 1, "start is ambiguous")
        self.assertEqual(transcript.count(footer), 1, "end is ambiguous")

        start = transcript.index(header)
        end = transcript.index(footer)
        self.assertLess(start, end)

        # The response is intact between them, with only its impostor lines
        # prefixed and every ordinary line untouched.
        body = transcript[start + 1:end]
        self.assertEqual(body, [
            "intro",
            shell.QUOTED_LINE_PREFIX + header,
            "middle",
            shell.QUOTED_LINE_PREFIX + footer,
            "outro",
        ])

    def test_a_multi_line_response_stays_inside_the_rules(self):
        class Chatty(FakeClaude):
            def send(self, message):
                return True, "line one\nline two\nline three"

        sh, out = self.make_shell(claude=Chatty(), lines=["do some work", "exit"])
        sh.run()
        header = out.index(shell.DELEGATED_RESPONSE_HEADER)
        footer = out.index(shell.DELEGATED_RESPONSE_FOOTER)
        self.assertLess(header, footer)
        body = "\n".join(out[header + 1:footer])
        self.assertIn("line one", body)
        self.assertIn("line three", body)

    def test_builtin_answers_are_not_marked(self):
        for line in ("help", "status", "parked"):
            sh, out = self.make_shell(lines=[line, "exit"])
            sh.run()
            self.assertNotIn(shell.DELEGATED_RESPONSE_HEADER, out, line)

    def test_state_query_answers_are_not_marked(self):
        sh, out = self.make_shell(lines=["what's happening?", "exit"])
        sh.run()
        self.assertNotIn(shell.DELEGATED_RESPONSE_HEADER, out)

    def test_empty_delegated_response_is_still_marked(self):
        class Silent(FakeClaude):
            def send(self, message):
                return True, ""

        sh, out = self.make_shell(claude=Silent(), lines=["do some work", "exit"])
        sh.run()
        index = out.index(shell.DELEGATED_RESPONSE_HEADER)
        self.assertEqual(out[index + 1], "(no output)")


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
        self.assertIn("do not retry the identical action", message)

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
