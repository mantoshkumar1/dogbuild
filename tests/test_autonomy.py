import json
import os
import unittest

from psk import autonomy, core, genesis, identity, review, install
from psk.errors import ValidationError
from tests._helpers import cleanup, make_repo, MIN_GENESIS


def _contract(ident, *, approved=True, milestone="complete one short reliable local control loop",
              next_action="do task 1"):
    return {
        "packet_type": "autonomy_contract",
        "autonomy_contract_revision": 1,
        "project_id": ident.project_id,
        "repository_id": ident.repository_id,
        "instruction_epoch": 1,
        "current_milestone": milestone,
        "acceptance_criteria": ["task 1", "task 2"],
        "exact_next_action": next_action,
        "permitted_actions": ["run_local_verification", "add_or_update_tests"],
        "reserved_human_actions": ["push", "merge", "deploy"],
        "limits": {"maximum_self_repair_attempts_per_failure": 2},
        "human_approved": approved,
        "created_by": "chatgpt",
    }


class TestAutonomy(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        core.initialize(self.d, display_name="Demo")
        gp = os.path.join(self.d, "g.md")
        with open(gp, "w", encoding="utf-8") as fh:
            fh.write(MIN_GENESIS)
        genesis.import_genesis(self.d, gp)
        self.ident = identity.load_identity(self.d)

    def tearDown(self):
        cleanup(self.d)

    def _start(self, **kw):
        cf = os.path.join(self.d, "contract.json")
        with open(cf, "w", encoding="utf-8") as fh:
            json.dump(_contract(self.ident, **kw), fh)
        return autonomy.start(self.d, cf)

    # 1. activation requires human approval
    def test_activation_requires_human_approval(self):
        cf = os.path.join(self.d, "bad.json")
        with open(cf, "w", encoding="utf-8") as fh:
            json.dump(_contract(self.ident, approved=False), fh)
        with self.assertRaises(ValidationError):
            autonomy.start(self.d, cf)
        st = self._start()
        self.assertEqual(st["status"], "ACTIVE")

    # 2. lifecycle
    def test_lifecycle(self):
        self._start()
        self.assertEqual(autonomy.pause(self.d)["status"], "PAUSED")
        self.assertEqual(autonomy.resume(self.d)["status"], "ACTIVE")
        self.assertEqual(autonomy.stop(self.d)["status"], "STOPPED")

    # 3. pending input persistence
    def test_pending_input_persists(self):
        self._start()
        autonomy.add_message(self.d, "I don't like this.")
        # simulate a fresh process: read straight from disk
        msgs = autonomy.list_messages(self.d)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["raw_message"], "I don't like this.")

    # 4-8. classification
    def test_classifications(self):
        cases = {
            "What's happening?": "STATE_QUERY",
            "Did tests pass?": "STATE_QUERY",
            "Keep responses shorter.": "NON_BLOCKING_FEEDBACK",
            "Do not add any API integration.": "MATERIAL_INSTRUCTION",
            "Change the milestone.": "MATERIAL_INSTRUCTION",
            "Pause this.": "PAUSE_OR_CANCEL",
            "I approve option B.": "HUMAN_DECISION",
            "I don't like this.": "AMBIGUOUS",
        }
        for text, expected in cases.items():
            self.assertEqual(autonomy.classify(text), expected, text)

    def test_ambiguous_marked_needs_clarification(self):
        self._start()
        m = autonomy.add_message(self.d, "Change it.")
        self.assertEqual(m["classification"]["type"], "AMBIGUOUS")
        self.assertEqual(m["status"], "NEEDS_CLARIFICATION")

    def test_pause_message_pauses_autonomy(self):
        self._start()
        autonomy.add_message(self.d, "Pause this.")
        self.assertEqual(autonomy.status(self.d)["status"], "PAUSED")

    # 9. state query leaves epoch unchanged
    def test_state_query_epoch_unchanged(self):
        self._start()
        e0 = autonomy.current_epoch(self.d)
        autonomy.add_message(self.d, "What's happening?")
        self.assertEqual(autonomy.current_epoch(self.d), e0)

    # 10 + 12. approval staleness under different inputs
    def test_state_query_and_feedback_do_not_stale_but_redirect_does(self):
        self._start()
        review.build_review_request(self.d, question="q", action="a")
        import psk.store as store
        rec = list(store.load_state(self.d).reviews.values())[0]
        epoch_at_request = rec["instruction_epoch"]
        self.assertTrue(autonomy.approval_is_current(self.d, epoch_at_request))
        autonomy.add_message(self.d, "What's happening?")
        autonomy.add_message(self.d, "Keep responses shorter.")
        self.assertTrue(autonomy.approval_is_current(self.d, epoch_at_request))  # not staled
        autonomy.add_message(self.d, "Stop working on this feature.")           # redirect
        self.assertFalse(autonomy.approval_is_current(self.d, epoch_at_request))  # staled

    # 11. material redirect increments epoch
    def test_material_redirect_increments_epoch(self):
        self._start()
        e0 = autonomy.current_epoch(self.d)
        autonomy.add_message(self.d, "Change the milestone.")
        self.assertEqual(autonomy.current_epoch(self.d), e0 + 1)

    # unrelated exclusion does NOT invalidate
    def test_unrelated_exclusion_does_not_invalidate(self):
        self._start()
        e0 = autonomy.current_epoch(self.d)
        m = autonomy.add_message(self.d, "Do not add any API integration.")
        self.assertEqual(m["material_effect"], "exclusion_noconflict")
        self.assertEqual(autonomy.current_epoch(self.d), e0)  # not bumped

    # 13-15. reconciliation includes every pending message + marks them
    def test_reconciliation_includes_every_message(self):
        self._start()
        autonomy.add_message(self.d, "What's happening?")
        autonomy.add_message(self.d, "Keep responses shorter.")
        autonomy.add_message(self.d, "Change the milestone.")
        ctx = autonomy.reconcile(self.d)
        classes = {c["classification"] for c in ctx["pending_owner_messages"]}
        self.assertEqual(classes, {"STATE_QUERY", "NON_BLOCKING_FEEDBACK", "MATERIAL_INSTRUCTION"})
        outcomes = {c["classification"]: c["outcome"] for c in ctx["pending_owner_messages"]}
        self.assertEqual(outcomes["STATE_QUERY"], "ANSWERED_NO_EXECUTION_EFFECT")
        self.assertEqual(outcomes["NON_BLOCKING_FEEDBACK"], "APPLIED_AS_FEEDBACK")
        self.assertEqual(outcomes["MATERIAL_INSTRUCTION"], "UPDATED_INSTRUCTION_EPOCH")
        # feedback text appears in the reviewer context
        self.assertTrue(any("shorter" in c["raw_message"] for c in ctx["pending_owner_messages"]))
        # processed messages marked
        by_type = {m["classification"]["type"]: m for m in autonomy.list_messages(self.d)}
        self.assertEqual(by_type["STATE_QUERY"]["status"], "ANSWERED")
        self.assertEqual(by_type["NON_BLOCKING_FEEDBACK"]["status"], "APPLIED")

    # 16. fresh session recovery includes pending messages
    def test_fresh_session_recovery_includes_pending(self):
        self._start()
        autonomy.add_message(self.d, "I don't like this.")   # stays NEEDS_CLARIFICATION
        cont = autonomy.continuation(self.d)                 # reads from disk only
        self.assertTrue(any("don't like" in m["raw_message"] for m in cont["pending_owner_messages"]))
        self.assertEqual(cont["instruction_epoch"], autonomy.current_epoch(self.d))

    # 17. explicit goal-change confirmation
    def test_goal_change_confirmation_phrase(self):
        for casual in ("okay", "yes", "sure", "do it"):
            self.assertFalse(autonomy.is_goal_change_confirmation(casual))
        self.assertTrue(autonomy.is_goal_change_confirmation(autonomy.GOAL_CONFIRM_PHRASE))

    # 18. repair-attempt limit
    def test_repair_attempt_limit(self):
        self._start()
        self.assertEqual(autonomy.note_verification_failure(self.d)["action"], "attempt_in_scope_repair")
        self.assertEqual(autonomy.note_verification_failure(self.d)["action"], "attempt_in_scope_repair")
        r = autonomy.note_verification_failure(self.d)
        self.assertEqual(r["action"], "NEEDS_HUMAN")
        self.assertEqual(autonomy.status(self.d)["status"], "NEEDS_HUMAN")

    # 19. owner return brief
    def test_owner_return_brief(self):
        self._start()
        brief = autonomy.owner_return_brief(self.d)
        for k in ("project", "stage", "current_milestone", "exact_next_action",
                  "anything_blocked", "human_decision_needed"):
            self.assertIn(k, brief)
        self.assertEqual(brief["stage"], "ACTIVE")
        self.assertEqual(brief["human_decision_needed"], "no")

    # 20. skill contains all required rules
    def test_skill_contains_autonomy_rules(self):
        txt = (install.source_dir() / "SKILL.md").read_text(encoding="utf-8")
        for needle in ["master reviewer", "Autonomy Contract", "instruction epoch",
                       "Reconcile before every reviewer direction",
                       "I approve updating the project goal as described above.",
                       "Welcome back", "Session rollover", "NEEDS_HUMAN",
                       "MATERIAL_INSTRUCTION"]:
            self.assertIn(needle, txt, needle)

    # 12 (scenario). the owner-away dogfood sequence
    def test_owner_away_dogfood_scenario(self):
        self._start()
        e0 = autonomy.current_epoch(self.d)
        # 2. state query -> answered, epoch unchanged, still ACTIVE
        autonomy.add_message(self.d, "What's happening?")
        self.assertEqual(autonomy.current_epoch(self.d), e0)
        self.assertEqual(autonomy.status(self.d)["status"], "ACTIVE")
        # 3. non-blocking feedback -> recorded, work valid
        autonomy.add_message(self.d, "Keep the summaries shorter.")
        self.assertEqual(autonomy.status(self.d)["status"], "ACTIVE")
        # 5. reconcile owner messages with the report
        ctx = autonomy.reconcile(self.d)
        self.assertEqual(len(ctx["pending_owner_messages"]), 2)
        # 7. unrelated material exclusion -> binding exclusion, task 2 not invalidated
        m = autonomy.add_message(self.d, "Do not add any API integration.")
        self.assertEqual(m["material_effect"], "exclusion_noconflict")
        self.assertEqual(autonomy.status(self.d)["status"], "ACTIVE")
        self.assertEqual(autonomy.current_epoch(self.d), e0)
        # 9-10. owner returns -> brief
        brief = autonomy.owner_return_brief(self.d)
        self.assertEqual(brief["stage"], "ACTIVE")


if __name__ == "__main__":
    unittest.main()
