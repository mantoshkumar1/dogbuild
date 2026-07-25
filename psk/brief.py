"""Orientation Brief — one-screen "where am I / what's next", goal-driven, with
reviewer-gate awareness. A stale historical artifact is a WARNING, never a human
interruption. Human decision = yes only when a CURRENT choice blocks the next action:
a current VETO / NEEDS_HUMAN / policy mismatch, or a current declaration marked
NEEDS_HUMAN_SCOPE_CHANGE.
"""

from __future__ import annotations

from typing import List, Tuple

from . import (agentmode, declaration, gitutil, identity as identity_mod,
               policy as policy_mod, review as review_mod, store)

_BLOCKING_GATE = {"STOP_VETO", "STOP_NEEDS_HUMAN", "STOP_POLICY_MISMATCH"}


def build(path: str) -> Tuple[dict, List[str]]:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)
    mode = agentmode.load(root)
    decl = declaration.load_latest(root)
    gc = state.goal_contract
    try:
        pol = policy_mod.load(root)
        policy_label = f"{pol['policy_id']} v{pol['policy_version']}"
    except Exception:
        pol, policy_label = None, "(none)"

    last_cp = state.checkpoints.get(state.last_checkpoint_id) if state.last_checkpoint_id else None

    # Latest reviewer gate (if any imported decision).
    gate_result, pending_conditions = "none", 0
    try:
        g = review_mod.gate(root)
        gate_result = g["result"]
        if g["verdict"] == "APPROVE_WITH_CONDITIONS":
            pending_conditions = sum(1 for c in g.get("conditions", [])
                                     if isinstance(c, dict) and c.get("status") == "open")
    except Exception:
        pass

    decl_current = bool(decl) and decl.get("claimed_head") == live["head_commit"]

    warnings: List[str] = []
    if gate_result == "STOP_STATE_CHANGED":
        warnings.append("A past reviewer decision is for an older state "
                        "(historical, not currently relied upon).")
    if decl and not decl_current:
        warnings.append("The latest agent declaration references an older HEAD; "
                        "ignoring it in favour of live git evidence.")

    # Blocking (current) conditions only.
    human_needed, reason = False, ""
    if gate_result in _BLOCKING_GATE:
        human_needed = True
        reason = {"STOP_VETO": "a current reviewer VETO blocks the action",
                  "STOP_NEEDS_HUMAN": "the reviewer requires a human decision",
                  "STOP_POLICY_MISMATCH": "the reviewer policy no longer matches"}[gate_result]
    if decl_current:
        ga = decl.get("goal_alignment") or {}
        if (ga.get("status") == "NEEDS_HUMAN_SCOPE_CHANGE"
                and ga.get("goal_contract_revision") == (gc["revision"] if gc else None)):
            human_needed = True
            reason = ga.get("explanation") or "an agent flagged a scope change"

    goal_alignment = ((decl.get("goal_alignment") or {}).get("status")
                      if decl_current else "IN_SCOPE") or "IN_SCOPE"
    exact_next = (last_cp.next_safe_action if last_cp
                  else (gc.get("exact_next_action") if gc else "(none)"))
    tested = "; ".join(last_cp.tested) if last_cp and last_cp.tested else "unknown"

    fields = {
        "product": gc["product_name"] if gc else ident.display_name,
        "core_repository": ident.display_name,
        "problem": gc["problem"] if gc else "(no goal contract)",
        "current_milestone": gc["current_milestone"] if gc else (
            state.scope.description if state.scope else "(not set)"),
        "what_just_completed": last_cp.summary if last_cp else "(no checkpoint yet)",
        "current_verified_state": (
            f"{live['branch']} @ {(live['head_commit'] or 'unborn')[:12]}, "
            f"worktree {'clean' if not live['dirty'] else 'dirty'} (ignoring .ai); "
            f"tests: {tested}"),
        "exact_next_action": exact_next,
        "reviewer_policy": policy_label,
        "current_gate": gate_result,
        "pending_conditions": pending_conditions,
        "goal_alignment": goal_alignment,
        "parked_ideas": len(state.parked_ideas),
        "human_decision_needed": "yes" if human_needed else "no",
        "human_decision_reason": reason,
        "active_agent": mode.get("active_execution_agent"),
    }
    return fields, warnings


def render_text(fields: dict, warnings: List[str]) -> str:
    out = (
        f"Product:              {fields['product']}\n"
        f"Core repository:      {fields['core_repository']}\n"
        f"Problem:              {fields['problem']}\n"
        f"Current milestone:    {fields['current_milestone']}\n"
        f"What just completed:  {fields['what_just_completed']}\n"
        f"Current verified state: {fields['current_verified_state']}\n"
        f"Exact next action:    {fields['exact_next_action']}\n"
        f"Reviewer policy:      {fields['reviewer_policy']}\n"
        f"Current gate:         {fields['current_gate']}\n"
        f"Pending conditions:   {fields['pending_conditions']}\n"
        f"Goal alignment:       {fields['goal_alignment']}\n"
        f"Parked ideas:         {fields['parked_ideas']}\n"
        f"Warnings:             {len(warnings)}"
        + (" (see below)" if warnings else " (none)") + "\n"
        f"Human decision needed: {fields['human_decision_needed']}"
        + (f" — {fields['human_decision_reason']}" if fields['human_decision_reason'] else "")
        + "\n"
    )
    if warnings:
        out += "---\n" + "".join(f"  · {w}\n" for w in warnings)
    return out
