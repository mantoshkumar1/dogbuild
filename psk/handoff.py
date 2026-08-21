"""Generic agent handoff packet — one canonical format for Claude now, Codex later.

The packet carries project/repository identity so a receiving agent can verify it
belongs to the local repository before acting. The instruction originates from the
delegated reviewer (ChatGPT) and is transported through Project State Keeper; the
receiving agent must still verify the repository. Codex generation is supported and
tested, but Codex execution is not required in this slice.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from . import agentmode, authority_freshness, gitutil, identity as identity_mod, store
from .errors import ProjectMismatchError, StateNotFoundError, ValidationError
from .models import Event, EventType, SCHEMA_VERSION
from .util import new_uuid, now_iso

TARGETS = ("claude", "codex")

RESERVED_HUMAN_ACTIONS = [
    "push", "merge", "deploy", "publish", "delete data", "spend money",
    "external communication", "expose secrets", "production changes",
]


def _event(type_: EventType, actor: str, **payload) -> Event:
    return Event(event_id=new_uuid(), type=type_, timestamp=now_iso(), actor=actor,
                 schema_version=SCHEMA_VERSION, payload=payload)


def create(path: str, *, to_agent: str, task: str, from_agent: str = "claude",
           instruction_from: str = "chatgpt", acceptance: str = "",
           next_action: str = "", prohibited: Optional[List[str]] = None,
           authority_sources: Optional[List[dict]] = None,
           authority_context: Optional[dict] = None) -> tuple:
    root = gitutil.repo_root(path)
    if to_agent not in TARGETS:
        raise ValidationError(f"target must be one of {TARGETS}")
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    if not state.scope or not state.scope.scope_id:
        raise ValidationError("no active scope with an id; run set_scope first")
    git = gitutil.capture_git_state(root)
    prohibited = prohibited or RESERVED_HUMAN_ACTIONS

    authority_evaluation = None
    if authority_sources:
        if not authority_context:
            raise ValidationError("authority_context is required for referenced authority sources")
        authority_evaluation = authority_freshness.classify_referenced_sources(
            authority_sources, authority_context
        )
        if not authority_evaluation["safe_to_use"]:
            raise ValidationError("referenced authority source is not current policy")

    gc = state.goal_contract
    pid = new_uuid()
    ts = now_iso()
    rec = {
        "packet_id": pid,
        "packet_type": "agent_handoff",
        "project_id": ident.project_id,
        "repository_id": ident.repository_id,
        "goal_contract_id": gc["goal_id"] if gc else None,
        "goal_revision": gc["revision"] if gc else None,
        "goal_fingerprint": gc["fingerprint"] if gc else None,
        "branch": git["branch"],
        "head_commit": git["head_commit"],
        "diff_fingerprint": git["dirty_fingerprint"],
        "scope_id": state.scope.scope_id,
        "scope_revision": state.scope.version,
        "source_agent": from_agent,
        "target_agent": to_agent,
        "instruction_source": instruction_from,
        "task": task,
        "acceptance": acceptance,
        "next_action": next_action,
        "status": "outstanding",
        "created_at": ts,
    }
    if authority_evaluation is not None:
        rec["authority_source_evaluation"] = authority_evaluation
    state.handoffs[pid] = rec
    state.updated_at = ts
    store.save_state(root, state)
    store.append_event(root, _event(EventType.HANDOFF_CREATED, from_agent,
                                    packet_id=pid, target=to_agent))

    objective = state.objective.text if state.objective else "(not set)"
    fp = git["dirty_fingerprint"] or "null"
    last_cp = state.checkpoints.get(state.last_checkpoint_id) if state.last_checkpoint_id else None
    verified = "; ".join(last_cp.tested) if last_cp and last_cp.tested else "see latest checkpoint"

    md = f"""# DogBuild — agent handoff

> The instruction below originated from the **delegated reviewer AI (ChatGPT)** and
> was transported through DogBuild's Project State Keeper subsystem. The receiving agent ({to_agent})
> **must verify this repository** (identity, branch, HEAD, scope, freshness) before
> acting. This packet contains no repository source code.

