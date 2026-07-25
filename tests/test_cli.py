import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest

from psk import __main__ as cli
from psk import exit_codes, gitutil, registry
from tests._helpers import cleanup, make_repo


def run(argv):
    """Run the CLI, capturing stdout; return (exit_code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.regdir = tempfile.mkdtemp(prefix="psk-reg-")
        self._old = os.environ.get(registry.REGISTRY_ENV)
        os.environ[registry.REGISTRY_ENV] = self.regdir
        self.d = make_repo(with_commit=True)
        self.root = gitutil.repo_root(self.d)

    def tearDown(self):
        if self._old is None:
            os.environ.pop(registry.REGISTRY_ENV, None)
        else:
            os.environ[registry.REGISTRY_ENV] = self._old
        shutil.rmtree(self.regdir, ignore_errors=True)
        cleanup(self.d)

    def test_init_then_status_json(self):
        code, _ = run(["init", self.root, "--objective", "obj"])
        self.assertEqual(code, exit_codes.SUCCESS)
        # registry now has the project
        self.assertEqual(len(registry.list_entries()), 1)

        code, out = run(["status", self.root, "--json"])
        self.assertEqual(code, exit_codes.SUCCESS)
        data = json.loads(out)
        self.assertIn("project_id", data)
        self.assertEqual(data["freshness"], "current")

    def test_context_identify_and_list(self):
        run(["init", self.root])
        code, out = run(["context", "identify", self.root, "--json"])
        self.assertEqual(code, exit_codes.SUCCESS)
        self.assertEqual(json.loads(out)["result"], "IDENTIFIED")

        code, out = run(["context", "list", "--json"])
        self.assertEqual(code, exit_codes.SUCCESS)
        self.assertEqual(len(json.loads(out)), 1)

    def test_no_repository_exit_code(self):
        nongit = tempfile.mkdtemp(prefix="psk-nongit-")
        self.addCleanup(shutil.rmtree, nongit, True)
        code, _ = run(["context", "identify", nongit])
        self.assertEqual(code, exit_codes.NO_REPOSITORY)

    def test_not_initialized_exit_code(self):
        # git repo, but no `init` run -> not initialized
        code, _ = run(["context", "identify", self.root])
        self.assertEqual(code, exit_codes.NOT_INITIALIZED)

    def test_double_init_is_usage_error(self):
        run(["init", self.root])
        code, _ = run(["init", self.root])
        self.assertEqual(code, exit_codes.INVALID_USAGE)

    def test_export_packet(self):
        run(["init", self.root])
        code, out = run(["context", "export", self.root, "--for", "chatgpt",
                         "--purpose", "review", "--json"])
        self.assertEqual(code, exit_codes.SUCCESS)
        self.assertTrue(os.path.exists(json.loads(out)["packet"]))


if __name__ == "__main__":
    unittest.main()
