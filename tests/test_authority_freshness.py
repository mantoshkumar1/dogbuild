import unittest

from psk.authority_freshness import AuthorityClass, classify_authority, classify_referenced_sources, may_use_as_current_policy


class AuthorityFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.context = {
            "repository": "mantoshkumar1/pingstep",
            "default_branch": "main",
            "current_task_id": "217",
            "current_authoritative_source": "main:e922132",
            "requested_scope": "repository-policy",
        }

    def source(self, **overrides):
        data = {
            "source_id": "main:e922132", "repository": "mantoshkumar1/pingstep",
            "branch": "main", "commit_in_authoritative_history": True,
            "current_revision": True,
        }
        data.update(overrides)
        return data

    def test_pingstep_217_rejects_paused_240_future_handoff_command(self):
        future = self.source(source_id="pr-242:governance-handoff", branch="codex/240-prehandoff-capability-plan",
                             commit_in_authoritative_history=False, pr_state="open", task_id="240",
                             task_lifecycle="paused", paused=True, command="governance:handoff")
        decision = may_use_as_current_policy(future, self.context)
        self.assertEqual(decision["classification"], AuthorityClass.PAUSED_UNMERGED.value)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "capability_not_currently_implemented")
        self.assertEqual(decision["authoritative_replacement"], "main:e922132")

    def test_unmerged_restrictive_or_permissive_rule_never_changes_main_policy(self):
        for rule in ("deny_release", "allow_release"):
            candidate = self.source(source_id=rule, branch="feature/future", commit_in_authoritative_history=False,
                                    pr_state="open", task_id="240", task_authorized=True, policy=rule)
            decision = may_use_as_current_policy(candidate, self.context)
            self.assertFalse(decision["allowed"])
            self.assertEqual(decision["classification"], AuthorityClass.UNKNOWN_OR_CONFLICTING.value)

    def test_newer_paused_work_does_not_outrank_main(self):
        paused = self.source(source_id="newer-paused", branch="future", commit_in_authoritative_history=False,
                             pr_state="open", paused=True, observed_at="2999-01-01T00:00:00Z")
        current = self.source()
        self.assertFalse(may_use_as_current_policy(paused, self.context)["allowed"])
        self.assertTrue(may_use_as_current_policy(current, self.context)["allowed"])

    def test_newer_valid_merged_policy_wins_when_old_revision_is_superseded(self):
        old = self.source(source_id="main:old", current_revision=False, superseded=True)
        new = self.source(source_id="main:new")
        self.assertEqual(classify_authority(old, self.context)["classification"], AuthorityClass.SUPERSEDED_OR_HISTORICAL.value)
        self.assertTrue(may_use_as_current_policy(new, self.context)["allowed"])

    def test_exact_current_founder_promotion_can_promote_future_policy(self):
        future = self.source(source_id="future-promoted", branch="feature/future", commit_in_authoritative_history=False,
                             pr_state="open", explicit_promotion={"current": True, "authority": "founder",
                             "decision_id": "FD-1", "repository": "mantoshkumar1/pingstep", "scope": "repository-policy"})
        self.assertTrue(may_use_as_current_policy(future, self.context)["allowed"])

    def test_active_wip_is_task_local_not_repository_policy(self):
        wip = self.source(source_id="pr-253", branch="codex/217", commit_in_authoritative_history=False,
                          pr_state="open", task_id="217", task_authorized=True)
        self.assertFalse(may_use_as_current_policy(wip, self.context)["allowed"])
        task_context = {**self.context, "requested_scope": "task-local"}
        self.assertTrue(may_use_as_current_policy(wip, task_context)["allowed"])

    def test_conflict_fails_closed(self):
        conflict = self.source(conflicting_authority=True)
        self.assertFalse(may_use_as_current_policy(conflict, self.context)["allowed"])

    def test_handoff_claim_loses_to_live_current_main(self):
        claimed = self.source(source_id="handoff-claim", branch="future", commit_in_authoritative_history=False,
                              pr_state="open", paused=True, task_id="240")
        result = classify_referenced_sources([claimed], self.context)
        self.assertFalse(result["safe_to_use"])
        self.assertEqual(result["authoritative_replacement"], "main:e922132")

    def test_restart_and_retry_are_deterministic(self):
        source = self.source(source_id="paused", branch="future", commit_in_authoritative_history=False,
                             pr_state="open", paused=True)
        self.assertEqual(may_use_as_current_policy(source, self.context), may_use_as_current_policy(source, self.context))


if __name__ == "__main__":
    unittest.main()