```yaml
packet_type: agent_handoff
packet_id: {pid}
project_id: {ident.project_id}
repository_id: {ident.repository_id}
project_name: {ident.display_name}
repository_name: {ident.repository_name}
branch: {git['branch']}
head: {git['head_commit']}
diff_fingerprint: {fp}
scope_id: {state.scope.scope_id}
scope_revision: {state.scope.version}
goal_contract_id: {gc['goal_id'] if gc else 'null'}
goal_revision: {gc['revision'] if gc else 'null'}
goal_fingerprint: {gc['fingerprint'] if gc else 'null'}

source_agent:
  actor_type: ai_execution_agent
  actor_name: {from_agent}
  role: execution_agent

target_agent:
  actor_type: ai_execution_agent
  actor_name: {to_agent}
  role: execution_agent

instruction_source:
  actor_type: ai_reviewer
  actor_name: {instruction_from}
  role: delegated_strategy_authority

human_override: always
```

## Original objective
{objective}

## Current phase
{state.scope.description} (scope revision {state.scope.version})

## Exact delegated task
{task}

## What already exists
- {len(state.decisions)} decisions, {len(state.checkpoints)} checkpoints, {len(state.reviews)} reviews recorded
- branch `{git['branch']}` at `{git['head_commit']}`

## What was verified
{verified}

## Failures and resolutions
{'; '.join(last_cp.failures_resolved) if last_cp and last_cp.failures_resolved else 'None recorded at this checkpoint.'}

## Relevant files
The repository at its verified HEAD; `.ai/STATE.md` for the current projection.

## Prohibited actions
{', '.join(prohibited)}

## Acceptance criteria
{acceptance or 'The delegated task is completed exactly, tests pass, and the result is checkpointed.'}

## Exact next safe action
{next_action or task}

## Required completion declaration (the receiving agent must return this)
```text
What are we building?
What did I change?
What did I actually verify?
What failed and how was it resolved?
What remains incomplete?
What is the exact next safe action?
```
"""
    out_dir = Path(root) / store.AI_DIR / "exchange" / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pid}-{to_agent}-handoff.md"
    store.atomic_write(out_path, md)
    store.atomic_write(Path(root) / store.AI_DIR / "HANDOFF.md", md)  # latest handoff
    return pid, out_path


def latest_outstanding(state) -> Optional[dict]:
    out = [h for h in state.handoffs.values() if h.get("status") == "outstanding"]
    if not out:
        return None
    return sorted(out, key=lambda h: h.get("created_at", ""))[-1]


def show(path: str) -> dict:
    root = gitutil.repo_root(path)
    state = store.load_state(root)
    rec = latest_outstanding(state)
    if rec is None:
        # fall back to most recent handoff of any status
        if not state.handoffs:
            raise StateNotFoundError("no handoff recorded")
        rec = sorted(state.handoffs.values(), key=lambda h: h.get("created_at", ""))[-1]
    return rec


def consume(path: str, *, packet_id: Optional[str] = None,
            as_agent: Optional[str] = None) -> dict:
    """Receiving agent validates + consumes a handoff. Rejects stale/mismatched."""
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    live = gitutil.capture_git_state(root)

    if packet_id:
        rec = state.handoffs.get(packet_id)
        if not rec:
            raise ValidationError(f"unknown handoff packet '{packet_id}'")
    else:
        rec = latest_outstanding(state)
        if rec is None:
            raise ValidationError("no outstanding handoff to consume")
    if rec.get("status") != "outstanding":
        raise ValidationError(f"handoff '{rec['packet_id']}' is not outstanding")

    if rec["project_id"] != ident.project_id:
        raise ProjectMismatchError("handoff project_id does not match this repository")
    if rec["repository_id"] != ident.repository_id:
        raise ProjectMismatchError("handoff repository_id does not match this repository")
    if as_agent and as_agent != rec["target_agent"]:
        raise ProjectMismatchError(
            f"this agent ({as_agent}) is not the handoff target ({rec['target_agent']})")
    if rec["branch"] != live["branch"]:
        raise ValidationError("handoff branch does not match the live repository")
    if rec["head_commit"] != live["head_commit"]:
        raise ValidationError("handoff is stale: HEAD has moved since it was created")
    if state.scope and rec["scope_id"] != state.scope.scope_id:
        raise ValidationError("handoff scope_id does not match the current scope")

    rec["status"] = "consumed"
    rec["consumed_at"] = now_iso()
    rec["consumed_by"] = as_agent or rec["target_agent"]
    state.handoffs[rec["packet_id"]] = rec
    state.updated_at = now_iso()
    store.save_state(root, state)
    agentmode.set_active_agent(root, rec["target_agent"])
    store.append_event(root, _event(EventType.HANDOFF_CONSUMED, rec["target_agent"],
                                    packet_id=rec["packet_id"]))
    return rec
