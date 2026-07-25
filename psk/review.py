"""Day 3 vertical slice: one review round-trip, APPROVE-only, agent-neutral.

    request  -> ChatGPT packet (Markdown)
    import   -> validate + record a returned decision (no execution)
    gate     -> APPROVE + still-current  => PROCEED

The protocol is agent-neutral: the packet/decision carry project & repository
identity, not an agent name (Codex/Cursor slot in later without redesign). Only
APPROVE is wired; other outcomes are reserved (see docs). Nothing here executes the
action or performs any irreversible operation.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from . import gitutil, identity as identity_mod, store
from .errors import ProjectMismatchError, StateNotFoundError, ValidationError
from .models import (
    Authority,
    Decision,
    DecisionBinding,
    Event,
    EventType,
    Verdict,
    SCHEMA_VERSION,
    to_jsonable,
)
from .util import new_uuid, now_iso

RESERVED_HUMAN_ACTIONS = [
    "push", "merge", "deploy", "publish", "delete data", "spend money",
    "external communication", "expose secrets", "production changes",
]

RESPONSE_TEMPLATE = """```yaml
schema_version: 1
packet_type: review_decision
packet_id: {packet_id}
project_id: {project_id}
repository_id: {repository_id}
reviewed_branch: {branch}
reviewed_head: {head}
reviewed_diff_fingerprint: {fingerprint}
scope_id: {scope_id}
scope_revision: {scope_revision}
reviewer: chatgpt
decision: APPROVE
confidence: low|medium|high
reviewed_at: <ISO-8601>
```

## Decision
APPROVE

## Rationale
<why>

## Conditions
None

## Required next action
<the exact approved action>
"""


def _live(root: str) -> dict:
    return gitutil.capture_git_state(root)


def _event(type_: EventType, actor: str, **payload) -> Event:
    return Event(event_id=new_uuid(), type=type_, timestamp=now_iso(), actor=actor,
                 schema_version=SCHEMA_VERSION, payload=payload)


# --------------------------------------------------------------------------- #
# request
# --------------------------------------------------------------------------- #
def build_review_request(path: str, *, question: str, action: str,
                         recommendation: str = "", against: str = "",
                         evidence: str = "", uncertainty: str = "",
                         actor: str = "claude") -> Path:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    git = _live(root)
    if not state.scope or not state.scope.scope_id:
        raise ValidationError("no active scope with an id; run set_scope first")

    packet_id = new_uuid()
    ts = now_iso()
    record = {
        "packet_id": packet_id,
        "packet_type": "review_request",
        "project_id": ident.project_id,
        "repository_id": ident.repository_id,
        "branch": git["branch"],
        "head_commit": git["head_commit"],
        "dirty_fingerprint": git["dirty_fingerprint"],
        "scope_id": state.scope.scope_id,
        "scope_revision": state.scope.version,
        "question": question,
        "action": action,
        "created_at": ts,
        "status": "pending",
        "decision_id": None,
    }
    state.reviews[packet_id] = record
    state.updated_at = ts
    store.save_state(root, state)
    store.append_event(root, _event(EventType.REVIEW_REQUESTED, actor,
                                    packet_id=packet_id, action=action))

    objective = state.objective.text if state.objective else "(not set)"
    fp = git["dirty_fingerprint"] or "null"
    out_dir = Path(root) / store.AI_DIR / "exchange" / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{packet_id}-chatgpt-review.md"

    packet = f"""# Project State Keeper — review request

> Upload this file to ChatGPT and say: **"Review the attached Project State Keeper
> packet."** No other context is needed. It contains no repository source code.

```yaml
packet_type: review_request
packet_id: {packet_id}
project_id: {ident.project_id}
repository_id: {ident.repository_id}
project_name: {ident.display_name}
repository_name: {ident.repository_name}
branch: {git['branch']}
head: {git['head_commit']}
dirty_fingerprint: {fp}
scope_id: {state.scope.scope_id}
scope_revision: {state.scope.version}
packet_created_at: {ts}
```

