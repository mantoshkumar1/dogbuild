import os
import tempfile
import unittest

from psk import brief, core, declaration, genesis, gitutil, goal, handoff, park, store
from psk.errors import ProjectMismatchError, ValidationError
from tests._helpers import cleanup, git, make_repo

GENESIS = """```yaml
schema_version: 1
packet_type: project_genesis
project_name: DogBuild
core_repository: project-state-keeper
problem: Solo devs lose project purpose and context across ChatGPT, Claude, Codex, and repos.
target_user: Solo developers who explore in ChatGPT and build with Claude or Codex.
desired_outcome: Turn a mature discussion into an executable contract and keep agents aligned.
why_now: The founder hits this repeatedly building PhotoSahi and DogBuild itself.
current_milestone: Complete one short, reliable local control loop.
acceptance_criteria:
  - The human can see where the project is in under 20 seconds.
  - Optional ideas are parked rather than implemented.
explicit_exclusions:
  - automatic browser control
  - payments
unresolved_assumptions:
  - external willingness to pay
parked_ideas:
  - project forecasting and analytics
  - BYOK model-cost optimization
exact_first_action: Make the Goal Contract and Orientation Brief reflect the approved purpose.
created_by: chatgpt
human_approved: true
```
"""


def write(text) -> str:
    fd, p = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)
        core.initialize(self.root, objective="Day 1 canonical schema")  # the OBSOLETE objective
        core.set_scope(self.root, "old scope")

    def _import(self, text=GENESIS):
        p = write(text)
        self.addCleanup(os.remove, p)
        return genesis.import_genesis(self.root, p, approved_at="2026-07-25T21:00:00Z")


class TestGenesisGoal(Base):
    def test_valid_import_creates_goal_and_parks(self):
        gc = self._import()
        self.assertEqual(gc["product_name"], "DogBuild")
        self.assertEqual(gc["revision"], 1)
        self.assertTrue(gc["fingerprint"])
        state = store.load_state(self.root)
        self.assertEqual(state.goal_contract["current_milestone"],
                         "Complete one short, reliable local control loop.")
        # genesis parked_ideas were parked, not implemented
        titles = [i["title"] for i in state.parked_ideas]
        self.assertIn("project forecasting and analytics", titles)

    def test_requires_human_approval(self):
        p = write(GENESIS.replace("human_approved: true", "human_approved: false"))
        self.addCleanup(os.remove, p)
        with self.assertRaises(ValidationError):
            genesis.import_genesis(self.root, p)

    def test_malformed_rejected(self):
        p = write("not a genesis packet")
        self.addCleanup(os.remove, p)
        with self.assertRaises(ValidationError):
            genesis.import_genesis(self.root, p)

    def test_goal_show_and_verify(self):
        self._import()
        self.assertEqual(goal.show(self.root)["product_name"], "DogBuild")
        v = goal.verify(self.root)
        self.assertTrue(v["ok"])
        self.assertTrue(v["checks"]["scope_references_current_goal"])

    def test_goal_identity_mismatch(self):
        self._import()
        state = store.load_state(self.root)
        state.goal_contract["project_id"] = "wrong"
        store.save_state(self.root, state)
        with self.assertRaises(ProjectMismatchError):
            goal.verify(self.root)

    def test_goal_revision_bumps(self):
        self._import()
        gc2 = self._import()  # re-import -> revision 2
        self.assertEqual(gc2["revision"], 2)

    def test_park_does_not_change_scope_or_milestone(self):
        self._import()
        before = store.load_state(self.root)
        milestone_before = before.goal_contract["current_milestone"]
        scope_before = before.scope.description
        park.add(self.root, title="premium reviewer + cheap executor",
                 reason="valid but out of scope", phase="later")
        after = store.load_state(self.root)
        self.assertEqual(after.goal_contract["current_milestone"], milestone_before)
        self.assertEqual(after.scope.description, scope_before)
        self.assertIn("premium reviewer + cheap executor",
                      [i["title"] for i in after.parked_ideas])

    def test_handoff_carries_goal_contract(self):
        self._import()
        pid, out = handoff.create(self.root, to_agent="claude", task="t")
        rec = store.load_state(self.root).handoffs[pid]
        gc = store.load_state(self.root).goal_contract
        self.assertEqual(rec["goal_contract_id"], gc["goal_id"])
        self.assertEqual(rec["goal_revision"], gc["revision"])
        self.assertIn("goal_fingerprint", out.read_text(encoding="utf-8"))

    def test_declaration_alignment_states(self):
        for s in ("IN_SCOPE", "PARKED_IDEA", "NEEDS_HUMAN_SCOPE_CHANGE"):
            d = declaration.record(self.root, building="b", changed="c", verified="v",
                                   failed="None", incomplete="None", next_action="n",
                                   alignment_status=s)
            self.assertEqual(d["goal_alignment"]["status"], s)

    def test_brief_uses_goal_not_obsolete_objective(self):
        self._import()
        core.create_checkpoint(self.root, "Project Genesis and Goal Lock",
                               tested=["tests passing"], next_safe_action="next slice")
        fields, warnings = brief.build(self.root)
        self.assertEqual(fields["product"], "DogBuild")
        self.assertNotIn("Day 1", fields["problem"])
        self.assertNotIn("canonical schema", fields["current_milestone"])
        self.assertGreaterEqual(fields["parked_ideas"], 2)

    def test_stale_evidence_warns_but_not_human_needed(self):
        self._import()
        core.create_checkpoint(self.root, "done", tested=["t"], next_safe_action="next")
        # a stale declaration (older HEAD) must warn, not interrupt
        declaration.record(self.root, building="b", changed="c", verified="v",
                           failed="None", incomplete="None", next_action="n",
                           alignment_status="IN_SCOPE")
        with open(os.path.join(self.root, "x.py"), "w") as fh:
            fh.write("y=1\n")
        git(self.root, "add", "-A"); git(self.root, "commit", "-m", "move head")
        fields, warnings = brief.build(self.root)
        self.assertTrue(warnings)                                  # warned
        self.assertEqual(fields["human_decision_needed"], "no")    # not blocked

    def test_genuine_scope_change_needs_human(self):
        self._import()
        rev = store.load_state(self.root).goal_contract["revision"]
        declaration.record(self.root, building="b", changed="c", verified="v",
                           failed="None", incomplete="None", next_action="n",
                           alignment_status="NEEDS_HUMAN_SCOPE_CHANGE", goal_revision=rev,
                           alignment_explanation="target user would change")
        fields, warnings = brief.build(self.root)
        self.assertEqual(fields["human_decision_needed"], "yes")


if __name__ == "__main__":
    unittest.main()
