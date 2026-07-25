"""Orientation Brief — one-screen answer to "where am I / what's next" for the
human owner, driven by the active Goal Contract.

Truth order (highest first), conflicts SHOWN not merged:
    live repository evidence > current valid reviewer decision > canonical state
    > latest execution-agent declaration > older summaries

Human-decision rule (fixed): a stale historical artifact produces a WARNING, never
a `Human decision needed: yes`. Human decision is `yes` only when a *current*
unresolved choice blocks the exact next action (a current agent declaration marked
`NEEDS_HUMAN_SCOPE_CHANGE` against the current goal revision).
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
    gc = state.goal_contract

    last_cp = state.checkpoints.get(state.last_checkpoint_id) if state.last_checkpoint_id else None
    imported = [r for r in state.reviews.values() if r.get("status") == "imported"]
    latest_review = sorted(imported, key=lambda r: r.get("imported_at", ""))[-1] if imported else None

    decl_current = bool(decl) and decl.get("claimed_head") == live["head_commit"]

    # Warnings — informational only; they NEVER set human_decision_needed.
    warnings: List[str] = []
    if latest_review and latest_review.get("head_commit") != live["head_commit"]:
        warnings.append("A past reviewer decision is for an older commit "
                        "(historical, not currently relied upon).")
    if decl and not decl_current:
        warnings.append("The latest agent declaration references an older HEAD; "
                        "ignoring it in favour of live git evidence.")

    # Human decision is required only for a CURRENT, blocking, unresolved choice.
    human_needed = False
    reason = ""
    if decl_current:
        ga = decl.get("goal_alignment") or {}
        cur_rev = gc["revision"] if gc else None
        if (ga.get("status") == "NEEDS_HUMAN_SCOPE_CHANGE"
                and ga.get("goal_contract_revision") == cur_rev):
            human_needed = True
            reason = ga.get("explanation") or "an agent flagged a scope change"

    exact_next = (last_cp.next_safe_action if last_cp
                  else (gc.get("exact_next_action") if gc else "(none recorded)"))
    tested = "; ".join(last_cp.tested) if last_cp and last_cp.tested else "unknown"

    fields = {
        "product": gc["product_name"] if gc else ident.display_name,
        "core_repository": ident.display_name,
        "problem": gc["problem"] if gc else "(no goal contract imported)",
        "current_milestone": gc["current_milestone"] if gc else (
            state.scope.description if state.scope else "(not set)"),
        "what_just_completed": last_cp.summary if last_cp else "(no checkpoint yet)",
        "current_verified_state": (
            f"{live['branch']} @ {(live['head_commit'] or 'unborn')[:12]}, "
            f"worktree {'clean' if not live['dirty'] else 'dirty'} (ignoring .ai); "
            f"tests: {tested}"),
        "exact_next_action": exact_next,
        "why_next": ("Recorded as the next safe action in the latest verified "
                     "checkpoint." if last_cp else
                     "First action from the approved goal contract." if gc else "n/a"),
        "parked_ideas": len(state.parked_ideas),
        "human_decision_needed": "yes" if human_needed else "no",
        "human_decision_reason": reason,
        "goal_revision": gc["revision"] if gc else None,
        "active_agent": mode.get("active_execution_agent"),
        "reviewer": mode.get("review_authority"),
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
        f"Why it is next:       {fields['why_next']}\n"
        f"Parked ideas:         {fields['parked_ideas']}\n"
        f"Warnings:             {len(warnings)}"
        + (" (see below)" if warnings else " (none)") + "\n"
        f"Human decision needed: {fields['human_decision_needed']}"
        + (f" — {fields['human_decision_reason']}" if fields['human_decision_reason'] else "")
        + "\n"
    )
    if warnings:
        out += "---\n"
        for w in warnings:
            out += f"  · {w}\n"
    return out
