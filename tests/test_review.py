import os
import tempfile
import unittest

from psk import core, gitutil, identity, review, store
from psk.errors import ProjectMismatchError, ValidationError
from tests._helpers import cleanup, make_repo


def build_decision(rec, ident, **overrides) -> str:
    fp = rec["dirty_fingerprint"] or "null"
    fields = {
        "schema_version": "1",
        "packet_type": "review_decision",
        "packet_id": rec["packet_id"],
        "project_id": ident.project_id,
        "repository_id": ident.repository_id,
        "reviewed_branch": rec["branch"],
        "reviewed_head": rec["head_commit"],
        "reviewed_diff_fingerprint": fp,
        "scope_id": rec["scope_id"],
        "scope_revision": rec["scope_revision"],
        "reviewer": "chatgpt",
        "decision": "APPROVE",
        "confidence": "high",
        "reviewed_at": "2026-07-25T00:00:00Z",
    }
    fields.update(overrides)
    yaml = "\n".join(f"{k}: {v}" for k, v in fields.items())
    return (f"```yaml\n{yaml}\n```\n\n## Decision\nAPPROVE\n\n## Rationale\nfine\n\n"
            f"## Conditions\nNone\n\n## Required next action\n{rec['action']}\n")


class TestReview(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)
        core.initialize(self.root, objective="obj")
        core.set_scope(self.root, "Day 3 scope")
        self.ident = identity.load_identity(self.root)

    def _record(self):
        return list(store.load_state(self.root).reviews.values())[-1]

    def _write(self, text) -> str:
        fd, p = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        self.addCleanup(os.remove, p)
        return p

    def _request(self):
        return review.build_review_request(
            self.root, question="Should Claude perform the action?",
            action="Add a documented example")

    def test_happy_path_end_to_end(self):
        out = self._request()
        self.assertTrue(out.exists())
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident))
        summary = review.import_decision(self.root, dfile)
        self.assertEqual(summary["verdict"], "APPROVE")
        g = review.gate(self.root)
        self.assertEqual(g["result"], "PROCEED")
        self.assertTrue(g["approval_current"])
        # archived unchanged
        arch = os.path.join(self.root, ".ai", "exchange", "archive", rec["packet_id"])
        self.assertTrue(os.path.exists(os.path.join(arch, "request.md")))
        self.assertTrue(os.path.exists(os.path.join(arch, "decision.md")))

    def test_reject_malformed(self):
        self._request()
        dfile = self._write("this is not a decision file")
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, dfile)

    def test_reject_unknown_packet(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident, packet_id="not-a-real-id"))
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, dfile)

    def test_reject_wrong_project(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident, project_id="wrong"))
        with self.assertRaises(ProjectMismatchError):
            review.import_decision(self.root, dfile)

    def test_reject_wrong_repository(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident, repository_id="wrong"))
        with self.assertRaises(ProjectMismatchError):
            review.import_decision(self.root, dfile)

    def test_reject_wrong_branch(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident, reviewed_branch="feature-x"))
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, dfile)

    def test_reject_stale_head(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident, reviewed_head="deadbeef" * 5))
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, dfile)

    def test_reject_wrong_fingerprint(self):
        self._request()
        rec = self._record()
        dfile = self._write(build_decision(rec, self.ident,
                                           reviewed_diff_fingerprint="abc123"))
        with self.assertRaises(ValidationError):
            review.import_decision(self.root, dfile)

    def test_gate_before_import_errors(self):
        self._request()
        with self.assertRaises(ValidationError):
            review.gate(self.root)


if __name__ == "__main__":
    unittest.main()
