import os
import unittest

from psk import gitutil
from tests._helpers import cleanup, git, make_repo


class TestGitUtil(unittest.TestCase):
    def test_clean_committed_repo(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        st = gitutil.capture_git_state(d)
        self.assertEqual(st["branch"], "main")
        self.assertIsNotNone(st["head_commit"])
        self.assertFalse(st["dirty"])
        self.assertIsNone(st["dirty_fingerprint"])
        self.assertFalse(st["detached"])

    def test_dirty_fingerprint_changes(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        with open(os.path.join(d, "a.txt"), "w") as fh:
            fh.write("one")
        st1 = gitutil.capture_git_state(d)
        self.assertTrue(st1["dirty"])
        self.assertIsNotNone(st1["dirty_fingerprint"])
        with open(os.path.join(d, "b.txt"), "w") as fh:
            fh.write("two")
        st2 = gitutil.capture_git_state(d)
        self.assertNotEqual(st1["dirty_fingerprint"], st2["dirty_fingerprint"])

    def test_unborn_head(self):
        d = make_repo(with_commit=False)
        self.addCleanup(cleanup, d)
        st = gitutil.capture_git_state(d)
        self.assertIsNone(st["head_commit"])

    def test_detached_head(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        head = git(d, "rev-parse", "HEAD").strip()
        git(d, "checkout", head)
        self.assertTrue(gitutil.is_detached(d))

    def test_sanitize_remote_strips_credentials(self):
        self.assertEqual(
            gitutil.sanitize_remote_url("https://user:pass@github.com/a/b.git"),
            "https://github.com/a/b.git",
        )
        self.assertEqual(
            gitutil.sanitize_remote_url("https://x-token@github.com/a/b.git"),
            "https://github.com/a/b.git",
        )
        # scp-like carries no secret; unchanged.
        self.assertEqual(
            gitutil.sanitize_remote_url("git@github.com:a/b.git"),
            "git@github.com:a/b.git",
        )

    def test_remotes_are_sanitized(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        git(d, "remote", "add", "origin", "https://user:secret@example.com/x/y.git")
        remotes = gitutil.remotes(d)
        self.assertEqual(remotes, ["https://example.com/x/y.git"])
        self.assertNotIn("secret", " ".join(remotes))


if __name__ == "__main__":
    unittest.main()