## Question
{question}

## Active scope (revision {state.scope.version})
{state.scope.description}

## Current objective
{objective}

## Concise current state
- items: {len(state.items)} | decisions: {len(state.decisions)} | checkpoints: {len(state.checkpoints)}
- branch `{git['branch']}` at `{git['head_commit']}`
- worktree: {'clean (ignoring .ai/)' if not git['dirty'] else 'dirty'}

## Proposed action (exact, small, reversible)
{action}

## Local-agent recommendation
{recommendation or 'Proceed with the proposed action.'}

## Strongest case against
{against or 'None identified for this small, reversible action.'}

## Verification evidence already available
{evidence or 'Full local test suite passing at this HEAD.'}

## Known uncertainty
{uncertainty or 'None material for this action.'}

## Reserved human-only actions (never auto-performed)
{', '.join(RESERVED_HUMAN_ACTIONS)}

## Required response format (return exactly this, with values matching the header)
{RESPONSE_TEMPLATE.format(packet_id=packet_id, project_id=ident.project_id, repository_id=ident.repository_id, branch=git['branch'], head=git['head_commit'], fingerprint=fp, scope_id=state.scope.scope_id, scope_revision=state.scope.version)}
"""
    store.atomic_write(out_path, packet)
    return out_path


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
def _extract_yaml(text: str) -> List[str]:
    lines = text.splitlines()
    inside, buf = False, []
    for line in lines:
        s = line.strip()
        if not inside and s.startswith("```") and "yaml" in s:
            inside = True
            continue
        if inside and s.startswith("```"):
            return buf
        if inside:
            buf.append(line)
    if lines and lines[0].strip() == "---":  # front-matter fallback
        for line in lines[1:]:
            if line.strip() == "---":
                break
            buf.append(line)
    return buf


def parse_decision(text: str) -> dict:
    buf = _extract_yaml(text)
    if not buf:
        raise ValidationError("no YAML block found in decision file")
    d = {}
    for line in buf:
        s = line.strip()
        if not s or s.startswith("#") or ":" not in s:
            continue
        k, v = s.split(":", 1)
        d[k.strip()] = v.strip()
    return d


def _section(text: str, header: str) -> str:
    out, capture = [], False
    for line in text.splitlines():
        if line.strip().lower() == f"## {header}".lower():
            capture = True
            continue
        if capture and line.strip().startswith("## "):
            break
        if capture:
            out.append(line)
    return "\n".join(out).strip()


def _norm(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return None if v.lower() in ("null", "none", "") else v


def validate_decision(record: dict, ident, d: dict) -> str:
    if d.get("packet_type") != "review_decision":
        raise ValidationError("packet_type must be 'review_decision'")
    if d.get("project_id") != ident.project_id:
        raise ProjectMismatchError("decision project_id does not match this repository")
    if d.get("repository_id") != ident.repository_id:
        raise ProjectMismatchError("decision repository_id does not match this repository")
    if d.get("reviewed_branch") != record["branch"]:
        raise ValidationError("reviewed_branch does not match the request")
    if d.get("reviewed_head") != record["head_commit"]:
        raise ValidationError("reviewed_head is stale / does not match the request")
    if _norm(d.get("reviewed_diff_fingerprint")) != _norm(record["dirty_fingerprint"]):
        raise ValidationError("reviewed_diff_fingerprint does not match the request")
    if d.get("scope_id") != record["scope_id"]:
        raise ValidationError("scope_id does not match the request")
    if str(d.get("scope_revision")) != str(record["scope_revision"]):
        raise ValidationError("scope_revision does not match the request")
    if d.get("reviewer") != "chatgpt":
        raise ValidationError("unrecognized reviewer")
    verdict = d.get("decision")
    if verdict not in {v.value for v in Verdict}:
        raise ValidationError(f"unrecognized decision '{verdict}'")
    return verdict


def import_decision(path: str, decision_file: str, actor: str = "human") -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)

    dfile = Path(decision_file)
    if not dfile.exists():
        raise StateNotFoundError(f"decision file not found: {decision_file}")
    text = dfile.read_text(encoding="utf-8")
    d = parse_decision(text)

    pid = d.get("packet_id")
    record = state.reviews.get(pid)
    if record is None:
        raise ValidationError(f"unknown packet_id '{pid}'")
    if record.get("status") != "pending":
        raise ValidationError(f"packet '{pid}' already imported")

    verdict = validate_decision(record, ident, d)  # raises on any mismatch

    # Archive request + decision UNCHANGED.
    archive_dir = Path(root) / store.AI_DIR / "exchange" / "archive" / pid
    archive_dir.mkdir(parents=True, exist_ok=True)
    req_file = Path(root) / store.AI_DIR / "exchange" / "outbox" / f"{pid}-chatgpt-review.md"
    if req_file.exists():
        shutil.copyfile(req_file, archive_dir / "request.md")
    shutil.copyfile(dfile, archive_dir / "decision.md")

    # Record the decision in canonical state (no execution).
    dec = Decision(
        id=new_uuid(),
        authority=Authority.CHATGPT,
        verdict=Verdict(verdict),
        conditions=[] if _section(text, "Conditions").strip().lower() in ("", "none")
        else [_section(text, "Conditions")],
        rationale=_section(text, "Rationale"),
        binding=DecisionBinding(
            repo_uuid=ident.project_id,
            branch=record["branch"],
            head_commit=record["head_commit"],
            scope_version=record["scope_revision"],
            action=record["action"],
        ),
        evidence_ids=[],
        created_at=now_iso(),
    )
    state.decisions[dec.id] = dec
    record["status"] = "imported"
    record["decision_id"] = dec.id
    record["imported_at"] = now_iso()
    record["verdict"] = verdict
    state.reviews[pid] = record
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, _event(EventType.DECISION_RECORDED, actor,
                                    decision_id=dec.id, verdict=verdict,
                                    action=record["action"]))
    store.append_event(root, _event(EventType.REVIEW_IMPORTED, actor,
                                    packet_id=pid, decision_id=dec.id))
    return {"packet_id": pid, "decision_id": dec.id, "verdict": verdict,
            "action": record["action"], "archived_to": str(archive_dir)}


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #
def gate(path: str, packet_id: Optional[str] = None) -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)

    imported = [r for r in state.reviews.values() if r.get("status") == "imported"]
    if not imported:
        raise ValidationError("no imported decision to gate")
    if packet_id:
        record = state.reviews.get(packet_id)
        if not record or record.get("status") != "imported":
            raise ValidationError(f"no imported decision for packet '{packet_id}'")
    else:
        record = sorted(imported, key=lambda r: r.get("imported_at", ""))[-1]

    dec = state.decisions[record["decision_id"]]
    live = _live(root)
    is_current = (live["head_commit"] == record["head_commit"]
                  and _norm(live["dirty_fingerprint"]) == _norm(record["dirty_fingerprint"]))
    if dec.verdict == Verdict.APPROVE and is_current:
        result = "PROCEED"
    else:
        result = "HOLD"  # non-APPROVE or stale approval => reserved handling
    return {
        "result": result,
        "decision": dec.verdict.value,
        "approved_action": record["action"],
        "packet_id": record["packet_id"],
        "project": ident.display_name,
        "branch": record["branch"],
        "head": record["head_commit"],
        "scope": f"{record['scope_id']} (rev {record['scope_revision']})",
        "reviewer": "chatgpt",
        "approval_current": is_current,
        "note": ("Authorizes only the exact approved action. Not authorized: push, "
                 "merge, deploy, publish, delete, spend, external comms, secrets, "
                 "production."),
    }
