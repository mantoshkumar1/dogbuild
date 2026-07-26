"""Execution Plan Sync — lightweight, session-to-session progress tracking.

An execution plan is a short (3–7 step) list derived from the active Goal
Contract, milestone, and acceptance criteria.  It lives in `state.execution_plan`
as a plain dict and is persisted through the existing state model at meaningful
boundaries (checkpoint, commit, verification, pause, session rollover, task
completion).

Session-local detail (a Claude todo list inside one session) is NOT persisted.
Only decision-relevant progress is written: completed steps, current step,
remaining acceptance criteria, blockers, and the exact next safe action.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from . import store
from .models import Event, EventType, SCHEMA_VERSION
from .util import new_uuid, now_iso


# Maximum steps allowed in an execution plan (scope protection).
MAX_STEPS = 10


def create(
    root: str,
    *,
    stage: str,
    current_item: str,
    completed: Optional[List[str]] = None,
    remaining: Optional[List[str]] = None,
    blocked: Optional[List[str]] = None,
    exact_next_action: str = "",
    actor: str = "claude",
) -> dict:
    """Create or replace the execution plan in persistent state.

    Returns the plan dict.
    """
    plan = {
        "stage": stage,
        "current_item": current_item,
        "completed": list(completed or []),
        "remaining": list(remaining or []),
        "blocked": list(blocked or []),
        "exact_next_action": exact_next_action,
        "updated_at": now_iso(),
    }
    total = 1 + len(plan["completed"]) + len(plan["remaining"])
    if total > MAX_STEPS:
        from .errors import ValidationError
        raise ValidationError(
            f"execution plan has {total} steps (max {MAX_STEPS}); "
            "keep plans bounded"
        )
    state = store.load_state(root)
    state.execution_plan = plan
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, Event(
        event_id=new_uuid(), type=EventType.CHECKPOINT_CREATED,
        timestamp=now_iso(), actor=actor, schema_version=SCHEMA_VERSION,
        payload={"execution_plan_updated": True,
                 "current_item": current_item}))
    return plan


def update(
    root: str,
    *,
    current_item: Optional[str] = None,
    add_completed: Optional[List[str]] = None,
    remaining: Optional[List[str]] = None,
    blocked: Optional[List[str]] = None,
    exact_next_action: Optional[str] = None,
    actor: str = "claude",
) -> dict:
    """Update the current execution plan in place.

    Only provided fields are changed.  Returns the updated plan dict.
    Raises StateNotFoundError if no plan exists.
    """
    state = store.load_state(root)
    plan = state.execution_plan
    if plan is None:
        from .errors import StateNotFoundError
        raise StateNotFoundError("no execution plan to update")

    if add_completed:
        plan["completed"] = plan.get("completed", []) + list(add_completed)
    if current_item is not None:
        plan["current_item"] = current_item
    if remaining is not None:
        plan["remaining"] = list(remaining)
    if blocked is not None:
        plan["blocked"] = list(blocked)
    if exact_next_action is not None:
        plan["exact_next_action"] = exact_next_action
    plan["updated_at"] = now_iso()

    state.execution_plan = plan
    state.updated_at = now_iso()
    store.save_state(root, state)
    return plan


def load(root: str) -> Optional[dict]:
    """Load the current execution plan, or None if none exists."""
    state = store.load_state(root)
    return state.execution_plan


def clear(root: str, *, actor: str = "claude") -> None:
    """Remove the execution plan (task complete or cancelled)."""
    state = store.load_state(root)
    state.execution_plan = None
    state.updated_at = now_iso()
    store.save_state(root, state)


def distance_label(plan: Optional[dict]) -> str:
    """Human-readable distance-to-delivery label (no percentages)."""
    if plan is None:
        return "no active plan"
    if plan.get("blocked"):
        return "blocked"
    remaining = plan.get("remaining", [])
    current = plan.get("current_item", "")
    if not remaining and not current:
        return "complete"
    if not remaining:
        return "current step"
    if len(remaining) == 1:
        return "one step remaining"
    return "verification remaining" if remaining == ["run-full-verification"] \
        else f"{len(remaining)} steps remaining"
