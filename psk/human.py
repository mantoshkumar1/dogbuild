"""Focused human-decision workflow — invoked only when a current choice genuinely
blocks the exact next action. The human never reconstructs prior context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import gitutil, identity as identity_mod, store
from .errors import StateNotFoundError, ValidationError
from .models import Event, EventType, SCHEMA_VERSION
from .util import new_uuid, now_iso


def _blocking_review(state):
    imp = [r for r in state.reviews.values()
           if r.get("status") == "imported" and r.get("verdict") in ("VETO", "NEEDS_HUMAN")]
    return sorted(imp, key=lambda r: r.get("imported_at", ""))[-1] if imp else None


def show(path: str) -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)
    rec = _blocking_review(state)
    if not rec:
        raise ValidationError("no human decision is currently required")
    gc = state.goal_contract or {}
    why = ("A reviewer VETO blocks the proposed action."
           if rec["verdict"] == "VETO" else
           "The reviewer flagged NEEDS_HUMAN: a human choice is required.")
    return {
        "why_needed": why,
        "decision_required": rec["question"],
        "options": ["approve the exact action", "reject the action", "change scope"],
        "consequences": ["proceed with the action", "stop and drop it",
                         "revise the goal contract (scope change)"],
        "recommendation": "reject unless the action is clearly safe and in-scope",
        "paused_step": rec["action"],
        "project": ident.display_name,
        "current_head": live["head_commit"],
        "goal_contract_revision": gc.get("revision"),
        "packet_id": rec["packet_id"],
    }


def decide(path: str, decision_file: str, actor: str = "human") -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)
    gc = state.goal_contract or {}

    dfile = Path(decision_file)
    if not dfile.exists():
        raise StateNotFoundError(f"human decision file not found: {decision_file}")
    d = {}
    for line in dfile.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            d[k.strip()] = v.strip()
    choice = d.get("choice")
    if not choice:
        raise ValidationError("human decision must specify a 'choice'")

    hid = new_uuid()
    seq = (max((r.get("seq", -1) for r in state.human_decisions.values()), default=-1) + 1)
    rec = {
        "id": hid, "seq": seq, "authority": "human",
        "question": d.get("question", ""), "choice": choice,
        "scope_changed": str(d.get("scope_changed", "false")).lower() == "true",
        "project_id": ident.project_id, "repository_id": ident.repository_id,
        "branch": live["branch"], "head_commit": live["head_commit"],
        "dirty_fingerprint": live["dirty_fingerprint"],
        "goal_contract_id": gc.get("goal_id"), "goal_contract_revision": gc.get("revision"),
        "timestamp": now_iso(),
    }
    state.human_decisions[hid] = rec
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, Event(new_uuid(), EventType.HUMAN_DECISION_RECORDED,
                                   now_iso(), actor, SCHEMA_VERSION,
                                   {"decision_id": hid, "choice": choice}))
    return rec


def resume_verify(path: str, decision_id: Optional[str] = None) -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)
    gc = state.goal_contract or {}

    if not state.human_decisions:
        raise ValidationError("no human decision recorded to verify")
    ordered = sorted(state.human_decisions.values(), key=lambda r: r.get("seq", 0))
    latest = ordered[-1]
    target = state.human_decisions.get(decision_id) if decision_id else latest
    if not target:
        raise ValidationError(f"unknown human decision '{decision_id}'")

    if decision_id and target.get("seq") != latest.get("seq"):
        result = "STOP_STALE_HUMAN_DECISION"
    elif target["project_id"] != ident.project_id or target["repository_id"] != ident.repository_id:
        result = "STOP_PROJECT_MISMATCH"
    elif target.get("goal_contract_id") != gc.get("goal_id") or target.get("goal_contract_revision") != gc.get("revision"):
        result = "STOP_GOAL_MISMATCH"
    elif target["head_commit"] != live["head_commit"] or _n(target["dirty_fingerprint"]) != _n(live["dirty_fingerprint"]):
        result = "STOP_STATE_CHANGED"
    else:
        result = "RESUME"
    return {"result": result, "decision_id": target["id"], "choice": target["choice"]}


def _n(v):
    if v is None:
        return None
    v = str(v).strip()
    return None if v.lower() in ("null", "none", "") else v


def _event(t, actor, **p):  # kept for symmetry; decide() inlines its event
    return Event(new_uuid(), t, now_iso(), actor, SCHEMA_VERSION, p)
