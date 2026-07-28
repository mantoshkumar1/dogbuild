"""Orientation Brief — one-screen "where am I / what's next", goal-driven, with
reviewer-gate awareness. A stale historical artifact is a WARNING, never a human
interruption. Human decision = yes only when a CURRENT choice blocks the next action:
a current VETO / NEEDS_HUMAN / policy mismatch, or a current declaration marked
NEEDS_HUMAN_SCOPE_CHANGE.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from . import (agentmode, declaration, gitutil, identity as identity_mod,
               plan as plan_mod, policy as policy_mod, review as review_mod, store)

_BLOCKING_GATE = {"STOP_VETO", "STOP_NEEDS_HUMAN", "STOP_POLICY_MISMATCH"}

# Autonomy states in which no task can be under way.
_IDLE_AUTONOMY = {"STOPPED", "INACTIVE", "COMPLETE", "PAUSED", "NOT_STARTED"}


def _head_of(git_state) -> str:
    """HEAD commit from a GitState dataclass or a plain dict."""
    if git_state is None:
        return ""
    if isinstance(git_state, dict):
        return git_state.get("head_commit") or ""
    return getattr(git_state, "head_commit", "") or ""


# Sentences that carry an actual verification result.
_RESULT_SENTENCE = re.compile(
    r"\d+\s*(pass|fail|passed|failed|passing|failing|error)"
    r"|\bexit\s+[0-9]+\b"
    r"|\b(pass|fail|green|red)\b\s*/\s*\d",
    re.I,
)

_EVIDENCE_BUDGET = 260


def _summarize_evidence(text: str) -> str:
    """Condense a long verification narrative to its test results.

    A declaration's `verified` field is written for a reviewer and can run to
    a paragraph. The one-line orientation needs the results, not the prose —
    and truncating would drop the numbers, which come last.
    """
    text = (text or "").strip()
    if not text or len(text) <= _EVIDENCE_BUDGET:
        return text or "unknown"

    sentences = [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]
    results = [s for s in sentences if _RESULT_SENTENCE.search(s)]
    if not results:
        return sentences[0][:_EVIDENCE_BUDGET].rstrip() + " …"

    out = ""
    for sentence in results:
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > _EVIDENCE_BUDGET:
            break
        out = candidate
    return out or results[0][:_EVIDENCE_BUDGET].rstrip() + " …"


def _checkpoint_at_head(state, head: str):
    """The newest checkpoint recorded at *head*, or None.

    Checkpoints carry the git state they were taken at. One taken at an older
    commit describes the past, however recently it was written.
    """
    if not head:
        return None
    matches = [cp for cp in state.checkpoints.values()
               if _head_of(cp.git_state) == head]
    if not matches:
        return None
    return max(matches, key=lambda cp: cp.created_at or "")


def _current_evidence(current_cp, decl_current, gc, last_cp, cp_is_stale):
    """Resolve (what_just_completed, tested, exact_next_action, source).

    Applies the order of truth. Falls back down the chain only when the higher
    source has nothing to say about the *current* commit.
    """
    if current_cp is not None:
        return (
            current_cp.summary,
            "; ".join(current_cp.tested) if current_cp.tested else "unknown",
            current_cp.next_safe_action or (gc.get("exact_next_action") if gc else "(none)"),
            "checkpoint at the current commit",
        )

    if decl_current:
        # A declaration is an agent claim, not canonical truth — but one made
        # AT the live commit is better evidence than a checkpoint made before it.
        return (
            decl_current.get("building") or "(no checkpoint at the current commit)",
            _summarize_evidence(decl_current.get("verified"))
            if decl_current.get("verified") else "not recorded for the current commit",
            decl_current.get("next_action")
            or (gc.get("exact_next_action") if gc else "(none)"),
            "agent declaration at the current commit",
        )

    if cp_is_stale:
        return (
            "(nothing recorded at the current commit)",
            "not recorded for the current commit",
            gc.get("exact_next_action") if gc else "(none)",
            "goal contract (no evidence at the current commit)",
        )

    if last_cp is not None:
        return (
            last_cp.summary,
            "; ".join(last_cp.tested) if last_cp.tested else "unknown",
            last_cp.next_safe_action or (gc.get("exact_next_action") if gc else "(none)"),
            "latest checkpoint",
        )

    return (
        "(no checkpoint yet)",
        "unknown",
        gc.get("exact_next_action") if gc else "(none)",
        "goal contract",
    )


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
    # A checkpoint recorded at an older commit is history, not current status.
    current_cp = _checkpoint_at_head(state, live["head_commit"])
    cp_is_stale = bool(last_cp) and current_cp is None

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
    if cp_is_stale:
        warnings.append(
            "The last checkpoint was recorded at "
            f"{(_head_of(last_cp.git_state) or 'an older commit')[:12]}, "
            f"before the current commit {(live['head_commit'] or '')[:12]}. "
            "It is shown as history; current status comes from newer evidence.")

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

    # Order of truth for "what is true right now", highest first:
    #   live git > checkpoint recorded AT the live HEAD > current declaration
    #   > goal contract > older checkpoints (history only).
    # A stale checkpoint must never supply current test evidence, the last
    # completed work, or the next action — that was the stale-orientation bug.
    completed, tested, exact_next, source = _current_evidence(
        current_cp, decl if decl_current else None, gc, last_cp, cp_is_stale)

    fields = {
        "product": gc["product_name"] if gc else ident.display_name,
        "core_repository": ident.display_name,
        "problem": gc["problem"] if gc else "(no goal contract)",
        "current_milestone": gc["current_milestone"] if gc else (
            state.scope.description if state.scope else "(not set)"),
        "what_just_completed": completed,
        "current_verified_state": (
            f"{live['branch']} @ {(live['head_commit'] or 'unborn')[:12]}, "
            f"worktree {'clean' if not live['dirty'] else 'dirty'} (ignoring .ai); "
            f"tests: {tested}"),
        "evidence_source": source,
        "checkpoint_is_historical": cp_is_stale,
        "historical_note": (
            f"Earlier checkpoint at "
            f"{_head_of(last_cp.git_state)[:12]}: {last_cp.summary}"
            if cp_is_stale and last_cp else ""),
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

    # Execution plan fields (if an active plan exists).
    ep = state.execution_plan
    if ep:
        fields["plan_current_task"] = ep.get("current_item", "(none)")
        fields["plan_completed"] = ep.get("completed", [])
        fields["plan_remaining"] = ep.get("remaining", [])
        fields["plan_blocked"] = ep.get("blocked", [])
        fields["plan_distance"] = plan_mod.distance_label(ep)
    else:
        fields["plan_current_task"] = None
        fields["plan_completed"] = []
        fields["plan_remaining"] = []
        fields["plan_blocked"] = []
        fields["plan_distance"] = "no active plan"

    # Is any task actually under way? A milestone that nothing is working
    # towards must not be presented as active merely because the Goal Contract
    # has not been manually revised. This reports status; it never changes the
    # product goal.
    autonomy_status = "INACTIVE"
    try:
        from . import autonomy as autonomy_mod
        autonomy_status = autonomy_mod.status(root).get("status", "INACTIVE")
    except Exception:
        pass

    no_active_task = (
        not fields["plan_current_task"]
        and str(autonomy_status).upper() in _IDLE_AUTONOMY
    )
    fields["autonomy_status"] = autonomy_status
    fields["has_active_task"] = not no_active_task
    fields["current_task"] = (
        fields["plan_current_task"] if not no_active_task else "None")
    fields["milestone_status"] = (
        "pending-next-milestone" if no_active_task else "active")
    fields["next_step"] = (
        "No task selected" if no_active_task else fields["exact_next_action"])

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
    )
    # Execution plan section (only when an active plan exists).
    if fields.get("plan_current_task") is not None:
        completed = fields.get("plan_completed", [])
        remaining = fields.get("plan_remaining", [])
        blocked = fields.get("plan_blocked", [])
        out += (
            f"Current task:         {fields['plan_current_task']}\n"
            f"Completed:            {', '.join(completed) if completed else '(none)'}\n"
            f"Remaining:            {', '.join(remaining) if remaining else '(none)'}\n"
            f"Blocked:              {', '.join(blocked) if blocked else '(none)'}\n"
            f"Distance to delivery: {fields.get('plan_distance', 'unknown')}\n"
        )
    out += (
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
