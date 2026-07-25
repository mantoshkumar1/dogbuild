import os
import tempfile
import unittest

from psk import brief, core, gitutil, human, identity, park, policy, review, store
from psk.errors import ValidationError
from tests._helpers import (build_review_decision, cleanup, git,
                            import_min_genesis, make_repo)


class Base(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)
        core.initialize(self.root, objective="obj")
        self.goal = import_min_genesis(self.root)
        self.ident = identity.load_identity(self.root)
        self.pol = policy.load(self.root)

    def _latest(self):
        revs = store.load_state(self.root).reviews.values()
        return sorted(revs, key=lambda r: r.get("seq", -1))[-1]

    def _rec(self):
        return self._latest()

    def _write(self, text) -> str:
        fd, p = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        self.addCleanup(os.remove, p)
        return p

    def _decide(self, decision, **ov):
        review.build_review_request(self.root, question="q?", action="Add a doc")
        rec = self._rec()
        dfile = self._write(build_review_decision(rec, self.ident, self.pol, self.goal,
                                                  decision=decision, **ov))
        return review.import_decision(self.root, dfile), rec

    def _commit_code(self, name="c.py"):
        with open(os.path.join(self.root, name), "w") as fh:
            fh.write("x=1\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "move head")


class TestPolicy(Base):
    def test_canonicalization_and_fingerprint(self):
        p = policy.load(self.root)
        self.assertEqual(p["policy_id"], "dogbuild-default-reviewer")
        self.assertEqual(policy.fingerprint(p), p["fingerprint"])  # deterministic
        self.assertIn("APPROVE", p["allowed_decisions"])
        self.assertTrue(p["behavior"]["judge_evidence_not_tone"])  # coerced bool

    def test_verify(self):
        v = policy.verify(self.root)
        self.assertTrue(v["ok"])
        self.assertTrue(v["checks"]["fingerprint_stable"])


class TestOutcomes(Base):
    def test_approve_proceed(self):
        self._decide("APPROVE")
        self.assertEqual(review.gate(self.root)["result"], "PROCEED")

    def test_conditional_persisted_and_proceeds(self):
        self._decide("APPROVE_WITH_CONDITIONS",
                     conditions_block="- keep it documentation-only\n- add a test")
        g = review.gate(self.root)
        self.assertEqual(g["result"], "PROCEED_WITH_CONDITIONS")
        conds = store.load_state(self.root).reviews[g["packet_id"]]["conditions"]
        self.assertEqual(len(conds), 2)
        self.assertEqual(conds[0]["status"], "open")

    def test_veto_stop(self):
        self._decide("VETO")
        self.assertEqual(review.gate(self.root)["result"], "STOP_VETO")

    def test_needs_human_stop_and_brief(self):
        self._decide("NEEDS_HUMAN")
        self.assertEqual(review.gate(self.root)["result"], "STOP_NEEDS_HUMAN")
        b = human.show(self.root)
        self.assertIn("NEEDS_HUMAN", b["why_needed"])
        self.assertTrue(b["decision_required"])
        self.assertIn("options", b)


class TestVetoRevision(Base):
    def test_one_revision_with_new_evidence(self):
        _, rec = self._decide("VETO")
        out = review.revise(self.root, rec["packet_id"], "new: tests now prove it is safe")
        self.assertTrue(out.exists())
        new = self._latest()
        self.assertEqual(new["revision_count"], 1)

    def test_revision_requires_new_evidence(self):
        _, rec = self._decide("VETO")
        with self.assertRaises(ValidationError):
            review.revise(self.root, rec["packet_id"], "   ")

    def test_revision_only_after_veto(self):
        _, rec = self._decide("APPROVE")
        with self.assertRaises(ValidationError):
            review.revise(self.root, rec["packet_id"], "evidence")

    def test_second_revision_rejected(self):
        _, rec = self._decide("VETO")
        review.revise(self.root, rec["packet_id"], "evidence 1")
        new = self._latest()
        # veto the revised request, then try to revise it again -> rejected
        dfile = self._write(build_review_decision(new, self.ident, self.pol, self.goal,
                                                  decision="VETO"))
        review.import_decision(self.root, dfile)
        with self.assertRaises(ValidationError):
            review.revise(self.root, new["packet_id"], "evidence 2")


class TestHumanAndResume(Base):
    def _human_file(self, choice="reject the action", scope_changed="false"):
        return self._write(f"choice: {choice}\nquestion: proceed?\n"
                           f"scope_changed: {scope_changed}\n")

    def test_decide_and_resume(self):
        human.decide(self.root, self._human_file())
        self.assertEqual(human.resume_verify(self.root)["result"], "RESUME")

    def test_resume_state_changed(self):
        human.decide(self.root, self._human_file())
        self._commit_code()  # HEAD moves after the decision
        self.assertEqual(human.resume_verify(self.root)["result"], "STOP_STATE_CHANGED")

    def test_stale_human_decision(self):
        first = human.decide(self.root, self._human_file())
        human.decide(self.root, self._human_file(choice="approve the exact action"))
        r = human.resume_verify(self.root, decision_id=first["id"])
        self.assertEqual(r["result"], "STOP_STALE_HUMAN_DECISION")


class TestBriefBlockerVsWarning(Base):
    def test_current_veto_blocks(self):
        self._decide("VETO")
        fields, _ = brief.build(self.root)
        self.assertEqual(fields["current_gate"], "STOP_VETO")
        self.assertEqual(fields["human_decision_needed"], "yes")

    def test_stale_veto_is_warning_not_blocker(self):
        self._decide("VETO")
        self._commit_code()  # veto now applies to an older HEAD
        fields, warnings = brief.build(self.root)
        self.assertTrue(warnings)
        self.assertEqual(fields["human_decision_needed"], "no")

    def test_parked_idea_is_not_a_blocker(self):
        park.add(self.root, title="forecasting", reason="out of scope", phase="later")
        fields, _ = brief.build(self.root)
        self.assertGreaterEqual(fields["parked_ideas"], 1)
        self.assertEqual(fields["human_decision_needed"], "no")


if __name__ == "__main__":
    unittest.main()
