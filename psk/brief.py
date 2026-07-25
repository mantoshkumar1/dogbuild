"""Orientation Brief — answers, for the human owner in <20s:
"Where am I, what am I building, what just happened, and what happens next?"

Combines live git evidence, canonical state, the latest agent declaration, the
latest valid reviewer decision, and the original objective — using this truth
order (highest first) and SHOWING conflicts rather than silently merging them:

    live repository evidence
    > current valid reviewer decision
    > canonical Project State Keeper state
    > latest execution-agent declaration
    > older summaries
"""

from __future__ import annotations

from typing import List, Tuple

from . import agentmode, declaration, gitutil, handoff as handoff_mod, identity as identity_mod, store


def build(path: str) -> Tuple[dict, List[str]]:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)
    mode = agentmode.load(root)
    decl = declaration.load_latest(root)

    last_cp = state.checkpoints.get(state.last_checkpoint_id) if state.last_checkpoint_id else None
    imported = [r for r in state.reviews.values() if r.get("status") == "imported"]
    latest_review = sorted(imported, key=lambda r: r.get("imported_at", ""))[-1] if imported else None
    pending_reviews = [r for r in state.reviews.values() if r.get("status") == "pending"]
    outstanding_handoff = handoff_mod.latest_outstanding(state)

    # Conflict detection across truth sources (never silently merged).
    conflicts: List[str] = []
    if latest_review and latest_review.get("head_commit") != live["head_commit"]:
        conflicts.append("Latest reviewer decision was made for an older commit "
                         "(no longer current) — re-request before relying on it.")
    if decl and decl.get("claimed_head") != live["head_commit"]:
        conflicts.append("Latest agent declaration references a different HEAD than "
                         "the live repository — trust git, not the declaration.")

    human_needed = bool(pending_reviews) or bool(conflicts)

    if outstanding_handoff:
        waiting = (f"outstanding handoff to {outstanding_handoff['target_agent']}: "
                   f"{outstanding_handoff['task'][:80]}")
    elif pending_reviews:
        waiting = f"{len(pending_reviews)} review(s) awaiting a ChatGPT decision"
    elif last_cp:
        waiting = last_cp.next_safe_action
    else:
        waiting = "(nothing recorded)"

    fields = {
        "project": ident.display_name,
        "original_objective": state.objective.text if state.objective else "(not set)",
        "current_phase": state.scope.description if state.scope else "(not set)",
        "what_just_completed": last_cp.summary if last_cp else "(no checkpoint yet)",
        "current_verified_state": (
            f"{live['branch']} @ {(live['head_commit'] or 'unborn')[:12]}, "
            f"worktree {'clean' if not live['dirty'] else 'dirty'} (ignoring .ai)"
        ),
        "what_is_waiting": waiting,
        "exact_next_action": last_cp.next_safe_action if last_cp else "(none recorded)",
        "why_next": ("Recorded as the next safe action in the latest verified "
                     "checkpoint." if last_cp else "No checkpoint yet."),
        "human_decision_needed": "yes" if human_needed else "no",
        "active_agent": mode.get("active_execution_agent"),
        "codex_status": mode.get("codex_status"),
        "reviewer": mode.get("review_authority"),
        "last_reviewer_decision": (f"{latest_review['verdict']} on "
                                   f"{(latest_review['head_commit'] or '')[:12]}"
                                   if latest_review else "none"),
    }
    return fields, conflicts


def render_text(fields: dict, conflicts: List[str]) -> str:
    out = (
        f"Project:              {fields['project']}\n"
        f"Original objective:   {fields['original_objective']}\n"
        f"Current phase:        {fields['current_phase']}\n"
        f"What just completed:  {fields['what_just_completed']}\n"
        f"Current verified state: {fields['current_verified_state']}\n"
        f"What is waiting:      {fields['what_is_waiting']}\n"
        f"Exact next action:    {fields['exact_next_action']}\n"
        f"Why that action is next: {fields['why_next']}\n"
        f"Human decision needed: {fields['human_decision_needed']}\n"
        f"---\n"
        f"Active agent: {fields['active_agent']} "
        f"(codex: {fields['codex_status']}) | reviewer: {fields['reviewer']} | "
        f"last reviewer decision: {fields['last_reviewer_decision']}\n"
    )
    if conflicts:
        out += "\n⚠ Source conflicts (shown, not merged):\n"
        for c in conflicts:
            out += f"  - {c}\n"
    return out
