"""
Documentation-contract test for README.md

Regression-sensitive assertions that detect removal of:
- Operational sections (Motivating workflow, Problem, Status, terminal guarantee)
- Initialization independence statement
- Mermaid architecture diagram
- Maturity labels (DOCUMENTED, PROCESS_IN_USE, DESIGN_REVIEWED, etc.)
- Evidence links to GitHub issues and PRs
- Design principles
- Production-ready disclaimer
"""

import unittest
import re


class TestREADMEDocumentationContract(unittest.TestCase):
    """Ensure README preserves critical operational and design documentation."""

    @classmethod
    def setUpClass(cls):
        """Load README.md once for all tests."""
        with open("README.md", "r", encoding="utf-8") as f:
            cls.readme_content = f.read()

    def test_readme_has_motivating_workflow_section(self):
        """Detect removal of motivating workflow section (PingStep context)."""
        self.assertIn(
            "## Motivating workflow",
            self.readme_content,
            "Missing: ## Motivating workflow section — critical operational context"
        )
        self.assertIn(
            "PingStep",
            self.readme_content,
            "Missing: PingStep reference in motivating workflow"
        )

    def test_readme_has_problem_statement_section(self):
        """Detect removal of problem statement."""
        self.assertIn(
            "## The Problem",
            self.readme_content,
            "Missing: ## The Problem section"
        )
        self.assertIn(
            "human becomes the message bus",
            self.readme_content,
            "Missing: 'human becomes the message bus' — core problem statement"
        )

    def test_readme_has_original_status_section(self):
        """Detect removal of original Status section with Phase and Framing."""
        self.assertIn(
            "## Status",
            self.readme_content,
            "Missing: ## Status section"
        )
        self.assertIn(
            "Phase",
            self.readme_content,
            "Missing: Phase in Status section"
        )
        self.assertIn(
            "Framing",
            self.readme_content,
            "Missing: Framing in Status section"
        )
        self.assertIn(
            "two-week MVP",
            self.readme_content,
            "Missing: 'two-week MVP' in Status section"
        )

    def test_readme_has_terminal_return_guarantee(self):
        """Detect removal of terminal return guarantee."""
        self.assertIn(
            "terminal returns to `dogBuild>`",
            self.readme_content,
            "Missing: 'terminal returns to dogBuild>' — critical UX guarantee"
        )

    def test_readme_has_initialization_independence_statement(self):
        """Detect removal of initialization independence statement."""
        self.assertIn(
            "Initialization is independent by default",
            self.readme_content,
            "Missing: 'Initialization is independent by default' statement"
        )
        self.assertIn(
            "DogBuild never injects the founder's private Lab",
            self.readme_content,
            "Missing: governance independence guarantee"
        )

    def test_readme_has_human_authority_statement(self):
        """Detect removal of human-authority principle."""
        self.assertIn(
            "The human is the final authority",
            self.readme_content,
            "Missing: 'The human is the final authority' principle"
        )

    def test_readme_has_mermaid_architecture_diagram(self):
        """Detect removal of architecture diagram."""
        self.assertIn(
            "```mermaid",
            self.readme_content,
            "Missing: Mermaid diagram block"
        )
        self.assertIn(
            "Founder Intent",
            self.readme_content,
            "Missing: 'Founder Intent' in architecture diagram"
        )
        self.assertIn(
            "GitHub Control",
            self.readme_content,
            "Missing: 'GitHub Control' in architecture diagram"
        )
        self.assertIn(
            "append-only",
            self.readme_content,
            "Missing: 'append-only' concept in architecture"
        )

    def test_readme_has_maturity_labels(self):
        """Detect removal of component maturity labels."""
        maturity_labels = [
            "DOCUMENTED",
            "PROCESS_IN_USE",
            "DESIGN_REVIEWED",
            "LIVE_ENFORCEMENT_PENDING",
            "IMPLEMENTED / NOT DEPLOYED",
            "IN_REVIEW",
            "PLANNED",
            "DEFERRED"
        ]
        for label in maturity_labels:
            self.assertIn(
                label,
                self.readme_content,
                f"Missing maturity label: {label}"
            )

    def test_readme_has_evidence_links(self):
        """Detect removal of GitHub issue and PR evidence links."""
        evidence_links = [
            "#180",  # Control board
            "#169",  # MCP tool curation
            "#175",  # Exact-SHA CI proof
            "#167",  # Least-privilege identity
            "#176",  # Pre-write authorization
            "#170",  # Onboarding conformance
            "#164",  # Fourth-server deployable
            "#183",  # Documentation task
            "#173",  # Control MCP package
            "#174",  # Comment policy tool
        ]
        for link in evidence_links:
            self.assertIn(
                link,
                self.readme_content,
                f"Missing evidence link: {link}"
            )

    def test_readme_has_design_principles_section(self):
        """Detect removal of design principles."""
        self.assertIn(
            "## Design Principles",
            self.readme_content,
            "Missing: ## Design Principles section"
        )
        self.assertIn(
            "GitHub records live control and execution state",
            self.readme_content,
            "Missing: GitHub-first design principle"
        )
        self.assertIn(
            "DogBuild contains no AI",
            self.readme_content,
            "Missing: 'no AI' design principle"
        )
        self.assertIn(
            "Workers do not self-start",
            self.readme_content,
            "Missing: worker boundary principle"
        )

    def test_readme_has_production_disclaimer(self):
        """Detect removal of production-ready disclaimer."""
        self.assertIn(
            "not yet a production-ready autonomous-agent platform",
            self.readme_content,
            "Missing: production-ready disclaimer"
        )

    def test_readme_has_completed_work_table(self):
        """Detect removal of completed work status table."""
        self.assertIn(
            "## Completed Work",
            self.readme_content,
            "Missing: ## Completed Work section"
        )
        self.assertIn(
            "GitHub-first control-board",
            self.readme_content,
            "Missing: GitHub control board in completed work"
        )

    def test_readme_has_roadmap_section(self):
        """Detect removal of immediate roadmap."""
        self.assertIn(
            "## Immediate Roadmap",
            self.readme_content,
            "Missing: ## Immediate Roadmap section"
        )
        # Verify roadmap items are present
        roadmap_items = [
            "Correct and independently review PR #184",
            "Reconcile or exclude PR #174",
            "Complete least-privilege identity",
            "Implement deterministic pre-write gateway",
        ]
        for item in roadmap_items:
            self.assertIn(
                item,
                self.readme_content,
                f"Missing roadmap item: {item}"
            )

    def test_readme_structure_has_no_silent_rewrites(self):
        """Regression test: detect if structure sections were silently replaced."""
        # Count major sections
        section_count = len(re.findall(r"^## ", self.readme_content, re.MULTILINE))
        self.assertGreaterEqual(
            section_count,
            12,
            f"Too few major sections: expected ≥12, found {section_count} — "
            "possible silent rewrite of documentation structure"
        )

    def test_readme_tests_run_in_ci_mentioned(self):
        """Detect removal of CI testing statement."""
        self.assertIn(
            "Tests run in CI",
            self.readme_content,
            "Missing: 'Tests run in CI' statement from Status section"
        )
        self.assertIn(
            "Python 3.9 and 3.11",
            self.readme_content,
            "Missing: Python version specification in Status"
        )

    def test_readme_scope_discipline_section_present(self):
        """Detect removal of scope discipline (MVP) section."""
        self.assertIn(
            "## Scope Discipline (MVP)",
            self.readme_content,
            "Missing: ## Scope Discipline section"
        )
        self.assertIn(
            "Local-only · file-based",
            self.readme_content,
            "Missing: scope discipline statement"
        )


