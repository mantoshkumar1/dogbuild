import json
import unittest

from psk import core, gitutil, store
from psk.errors import IncompatibleStateError, StateExistsError, StateNotFoundError, ValidationError
from psk.models import ProjectState, to_jsonable
from tests._helpers import cleanup, make_repo


class TestStore(unittest.TestCase):
    def setUp(self):
        self.d = make_repo(with_commit=True)
        self.addCleanup(cleanup, self.d)
        self.root = gitutil.repo_root(self.d)

    def test_initialize_creates_files(self):
        core.initialize(self.root, objective="Ship the Day 1 schema")
        self.assertTrue(store.state_path(self.root).exists())
        self.assertTrue(store.events_path(self.root).exists())
        self.assertTrue(store.projection_path(self.root).exists())
        self.assertTrue(store.state_exists(self.root))

    def test_no_silent_overwrite(self):
        core.initialize(self.root)
        with self.assertRaises(StateExistsError):
            core.initialize(self.root)
        # force allows reinit
        core.initialize(self.root, force=True)

    def test_load_roundtrip_identity(self):
        s = core.initialize(self.root, objective="obj")
        loaded = store.load_state(self.root)
        self.assertEqual(loaded.identity.psk_uuid, s.identity.psk_uuid)
        self.assertEqual(loaded.objective.text, "obj")

    def test_malformed_state_rejected(self):
        core.initialize(self.root)
        store.state_path(self.root).write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValidationError):
            store.load_state(self.root)

    def test_incompatible_schema_rejected(self):
        core.initialize(self.root)
        d = json.loads(store.state_path(self.root).read_text(encoding="utf-8"))
        d["schema_version"] = "99.0.0"
        store.state_path(self.root).write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(IncompatibleStateError):
            store.load_state(self.root)

    def test_save_without_create_requires_existing(self):
        s = core.initialize(self.root)
        # simulate a brand-new repo with no state, then save without allow_create
        d2 = make_repo(with_commit=True)
        self.addCleanup(cleanup, d2)
        root2 = gitutil.repo_root(d2)
        with self.assertRaises(StateNotFoundError):
            store.save_state(root2, s)


class TestModels(unittest.TestCase):
    def test_roundtrip_stable(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        core.initialize(root, objective="x")
        loaded = store.load_state(root)
        once = to_jsonable(loaded)
        twice = to_jsonable(ProjectState.from_dict(once))
        self.assertEqual(once, twice)

    def test_enums_serialize_to_strings(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        core.initialize(root)
        d2 = json.loads(store.state_path(root).read_text(encoding="utf-8"))
        for action in d2["reserved_approvals"]:
            self.assertIsInstance(action, str)
        self.assertIn("push", d2["reserved_approvals"])


if __name__ == "__main__":
    unittest.main()
