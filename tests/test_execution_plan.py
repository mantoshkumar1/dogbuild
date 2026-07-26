"""Tests for Execution Plan Sync — bounded plans, persistence, brief integration."""

import os
import shutil
import tempfile
import unittest

from psk import brief as brief_mod, declaration, gitutil, plan, registry, store
from psk.errors import StateNotFoundError, ValidationError
from tests._helpers import cleanup, make_repo, import_min_genesis


def _setup_repo():
    """Create a git repo with DogBuild initialized and a genesis imported."""
    regdir = tempfile.mkdtemp(prefix="psk-reg-")
    old_reg = os.environ.get(registry.REGISTRY_ENV)
    os.environ[registry.REGISTRY_ENV] = regdir
    d = make_repo(with_commit=True)
    root = gitutil.repo_root(d)

    # Import CLI to get init, then genesis
    import contextlib, io
    from psk import __main__ as cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.main(["init", root, "--objective", "test objective"])
    import_min_genesis(root)
    return d, root, regdir, old_reg


def _teardown_repo(d, regdir, old_reg):
    if old_reg is None:
        os.environ.pop(registry.REGISTRY_ENV, None)
    else:
        os.environ[registry.REGISTRY_ENV] = old_reg
    shutil.rmtree(regdir, ignore_errors=True)
    cleanup(d)


class TestExecutionPlanBounded(unittest.TestCase):
    """A complex task receives a bounded execution plan; simple tasks do not."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_complex_task_gets_bounded_plan(self):
        """A plan with 3-7 steps is created and bounded."""
        p = plan.create(
            self.root,
            stage="personal-alpha-refinement",
            current_item="update-state-model",
            remaining=["update-skill", "add-tests", "run-verification"],
            exact_next_action="update the state model",
        )
        self.assertEqual(p["stage"], "personal-alpha-refinement")
        self.assertEqual(p["current_item"], "update-state-model")
        self.assertEqual(len(p["remaining"]), 3)
        # Total steps = 1 (current) + 0 (completed) + 3 (remaining) = 4
        self.assertLessEqual(
            1 + len(p["completed"]) + len(p["remaining"]),
            plan.MAX_STEPS,
        )

    def test_simple_task_no_plan_needed(self):
        """Simple tasks should not have a plan — verify no plan exists by default."""
        loaded = plan.load(self.root)
        self.assertIsNone(loaded)

    def test_plan_rejects_excessive_steps(self):
        """Plans over MAX_STEPS are rejected."""
        with self.assertRaises(ValidationError):
            plan.create(
                self.root,
                stage="test",
                current_item="step-0",
                remaining=[f"step-{i}" for i in range(1, plan.MAX_STEPS + 1)],
            )


class TestPlanDerivesFromAcceptance(unittest.TestCase):
    """Plan derives from active acceptance criteria."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_plan_stage_matches_milestone(self):
        """The plan's stage field should reflect the current milestone context."""
        p = plan.create(
            self.root,
            stage="personal-alpha-refinement",
            current_item="implement-execution-plan-sync",
            remaining=["update-skill", "add-tests"],
            exact_next_action="extend state model with execution_plan field",
        )
        self.assertEqual(p["stage"], "personal-alpha-refinement")
        self.assertIn("implement", p["current_item"])


class TestOptionalIdeaParked(unittest.TestCase):
    """Optional idea is parked rather than added to the active plan."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_plan_contains_only_milestone_work(self):
        """After creating a plan, an unrelated idea should not appear in remaining."""
        plan.create(
            self.root,
            stage="test",
            current_item="task-a",
            remaining=["task-b", "task-c"],
        )
        # Simulate: optional idea arrives → we update remaining WITHOUT the idea
        plan.update(
            self.root,
            remaining=["task-b", "task-c"],  # same — idea was parked, not added
        )
        loaded = plan.load(self.root)
        self.assertNotIn("optional-dashboard", loaded["remaining"])
        self.assertEqual(loaded["remaining"], ["task-b", "task-c"])


class TestMeaningfulProgressPersisted(unittest.TestCase):
    """Meaningful progress is persisted; session-local detail is not over-persisted."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_progress_survives_reload(self):
        """Completed steps persist across load cycles."""
        plan.create(
            self.root,
            stage="test",
            current_item="step-b",
            completed=["step-a"],
            remaining=["step-c"],
            exact_next_action="do step-b",
        )
        loaded = plan.load(self.root)
        self.assertEqual(loaded["completed"], ["step-a"])
        self.assertEqual(loaded["current_item"], "step-b")

    def test_update_adds_completed(self):
        """update() appends to completed list."""
        plan.create(
            self.root, stage="test", current_item="step-a",
            remaining=["step-b"],
        )
        plan.update(
            self.root,
            add_completed=["step-a"],
            current_item="step-b",
            remaining=[],
            exact_next_action="finish step-b",
        )
        loaded = plan.load(self.root)
        self.assertIn("step-a", loaded["completed"])
        self.assertEqual(loaded["current_item"], "step-b")

    def test_clear_removes_plan(self):
        """clear() removes the plan entirely."""
        plan.create(self.root, stage="test", current_item="x")
        plan.clear(self.root)
        self.assertIsNone(plan.load(self.root))

    def test_update_without_plan_raises(self):
        """Updating a non-existent plan raises StateNotFoundError."""
        with self.assertRaises(StateNotFoundError):
            plan.update(self.root, current_item="x")


