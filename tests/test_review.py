import os
import tempfile
import unittest

from psk import core, gitutil, identity, policy, review, store
from psk.errors import ProjectMismatchError, ValidationError
from tests._helpers import build_review_decision, cleanup, import_min_genesis, make_repo


class Base(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)
        core.initialize(self.root, objective="obj")
        self.goal = import_min_genesis(self.root)
        self.ident = identity.load_identity(self.root)
        self.pol = policy.load(self.root)

    def _record(self):
        revs = store.load_state(self.root).reviews.values()
        return sorted(revs, key=lambda r: r.get("seq", -1))[-1]

    def _write(self, text) -> str:
        fd, p = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        self.addCleanup(os.remove, p)
        return p

    def _request(self, **kw):
        return review.build_review_request(
            self.root, question="Should Claude do it?", action="Add a doc", **kw)


class TestReviewHappy(Base):
    def test_approve_end_to_end(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_review_decision(rec, self.ident, self.pol, self.goal))
        s = review.import_decision(self.root, dfile)
        self.assertEqual(s["verdict"], "APPROVE")
        g = review.gate(self.root)
        self.assertEqual(g["result"], "PROCEED")
        arch = os.path.join(self.root, ".ai", "exchange", "archive", rec["packet_id"])
        self.assertTrue(os.path.exists(os.path.join(arch, "decision.md")))

    def test_request_carries_policy_and_goal_bindings(self):
        out = self._request()
        rec = self._record()
        self.assertEqual(rec["review_policy_id"], self.pol["policy_id"])
        self.assertEqual(rec["review_policy_fingerprint"], self.pol["fingerprint"])
        self.assertEqual(rec["goal_contract_id"], self.goal["goal_id"])
        text = out.read_text(encoding="utf-8")
        self.assertIn("review_policy_fingerprint", text)
        self.assertIn("goal_contract_fingerprint", text)
        # packet visibly separates evidence vs claims
        self.assertIn("Machine-collected evidence", text)
        self.assertIn("Execution-agent claims", text)


class TestReviewRejections(Base):
    def _reject(self, exc, **ov):
        self._request()
        rec = self._record()
        dfile = self._write(build_review_decision(rec, self.ident, self.pol, self.goal, **ov))
        with self.assertRaises(exc):
            review.import_decision(self.root, dfile)

    def test_malformed(self):
        self._request()
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, self._write("not a decision"))

    def test_unknown_packet(self):
        self._reject(ValidationError, packet_id="nope")

    def test_wrong_project(self):
        self._reject(ProjectMismatchError, project_id="wrong")

    def test_wrong_repository(self):
        self._reject(ProjectMismatchError, repository_id="wrong")

    def test_wrong_branch(self):
        self._reject(ValidationError, reviewed_branch="feature")

    def test_stale_head(self):
        self._reject(ValidationError, reviewed_head="deadbeef" * 5)

    def test_wrong_fingerprint(self):
        self._reject(ValidationError, reviewed_diff_fingerprint="abc123")

    def test_missing_policy_binding(self):
        self._reject(ValidationError, review_policy_fingerprint="")

    def test_mismatched_policy(self):
        self._reject(ValidationError, review_policy_version="999")

    def test_stale_goal(self):
        self._reject(ValidationError, goal_contract_revision="999")


if __name__ == "__main__":
    unittest.main()
