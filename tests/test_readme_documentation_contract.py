"""
Documentation-contract test for README.md

Regression-sensitive assertions that detect removal of:
- Operational sections (Motivating workflow, Problem, Status, Quickstart, terminal guarantee)
- Initialization independence statement
- Design principles
- Component status legend with maturity labels
- Production-ready disclaimer
"""

import unittest
import re


class DocumentationContract:
    """Shared contract validation used by both positive and negative tests."""

    # Define the contract predicates based on actual content
    REQUIRED_SECTIONS = {
        "motivating_workflow": "## Motivating workflow",
        "status_section": "## Status",
        "quickstart_section": "## Quickstart",
        "share_short_status_section": "### Share a short status",
        "component_status_legend": "Component Status Legend",
    }

    REQUIRED_CONTENT = {
        "pingstep_reference": "PingStep",
        "initialization_independence": "Initialization is independent by default",
        "terminal_guarantee": "terminal returns to `dogBuild>`",
        "report_command_example": "dogbuild report . --output-dir",
        "report_safety_boundary": "DogBuild does not copy project files, source code, or command output",
        "report_output_choice": "Pick the output folder yourself",
        "documented_label": "DOCUMENTED",
        "process_in_use_label": "PROCESS_IN_USE",
        "design_reviewed_label": "DESIGN_REVIEWED",
        "live_enforcement_pending": "LIVE_ENFORCEMENT_PENDING",
        "authority_model_link": "docs/authority-model.md",
        "governance_boundaries_link": "docs/governance-boundaries.md",
        "production_disclaimer": "not yet production-ready",
        "connectivity_inventory_item": "MCP portal connectivity and inventory documentation",
        "enforcement_identity_item": "Curation enforcement and least-privilege access control",
        "issue_169_reference": "#169",
        "issue_167_reference": "#167",
    }

    def validate(self, readme_text):
        """
        Validate README against contract.

        Returns: (is_valid, diagnostic_messages)
        """
        failures = []

        # Check required sections
        for key, section in self.REQUIRED_SECTIONS.items():
            if section not in readme_text:
                failures.append(f"Missing section: {key} ('{section}')")

        # Check required content
        for key, content in self.REQUIRED_CONTENT.items():
            if content not in readme_text:
                failures.append(f"Missing content: {key} ('{content}')")

        is_valid = len(failures) == 0
        return is_valid, failures