class TestBriefShowsPlanFields(unittest.TestCase):
    """Orientation Brief shows current/completed/remaining/blocked."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_brief_includes_plan_fields_when_active(self):
        plan.create(
            self.root,
            stage="test",
            current_item="update-skill",
            completed=["update-model"],
            remaining=["add-tests"],
            blocked=[],
        )
        fields, _ = brief_mod.build(self.root)
        self.assertEqual(fields["plan_current_task"], "update-skill")
        self.assertEqual(fields["plan_completed"], ["update-model"])
        self.assertEqual(fields["plan_remaining"], ["add-tests"])
        self.assertEqual(fields["plan_blocked"], [])
        self.assertIn("remaining", fields["plan_distance"])

    def test_brief_shows_no_plan_when_inactive(self):
        fields, _ = brief_mod.build(self.root)
        self.assertIsNone(fields["plan_current_task"])
        self.assertEqual(fields["plan_distance"], "no active plan")

    def test_brief_text_renders_plan_section(self):
        plan.create(
            self.root,
            stage="test",
            current_item="update-skill",
            completed=["update-model"],
            remaining=["add-tests"],
        )
        fields, warnings = brief_mod.build(self.root)
        text = brief_mod.render_text(fields, warnings)
        self.assertIn("Current task:", text)
        self.assertIn("update-skill", text)
        self.assertIn("Completed:", text)
        self.assertIn("update-model", text)
        self.assertIn("Distance to delivery:", text)


class TestStateQueryDoesNotAlter(unittest.TestCase):
    """State query does not alter execution plan."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_brief_build_is_read_only(self):
        """Building the brief does not change the execution plan."""
        plan.create(
            self.root, stage="test", current_item="step-a",
            remaining=["step-b"],
        )
        before = plan.load(self.root)
        # Simulate a state query by building the brief
        brief_mod.build(self.root)
        after = plan.load(self.root)
        self.assertEqual(before["current_item"], after["current_item"])
        self.assertEqual(before["remaining"], after["remaining"])
        self.assertEqual(before["completed"], after["completed"])


class TestContinuationRecoversPlan(unittest.TestCase):
    """Continuation recovers the current plan from persistent state."""

    def setUp(self):
        self.d, self.root, self.regdir, self._old_reg = _setup_repo()

    def tearDown(self):
        _teardown_repo(self.d, self.regdir, self._old_reg)

    def test_plan_survives_state_reload(self):
        """A plan persisted in state.json survives a full reload cycle."""
        plan.create(
            self.root, stage="alpha", current_item="task-2",
            completed=["task-1"], remaining=["task-3"],
            exact_next_action="do task-2",
        )
        # Reload state from disk (simulates a fresh session)
        state = store.load_state(self.root)
        ep = state.execution_plan
        self.assertIsNotNone(ep)
        self.assertEqual(ep["current_item"], "task-2")
        self.assertEqual(ep["completed"], ["task-1"])
        self.assertEqual(ep["remaining"], ["task-3"])
        self.assertEqual(ep["exact_next_action"], "do task-2")


class TestSkillContainsPlanRules(unittest.TestCase):
    """Claude skill contains the delivery-first and plan-sync rules."""

    def test_skill_mentions_execution_plan(self):
        from pathlib import Path
        skill_path = Path(__file__).resolve().parent.parent / "psk" / "skills" / "dogbuild" / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("Execution plan sync", content)
        self.assertIn("delivery", content.lower())

    def test_skill_mentions_scope_protection(self):
        from pathlib import Path
        skill_path = Path(__file__).resolve().parent.parent / "psk" / "skills" / "dogbuild" / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("Scope protection", content)
        self.assertIn("park", content.lower())

    def test_skill_mentions_session_recovery(self):
        from pathlib import Path
        skill_path = Path(__file__).resolve().parent.parent / "psk" / "skills" / "dogbuild" / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("Session recovery", content)
        self.assertIn("execution_plan", content)


class TestDistanceLabel(unittest.TestCase):
    """Distance-to-delivery labels use bounded language, no percentages."""

    def test_no_plan(self):
        self.assertEqual(plan.distance_label(None), "no active plan")

    def test_blocked(self):
        self.assertEqual(
            plan.distance_label({"blocked": ["waiting"]}),
            "blocked",
        )

    def test_complete(self):
        self.assertEqual(
            plan.distance_label({"current_item": "", "remaining": []}),
            "complete",
        )

    def test_current_step_only(self):
        self.assertEqual(
            plan.distance_label({"current_item": "x", "remaining": []}),
            "current step",
        )

    def test_one_remaining(self):
        self.assertEqual(
            plan.distance_label({"current_item": "x", "remaining": ["y"]}),
            "one step remaining",
        )

    def test_multiple_remaining(self):
        label = plan.distance_label(
            {"current_item": "x", "remaining": ["y", "z"]}
        )
        self.assertIn("2 steps remaining", label)


if __name__ == "__main__":
    unittest.main()