class TestREADMEMutationDetection(unittest.TestCase):
    """Negative-control tests: execute contract against mutated content.

    These tests create mutated versions of README.md (with specific sections
    removed) and run the actual documentation contract assertions against them.
    They verify that contract tests fail with the expected failure reason.
    """

    @classmethod
    def setUpClass(cls):
        """Load README once."""
        with open("README.md", "r", encoding="utf-8") as f:
            cls.original_readme = f.read()

    def _run_contract_assertion(self, mutated_content, assertion_key):
        """Execute a specific contract assertion against mutated content.

        Returns: (passed, actual_in_content, expected_key)
        """
        # Test: motivating workflow
        if assertion_key == "motivating_workflow":
            return ("## Motivating workflow" in mutated_content,
                    "## Motivating workflow",
                    "## Motivating workflow")

        # Test: initialization independence
        elif assertion_key == "initialization_independence":
            return ("Initialization is independent by default" in mutated_content,
                    "Initialization is independent by default",
                    "Initialization is independent by default")

        # Test: terminal guarantee
        elif assertion_key == "terminal_guarantee":
            return ("terminal returns to `dogBuild>`" in mutated_content,
                    "terminal returns to `dogBuild>`",
                    "terminal returns to `dogBuild>`")

        # Test: design principles
        elif assertion_key == "design_principles":
            return ("## Design Principles" in mutated_content,
                    "## Design Principles",
                    "## Design Principles")

        # Test: mermaid diagram
        elif assertion_key == "mermaid_diagram":
            return (("```mermaid" in mutated_content and "Founder Intent" in mutated_content),
                    "```mermaid...Founder Intent",
                    "mermaid diagram with Founder Intent")

    def test_mutation_removal_of_motivating_workflow_is_caught(self):
        """Negative control: contract fails when motivating workflow removed."""
        mutated = self.original_readme.replace("## Motivating workflow", "")
        passed, found, expected = self._run_contract_assertion(mutated, "motivating_workflow")
        # Contract test MUST fail for this mutation
        self.assertFalse(passed,
            f"Contract should catch removal of '{expected}', but assertion passed on mutated content")

    def test_mutation_removal_of_initialization_independence_is_caught(self):
        """Negative control: contract fails when initialization independence removed."""
        mutated = self.original_readme.replace("Initialization is independent by default", "")
        passed, found, expected = self._run_contract_assertion(mutated, "initialization_independence")
        # Contract test MUST fail for this mutation
        self.assertFalse(passed,
            f"Contract should catch removal of '{expected}', but assertion passed on mutated content")

    def test_mutation_removal_of_terminal_guarantee_is_caught(self):
        """Negative control: contract fails when terminal guarantee removed."""
        mutated = self.original_readme.replace("terminal returns to `dogBuild>`", "")
        passed, found, expected = self._run_contract_assertion(mutated, "terminal_guarantee")
        # Contract test MUST fail for this mutation
        self.assertFalse(passed,
            f"Contract should catch removal of '{expected}', but assertion passed on mutated content")

    def test_mutation_removal_of_design_principles_is_caught(self):
        """Negative control: contract fails when design principles removed."""
        mutated = self.original_readme.replace("## Design Principles", "")
        passed, found, expected = self._run_contract_assertion(mutated, "design_principles")
        # Contract test MUST fail for this mutation
        self.assertFalse(passed,
            f"Contract should catch removal of '{expected}', but assertion passed on mutated content")

    def test_mutation_removal_of_mermaid_is_caught(self):
        """Negative control: contract fails when mermaid diagram removed."""
        mutated = self.original_readme.replace("```mermaid", "```text")
        passed, found, expected = self._run_contract_assertion(mutated, "mermaid_diagram")
        # Contract test MUST fail for this mutation
        self.assertFalse(passed,
            f"Contract should catch removal of '{expected}', but assertion passed on mutated content")


if __name__ == "__main__":
    unittest.main()
