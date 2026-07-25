import unittest

from psk import core, gitutil, store
from psk.models import Authority, EvidenceKind, ItemStatus, Verdict
from tests._helpers import cleanup, make_repo


class TestCore(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)

    def _events(self):
        return store.read_events(self.root)

    def test_initialize_records_events(self):
        core.initialize(self.root, objective="obj")
        types = [e["type"] for e in self._events()]
        self.assertEqual(types[0], "initialized")
        self.assertIn("objective_set", types)

    def test_objective_versions_bump(self):
        core.initialize(self.root, objective="v1")
        s = core.set_objective(self.root, "v2")
        self.assertEqual(s.objective.version, 2)
        self.assertEqual(s.objective.text, "v2")

    def test_item_lifecycle(self):
        core.initialize(self.root)
        item = core.request_item(self.root, "implement schema")
        self.assertEqual(item.status, ItemStatus.REQUESTED)
        s = core.set_item_status(self.root, item.id, ItemStatus.DONE)
        self.assertEqual(s.items[item.id].status, ItemStatus.DONE)
        types = [e["type"] for e in self._events()]
        self.assertIn("item_requested", types)
        self.assertIn("item_status_changed", types)

    def test_evidence_links_to_item(self):
        core.initialize(self.root)
        item = core.request_item(self.root, "task")
        ev = core.record_evidence(
            self.root, EvidenceKind.TEST, "18 tests pass", item_id=item.id
        )
        s = store.load_state(self.root)
        self.assertIn(ev.id, s.items[item.id].evidence_ids)
        self.assertEqual(s.evidence[ev.id].kind, EvidenceKind.TEST)

    def test_decision_binding_captures_commit(self):
        core.initialize(self.root)
        head = gitutil.head_commit(self.root)
        dec = core.record_decision(
            self.root, Authority.CHATGPT, Verdict.APPROVE, action="commit day1"
        )
        self.assertEqual(dec.binding.head_commit, head)
        self.assertEqual(dec.verdict, Verdict.APPROVE)
        self.assertEqual(dec.binding.repo_uuid, store.load_state(self.root).identity.psk_uuid)

    def test_checkpoint_sets_last_id(self):
        core.initialize(self.root)
        cp = core.create_checkpoint(
            self.root, "Day 1 done", implemented=["schema"], next_safe_action="Day 2 CLI"
        )
        s = store.load_state(self.root)
        self.assertEqual(s.last_checkpoint_id, cp.id)
        self.assertIn(cp.id, s.checkpoints)
        self.assertIn("checkpoint_created", [e["type"] for e in self._events()])

    def test_all_events_valid_and_ordered(self):
        core.initialize(self.root, objective="o")
        core.set_scope(self.root, "day 1 only")
        item = core.request_item(self.root, "t")
        core.set_item_status(self.root, item.id, ItemStatus.IN_PROGRESS)
        core.record_evidence(self.root, EvidenceKind.NOTE, "n")
        events = self._events()
        self.assertGreaterEqual(len(events), 5)
        # timestamps are non-decreasing
        stamps = [e["timestamp"] for e in events]
        self.assertEqual(stamps, sorted(stamps))


if __name__ == "__main__":
    unittest.main()
