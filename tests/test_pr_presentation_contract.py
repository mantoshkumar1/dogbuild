import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from scripts.check_pr_presentation import findings, main


class PRPresentationContractTests(unittest.TestCase):
    def test_template_explains_the_issue_only_project_record(self):
        template = Path(".github/pull_request_template.md").read_text(encoding="utf-8")
        self.assertIn("## PR presentation contract", template)
        self.assertIn("**Authoritative issue:**", template)
        self.assertIn("**Project record:** Issue #<issue> in the configured GitHub Project — PR not a Project item.", template)
        self.assertIn("**PR role:**", template)
        self.assertIn("**Closing semantics:**", template)

    def test_valid_partial_pr_body_passes(self):
        body = "\n".join([
            "Refs #28 — partial; issue remains open",
            "",
            "## PR presentation contract",
            "",
            "- **Authoritative issue:** #28 — In Review",
            "- **Project record:** Issue #28 in the configured GitHub Project — PR not a Project item.",
            "- **PR role:** governance implementation slice.",
            "- **Closing semantics:** partial slice; matches the plain top-of-body directive.",
        ])
        self.assertEqual(findings(body), [])

    def test_mismatched_project_issue_and_closing_semantics_fail(self):
        body = "\n".join([
            "Refs #28 — partial; issue remains open",
            "",
            "- **Authoritative issue:** #28 — In Review",
            "- **Project record:** Issue #29 in the configured GitHub Project — PR not a Project item.",
            "- **PR role:** governance implementation slice.",
            "- **Closing semantics:** full completion;",
        ])
        result = findings(body)
        self.assertEqual(len(result), 2)
        self.assertIn("#29", result[0])
        self.assertIn("full completion", result[1])

    def test_event_payload_is_checked_without_a_github_api_call(self):
        event = {"pull_request": {"body": "Refs #28 — partial; issue remains open"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(event, handle)
            event_path = handle.name
        self.addCleanup(lambda: Path(event_path).unlink(missing_ok=True))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["check_pr_presentation.py", event_path]), 1)
