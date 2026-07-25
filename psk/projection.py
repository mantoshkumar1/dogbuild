"""Deterministic Markdown projection of the canonical state.

Given the same ProjectState, render_markdown always returns the same string
(stable ordering, no timestamps invented here). It clearly separates *current
facts* (the live snapshot) from *historical claims* (checkpoints), per the
quality standard.
"""

from __future__ import annotations

from .models import ProjectState


def _bullets(items) -> str:
    items = list(items)
    if not items:
        return "_(none)_\n"
    return "".join(f"- {x}\n" for x in items)


def render_markdown(state: ProjectState) -> str:
    lines: list = []
    a = lines.append

    a("# Project State (current)\n")
    a("\n> Generated from `.ai/state.json`. Current facts only; history lives in "
      "`.ai/events.jsonl` and the Checkpoints section below.\n")

    a(f"\n- **Schema version:** {state.schema_version}\n")
    a(f"- **PSK id:** `{state.identity.psk_uuid}`\n")
    a(f"- **Repo root:** `{state.identity.root}`\n")
    if state.identity.remotes:
        a(f"- **Remotes:** {', '.join(f'`{r}`' for r in state.identity.remotes)}\n")
    a(f"- **State updated:** {state.updated_at}\n")

    a("\n## Objective\n")
    if state.objective:
        a(f"\n(v{state.objective.version}, set {state.objective.set_at})\n\n")
        a(f"{state.objective.text}\n")
    else:
        a("\n_(not set)_\n")

    a("\n## Active scope\n")
    if state.scope:
        a(f"\n(v{state.scope.version}, set {state.scope.set_at})\n\n")
        a(f"{state.scope.description}\n")
    else:
        a("\n_(not set)_\n")

    a("\n## Git state (as last captured)\n")
    g = state.git_state
    a(f"\n- **Branch:** `{g.branch}`{' (detached)' if g.detached else ''}\n")
    a(f"- **HEAD:** `{g.head_commit or 'unborn'}`\n")
    a(f"- **Worktree:** {'dirty' if g.dirty else 'clean'}"
      f"{f' (fingerprint `{g.dirty_fingerprint[:12]}…`)' if g.dirty_fingerprint else ''}\n")
    a(f"- **Captured:** {g.captured_at}\n")

    a("\n## Requested items\n\n")
    if state.items:
        for iid in sorted(state.items):
            it = state.items[iid]
            a(f"- **[{it.status.value}]** {it.description} "
              f"(`{iid}`, updated {it.updated_at})\n")
    else:
        a("_(none)_\n")

    a("\n## Reserved human-only approvals\n\n")
    a(_bullets(sorted(ra.value for ra in state.reserved_approvals)))

    a("\n## Decisions (records)\n\n")
    if state.decisions:
        for did in sorted(state.decisions):
            d = state.decisions[did]
            a(f"- **{d.verdict.value}** by {d.authority.value} on "
              f"`{d.binding.action}` (commit `{(d.binding.head_commit or 'n/a')[:8]}`, "
              f"`{did}`)\n")
    else:
        a("_(none)_\n")

    a("\n## Checkpoints (historical claims)\n\n")
    if state.checkpoints:
        for cid in sorted(state.checkpoints, key=lambda k: state.checkpoints[k].created_at):
            c = state.checkpoints[cid]
            a(f"### {c.created_at} — {c.summary}\n\n")
            a(f"- Implemented:\n")
            for x in c.implemented:
                a(f"  - {x}\n")
            a(f"- Next safe action: {c.next_safe_action or '_(none)_'}\n")
            if c.unresolved_risks:
                a("- Unresolved risks:\n")
                for x in c.unresolved_risks:
                    a(f"  - {x}\n")
            a("\n")
    else:
        a("_(none)_\n")

    return "".join(lines)
