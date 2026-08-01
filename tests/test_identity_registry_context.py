import os
import shutil
import tempfile
import unittest

from psk import context, core, gitutil, identity, registry
from psk.errors import ValidationError
from tests._helpers import cleanup, git, make_repo


class TestIdentity(unittest.TestCase):
    def test_stable_ids_and_survives_move(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        i1 = identity.ensure_identity(root, display_name="PSK", aliases=["psk"])
        i2 = identity.ensure_identity(root)  # idempotent
        self.assertEqual(i1.project_id, i2.project_id)
        self.assertEqual(i1.repository_id, i2.repository_id)

        # Move the repository; identity must survive (same ids, updated path).
        d2 = d + "-moved"
        shutil.move(d, d2)
        self.addCleanup(cleanup, d2)
        root2 = gitutil.repo_root(d2)
        i3 = identity.ensure_identity(root2)
        self.assertEqual(i3.project_id, i1.project_id)
        self.assertEqual(i3.repository_id, i1.repository_id)
        self.assertEqual(i3.root_path, root2)

    def test_remote_fingerprint_not_raw_url(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        git(d, "remote", "add", "origin", "https://user:secret@example.com/x/y.git")
        root = gitutil.repo_root(d)
        ident = identity.ensure_identity(root)
        self.assertIsNotNone(ident.remote_fingerprint)
        self.assertNotIn("secret", ident.remote_fingerprint)
        self.assertNotIn("example.com", ident.remote_fingerprint)

    def test_no_remote_fingerprint_none(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        ident = identity.ensure_identity(gitutil.repo_root(d))
        self.assertIsNone(ident.remote_fingerprint)

    def test_upstream_source_requires_name_and_record(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        with self.assertRaises(ValidationError):
            identity.ensure_identity(root, parent_name="Opportunity Lab")
        with self.assertRaises(ValidationError):
            identity.ensure_identity(root, parent_record="https://example.test/record")

    def test_explicit_upstream_source_can_be_added_to_existing_identity(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        original = identity.ensure_identity(root)
        self.assertIsNone(original.parent_system)

        updated = identity.ensure_identity(
            root,
            parent_name="Opportunity Lab",
            parent_record="https://example.test/versioned-record",
        )
        self.assertEqual(
            updated.parent_system,
            {
                "name": "Opportunity Lab",
                "record": "https://example.test/versioned-record",
            },
        )
        self.assertEqual(updated.project_id, original.project_id)
        self.assertEqual(updated.repository_id, original.repository_id)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir

    def tearDown(self):
        if self._old is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old
        shutil.rmtree(self.regdir, ignore_errors=True)

    def test_upsert_is_idempotent(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        ident = identity.ensure_identity(gitutil.repo_root(d), display_name="X")
        registry.register(ident, branch="main", head="abc")
        registry.register(ident, branch="main", head="def")  # same project_id
        entries = registry.list_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["last_seen_head"], "def")
        # no secrets/code fields
        self.assertNotIn("secret", str(entries[0]))


class TestContext(unittest.TestCase):
    def test_identify_and_freshness(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        core.initialize(root, objective="ctx test")
        res = context.identify_local(root)
        self.assertEqual(res["result"], "IDENTIFIED")
        self.assertEqual(res["freshness"], "current")  # .ai writes don't mark stale

        # A real code change -> stale.
        with open(os.path.join(root, "code.py"), "w") as fh:
            fh.write("x=1\n")
        git(root, "add", "-A")
        git(root, "commit", "-m", "change")
        self.assertEqual(context.freshness(root), "stale")

    def test_export_packet_is_safe(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        core.initialize(root, objective="obj")
        out = context.export_context_packet(root, purpose="Day 2 review")
        self.assertTrue(out.exists())
        text = out.read_text(encoding="utf-8")
        card = context.context_card(root)
        self.assertIn("# DogBuild — chat context packet", text)
        self.assertIn("Review the attached DogBuild packet.", text)
        self.assertIn(card["project_id"], text)
        self.assertIn("Day 2 review", text)


if __name__ == "__main__":
    unittest.main()