class TestREADMEDocumentationContract(unittest.TestCase):
    """Ensure README preserves critical operational and design documentation."""

    @classmethod
    def setUpClass(cls):
        """Load README.md and set up contract validator."""
        with open("README.md", "r", encoding="utf-8") as f:
            cls.pristine_readme = f.read()
        cls.contract = DocumentationContract()

    def test_pristine_readme_passes_contract(self):
        """Positive test: pristine README passes contract."""
        is_valid, failures = self.contract.validate(self.pristine_readme)
        self.assertTrue(is_valid, f"Pristine README should pass contract. Failures: {failures}")

    def test_mutation_removal_of_motivating_workflow_is_caught(self):
        """Negative control: contract fails when motivating workflow removed."""
        mutated = self.pristine_readme.replace("## Motivating workflow", "")
        self.assertNotIn("## Motivating workflow", mutated,
            "Mutation should remove motivating workflow section")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed motivating workflow")
        self.assertTrue(any("motivating_workflow" in f for f in failures),
            f"Failure should mention motivating_workflow. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring motivating workflow. Failures: {failures}")

    def test_mutation_removal_of_status_section_is_caught(self):
        """Negative control: contract fails when status section removed."""
        mutated = self.pristine_readme.replace("## Status", "")
        self.assertNotIn("## Status", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed status section")
        self.assertTrue(any("status_section" in f for f in failures),
            f"Failure should mention status_section. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring status section. Failures: {failures}")

    def test_mutation_removal_of_initialization_independence_is_caught(self):
        """Negative control: contract fails when initialization independence removed."""
        mutated = self.pristine_readme.replace("Initialization is independent by default", "")
        self.assertNotIn("Initialization is independent by default", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed initialization independence")
        self.assertTrue(any("initialization_independence" in f for f in failures),
            f"Failure should mention initialization_independence. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring initialization independence. Failures: {failures}")

    def test_mutation_removal_of_terminal_guarantee_is_caught(self):
        """Negative control: contract fails when terminal guarantee removed."""
        mutated = self.pristine_readme.replace("terminal returns to `dogBuild>`", "")
        self.assertNotIn("terminal returns to `dogBuild>`", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed terminal guarantee")
        self.assertTrue(any("terminal_guarantee" in f for f in failures),
            f"Failure should mention terminal_guarantee. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring terminal guarantee. Failures: {failures}")

    def test_mutation_removal_of_component_status_legend_is_caught(self):
        """Negative control: contract fails when component status legend removed."""
        mutated = self.pristine_readme.replace("Component Status Legend", "")
        self.assertNotIn("Component Status Legend", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed component status legend")
        self.assertTrue(any("component_status_legend" in f for f in failures),
            f"Failure should mention component_status_legend. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring component status legend. Failures: {failures}")

    def test_mutation_removal_of_documented_label_is_caught(self):
        """Negative control: contract fails when DOCUMENTED status label removed."""
        mutated = self.pristine_readme.replace("DOCUMENTED", "")
        self.assertNotIn("DOCUMENTED", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed DOCUMENTED status label")
        self.assertTrue(any("documented_label" in f for f in failures),
            f"Failure should mention documented_label. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring DOCUMENTED label. Failures: {failures}")

    def test_mutation_removal_of_pingstep_reference_is_caught(self):
        """Negative control: contract fails when PingStep reference removed."""
        mutated = self.pristine_readme.replace("PingStep", "")
        self.assertNotIn("PingStep", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed PingStep reference")
        self.assertTrue(any("pingstep_reference" in f for f in failures),
            f"Failure should mention pingstep_reference. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring PingStep reference. Failures: {failures}")

    def test_mutation_removal_of_authority_model_link_is_caught(self):
        """Negative control: contract fails when authority model link removed."""
        mutated = self.pristine_readme.replace("docs/authority-model.md", "")
        self.assertNotIn("docs/authority-model.md", mutated)

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed authority model link")
        self.assertTrue(any("authority_model_link" in f for f in failures),
            f"Failure should mention authority_model_link. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring authority model link. Failures: {failures}")

    def test_mutation_removal_of_share_short_status_section_is_caught(self):
        """Negative control: contract fails when 'Share a short status' section removed."""
        mutated = self.pristine_readme.replace("### Share a short status", "")
        self.assertNotIn("### Share a short status", mutated,
            "Mutation should remove 'Share a short status' section")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed 'Share a short status' section")
        self.assertTrue(any("share_short_status_section" in f for f in failures),
            f"Failure should mention share_short_status_section. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring 'Share a short status' section. Failures: {failures}")

    def test_mutation_removal_of_report_command_example_is_caught(self):
        """Negative control: contract fails when report command example removed."""
        mutated = self.pristine_readme.replace("dogbuild report . --output-dir", "")
        self.assertNotIn("dogbuild report . --output-dir", mutated,
            "Mutation should remove report command example")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed report command example")
        self.assertTrue(any("report_command_example" in f for f in failures),
            f"Failure should mention report_command_example. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring report command example. Failures: {failures}")

    def test_mutation_removal_of_report_safety_boundary_is_caught(self):
        """Negative control: contract fails when report safety boundary removed."""
        mutated = self.pristine_readme.replace("DogBuild does not copy project files, source code, or command output", "")
        self.assertNotIn("DogBuild does not copy project files, source code, or command output", mutated,
            "Mutation should remove report safety boundary")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed report safety boundary")
        self.assertTrue(any("report_safety_boundary" in f for f in failures),
            f"Failure should mention report_safety_boundary. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring report safety boundary. Failures: {failures}")

    def test_mutation_removal_of_report_output_choice_is_caught(self):
        """Negative control: contract fails when report output-choice statement removed."""
        mutated = self.pristine_readme.replace("Pick the output folder yourself", "")
        self.assertNotIn("Pick the output folder yourself", mutated,
            "Mutation should remove output-choice statement")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed output-choice statement")
        self.assertTrue(any("report_output_choice" in f for f in failures),
            f"Failure should mention report_output_choice. Got: {failures}")

        restored = self.pristine_readme
        is_valid, failures = self.contract.validate(restored)
        self.assertTrue(is_valid,
            f"Contract should pass after restoring output-choice statement. Failures: {failures}")

    def test_mutation_removal_of_connectivity_inventory_is_caught(self):
        """Negative control: contract fails when portal connectivity/inventory item removed."""
        mutated = self.pristine_readme.replace(
            "- [x] MCP portal connectivity and inventory documentation", "")
        self.assertNotIn("MCP portal connectivity and inventory documentation", mutated,
            "Mutation should remove connectivity/inventory item")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed portal connectivity/inventory item")
        
        self.assertIn("MCP portal connectivity and inventory documentation", self.pristine_readme,
            "Pristine should contain connectivity/inventory item")

    def test_mutation_removal_of_enforcement_identity_is_caught(self):
        """Negative control: contract fails when curation enforcement/identity item removed."""
        mutated = self.pristine_readme.replace(
            "- [ ] Curation enforcement and least-privilege access control (#169, #167)", "")
        self.assertNotIn("Curation enforcement and least-privilege access control", mutated,
            "Mutation should remove enforcement/identity item")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed curation enforcement/identity item")

    def test_mutation_removal_of_169_reference_is_caught(self):
        """Negative control: contract fails when #169 reference removed from enforcement item."""
        mutated = self.pristine_readme.replace("#169", "")
        self.assertNotIn("#169", mutated,
            "Mutation should remove #169 reference")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed #169 reference")

    def test_mutation_removal_of_167_reference_is_caught(self):
        """Negative control: contract fails when #167 reference removed from enforcement item."""
        mutated = self.pristine_readme.replace("#167", "")
        self.assertNotIn("#167", mutated,
            "Mutation should remove #167 reference")

        is_valid, failures = self.contract.validate(mutated)
        self.assertFalse(is_valid,
            "Contract should fail for removed #167 reference")

    def test_maturity_split_preserves_both_items(self):
        """Positive control: both portal items must be present and distinct."""
        self.assertIn("MCP portal connectivity and inventory documentation", self.pristine_readme,
            "README must include connectivity/inventory documentation item")
        self.assertIn("Curation enforcement and least-privilege access control (#169, #167)", 
            self.pristine_readme,
            "README must include enforcement/identity item with issue references")


if __name__ == "__main__":
    unittest.main()
