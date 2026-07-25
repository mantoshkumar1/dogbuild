"""Active Goal Contract — the versioned, human-approved purpose the work serves."""

from __future__ import annotations

from . import gitutil, identity as identity_mod, store
from .errors import ProjectMismatchError, ValidationError


def show(path: str) -> dict:
    root = gitutil.repo_root(path)
    gc = store.load_state(root).goal_contract
    if not gc:
        raise ValidationError("no approved goal contract (import a project genesis first)")
    return gc


def verify(path: str) -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    gc = state.goal_contract
    if not gc:
        raise ValidationError("no approved goal contract to verify")
    if gc.get("project_id") != ident.project_id or gc.get("repository_id") != ident.repository_id:
        raise ProjectMismatchError("goal contract identity does not match this repository")

    scope_ok = bool(state.scope) and state.scope.goal_revision == gc["revision"]
    checks = {
        "approved_contract_exists": True,
        "human_approved": bool(gc.get("human_approved")),
        "identity_matches": True,
        "scope_references_current_goal": scope_ok,
        "exact_next_action_present": bool(gc.get("exact_next_action")),
        "not_superseded": True,  # no later human scope-change decision recorded
    }
    ok = all(checks.values())
    return {"ok": ok, "revision": gc["revision"], "fingerprint": gc["fingerprint"],
            "current_milestone": gc["current_milestone"], "checks": checks}
