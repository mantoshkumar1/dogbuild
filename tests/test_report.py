from __future__ import annotations

from datetime import datetime, timezone
import os
import shutil
import tempfile
import unittest

from psk import report
from psk.errors import ValidationError
from tests._helpers import cleanup, make_repo


class TestStatusReports(unittest.TestCase):
    def setUp(self):
        self.repo = make_repo(with_commit=True)
        self.destination = tempfile.mkdtemp(prefix="psk-reports-")

    def tearDown(self):
        cleanup(self.repo)
        shutil.rmtree(self.destination, ignore_errors=True)

    def test_writes_only_short_explicit_status(self):
        result = report.write_status_report(
            self.repo,
            output_dir=self.destination,
            changed="Added the report command",
            worked="Focused tests pass",
            blocked="Nothing",
            next_action="Open the pull request",
            now=datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc),
        )
        self.assertTrue(os.path.isfile(result["report"]))
        with open(result["report"], encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("# DogBuild report — 2026-08-14 12:30 UTC", text)
        self.assertIn("## What changed\nAdded the report command", text)
        self.assertIn("## What worked\nFocused tests pass", text)
        self.assertIn("## What is blocked\nNothing", text)
        self.assertIn("## What happens next\nOpen the pull request", text)
        self.assertNotIn("# test", text)

    def test_refuses_multiline_or_secret_input(self):
        common = {
            "output_dir": self.destination,
            "worked": "Focused tests pass",
            "blocked": "Nothing",
            "next_action": "Open the pull request",
        }
        with self.assertRaisesRegex(ValidationError, "one line"):
            report.write_status_report(self.repo, changed="line one\nline two", **common)
        with self.assertRaisesRegex(ValidationError, "appears to contain a secret"):
            report.write_status_report(
                self.repo,
                changed="Use ghp_abcdefghijklmnopqrstuvwxyz1234567890",
                **common,
            )
        self.assertEqual(os.listdir(self.destination), [])

    def test_never_overwrites_same_timestamp(self):
        values = {
            "output_dir": self.destination,
            "changed": "Added reporting",
            "worked": "Tests pass",
            "blocked": "Nothing",
            "next_action": "Open the pull request",
            "now": datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc),
        }
        first = report.write_status_report(self.repo, **values)
        second = report.write_status_report(self.repo, **values)
        self.assertNotEqual(first["report"], second["report"])
        self.assertTrue(os.path.exists(first["report"]))
        self.assertTrue(os.path.exists(second["report"]))
