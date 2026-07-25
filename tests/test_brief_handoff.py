import contextlib
import io
import json
import os
import unittest

from psk import (agentmode, brief, core, declaration, gitutil, handoff, store)
from psk import __main__ as cli
from psk.errors import ProjectMismatchError, ValidationError
from psk.models import ItemStatus
from tests._helpers import cleanup, git, make_repo


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)
        core.initialize(self.root, objective="Build PSK MVP (dogfood-first)")
        core.set_scope(self.root, "Day 4: brief + handoff slice")
        core.create_checkpoint(self.root, "prior work done",
                               tested=["47 tests"], next_safe_action="do the next thing")

    def _commit_code(self, name="code.py"):
        with open(os.path.join(self.root, name), "w") as fh:
            fh.write("x = 1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "change")


class TestBrief(Base):
    def test_human_brief(self):
        fields, conflicts = brief.build(self.root)
        text = brief.render_text(fields, conflicts)
        self.assertIn("Project:", text)
        self.assertIn("Exact next action:", text)
        self.assertIn("Human decision needed:", text)
        self.assertEqual(fields["human_decision_needed"], "no")
        self.assertEqual(conflicts, [])

    def test_json_brief_and_where_am_i_alias(self):
        c1, o1 = run(["brief", self.root, "--json"])
        c2, o2 = run(["where-am-i", self.root, "--json"])
        self.assertEqual((c1, c2), (0, 0))
        j1, j2 = json.loads(o1), json.loads(o2)
        self.assertIn("project", j1)
        self.assertEqual(j1["project"], j2["project"])          # alias -> same source
        self.assertEqual(j1["current_phase"], j2["current_phase"])

    def test_where_am_i_human_alias(self):
        # Delegated dogfood task: confirm the alias for HUMAN-READABLE output too
        # (JSON alias is covered above).
        c1, o1 = run(["brief", self.root])
        c2, o2 = run(["where-am-i", self.root])
        self.assertEqual((c1, c2), (0, 0))
        self.assertEqual(o1, o2)  # identical output => true alias
        self.assertIn("Project:", o1)

    def test_missing_declaration_is_fine(self):
        self.assertIsNone(declaration.load_latest(self.root))
        fields, conflicts = brief.build(self.root)  # must not crash
        self.assertEqual(conflicts, [])

    def test_declaration_conflicting_with_git(self):
        declaration.record(self.root, building="x", changed="y", verified="z",
                           failed="None", incomplete="None", next_action="next")
        self._commit_code()  # HEAD moves -> declaration.claimed_head is now stale
        fields, conflicts = brief.build(self.root)
        self.assertTrue(any("declaration" in c.lower() for c in conflicts))
        self.assertEqual(fields["human_decision_needed"], "yes")


class TestHandoff(Base):
    def test_generate_claude_and_codex(self):
        for target in ("claude", "codex"):
            pid, out = handoff.create(self.root, to_agent=target,
                                      task=f"do work for {target}")
            self.assertTrue(out.exists())
            text = out.read_text(encoding="utf-8")
            self.assertIn("contains no repository source code", text)
            self.assertNotIn("import argparse", text)  # no source leaked
            self.assertIn("push, merge", text)         # reserved human-only actions
            rec = store.load_state(self.root).handoffs[pid]
            self.assertEqual(rec["packet_type"], "agent_handoff")
            self.assertEqual(rec["target_agent"], target)
            # identity + scope bindings
            ident = __import__("psk.identity", fromlist=["load_identity"]).load_identity(self.root)
            self.assertEqual(rec["project_id"], ident.project_id)
            self.assertEqual(rec["scope_id"], store.load_state(self.root).scope.scope_id)

    def test_consume_sets_active_agent(self):
        pid, _ = handoff.create(self.root, to_agent="claude", task="t")
        rec = handoff.consume(self.root, packet_id=pid, as_agent="claude")
        self.assertEqual(rec["status"], "consumed")
        self.assertEqual(agentmode.load(self.root)["active_execution_agent"], "claude")

    def test_stale_handoff_rejected(self):
        pid, _ = handoff.create(self.root, to_agent="claude", task="t")
        self._commit_code()  # HEAD moves after handoff created
        with self.assertRaises(ValidationError):
            handoff.consume(self.root, packet_id=pid)

    def test_wrong_repository_rejected(self):
        pid, _ = handoff.create(self.root, to_agent="claude", task="t")
        state = store.load_state(self.root)
        state.handoffs[pid]["project_id"] = "some-other-project"
        store.save_state(self.root, state)
        with self.assertRaises(ProjectMismatchError):
            handoff.consume(self.root, packet_id=pid)

    def test_wrong_target_agent_rejected(self):
        pid, _ = handoff.create(self.root, to_agent="codex", task="t")
        with self.assertRaises(ProjectMismatchError):
            handoff.consume(self.root, packet_id=pid, as_agent="claude")


if __name__ == "__main__":
    unittest.main()
