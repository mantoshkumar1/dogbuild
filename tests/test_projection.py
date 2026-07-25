import unittest

from psk import core, gitutil, store
from psk.projection import render_markdown
from tests._helpers import cleanup, make_repo


class TestProjection(unittest.TestCase):
    def test_deterministic_and_informative(self):
        d = make_repo(with_commit=True)
        self.addCleanup(cleanup, d)
        root = gitutil.repo_root(d)
        core.initialize(root, objective="Deterministic projection test")
        state = store.load_state(root)
        md1 = render_markdown(state)
        md2 = render_markdown(state)
        self.assertEqual(md1, md2)  # deterministic for the same state
        self.assertIn("Deterministic projection test", md1)
        self.assertIn("Git state", md1)
        self.assertIn("Reserved human-only approvals", md1)
        # separates current facts from historical claims
        self.assertIn("Project State (current)", md1)
        self.assertIn("Checkpoints (historical claims)", md1)


if __name__ == "__main__":
    unittest.main()
