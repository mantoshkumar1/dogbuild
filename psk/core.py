"""High-level operations: initialize state and record facts/decisions/checkpoints.

Every mutating op is load → modify → save, and appends a matching event to the
append-only history. Day 1 provides the data model and safe recording. The
authority *gate* (evaluating decisions) is Day 10 and is intentionally absent
here — decisions are recorded, not enforced yet.
"""

from __future__ import annotations

from typing import List, Optional

from . import gitutil, store
from .errors import StateExistsError
from .models import (
    DEFAULT_RESERVED,
    Authority,
    Checkpoint,
    Decision,
    DecisionBinding,
    Event,
    EventType,
    Evidence,
    EvidenceKind,
    GitState,
    Objective,
    ProjectState,
    RepositoryIdentity,
    RequestedItem,
    Scope,
    ItemStatus,
    Verdict,
    SCHEMA_VERSION,
)
from .util import new_uuid, now_iso


def _git_state(repo_root: str) -> GitState:
    d = gitutil.capture_git_state(repo_root)
    return GitState(**d)


def _event(type_: EventType, actor: str, **payload) -> Event:
    return Event(
        event_id=new_uuid(),
        type=type_,
        timestamp=now_iso(),
        actor=actor,
        schema_version=SCHEMA_VERSION,
        payload=payload,
    )


def initialize(path: str, *, objective: Optional[str] = None, actor: str = "human",
               force: bool = False) -> ProjectState:
    root = gitutil.repo_root(path)  # raises NotAGitRepoError if not a repo
    if store.state_exists(root) and not force:
        raise StateExistsError(
            f"{store.state_path(root)} already exists; pass force=True to reinitialize"
        )
    ts = now_iso()
    identity = RepositoryIdentity(
        psk_uuid=new_uuid(),
        root=root,
        remotes=gitutil.remotes(root),
        created_at=ts,
    )
    state = ProjectState(
        schema_version=SCHEMA_VERSION,
        identity=identity,
        git_state=_git_state(root),
        reserved_approvals=list(DEFAULT_RESERVED),
        updated_at=ts,
        objective=(Objective(text=objective, version=1, set_at=ts) if objective else None),
    )
    store.save_state(root, state, allow_create=True, force=force)
    store.append_event(root, _event(EventType.INITIALIZED, actor,
                                    psk_uuid=identity.psk_uuid, root=root))
    if objective:
        store.append_event(root, _event(EventType.OBJECTIVE_SET, actor,
                                        version=1, text=objective))
    return state


def _load(path: str):
    root = gitutil.repo_root(path)
    return root, store.load_state(root)


def _commit(root: str, state: ProjectState, event: Event) -> ProjectState:
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, event)
    return state


def capture_git(path: str, actor: str = "human") -> ProjectState:
    root, state = _load(path)
    state.git_state = _git_state(root)
    return _commit(root, state, _event(EventType.GIT_CAPTURED, actor,
                                       branch=state.git_state.branch,
                                       head_commit=state.git_state.head_commit,
                                       dirty=state.git_state.dirty))


def set_objective(path: str, text: str, actor: str = "human") -> ProjectState:
    root, state = _load(path)
    version = (state.objective.version + 1) if state.objective else 1
    state.objective = Objective(text=text, version=version, set_at=now_iso())
    return _commit(root, state, _event(EventType.OBJECTIVE_SET, actor,
                                       version=version, text=text))


def set_scope(path: str, description: str, actor: str = "human") -> ProjectState:
    root, state = _load(path)
    version = (state.scope.version + 1) if state.scope else 1
    state.scope = Scope(description=description, version=version, set_at=now_iso())
    return _commit(root, state, _event(EventType.SCOPE_SET, actor,
                                       version=version, description=description))


def request_item(path: str, description: str, actor: str = "human") -> RequestedItem:
    root, state = _load(path)
    ts = now_iso()
    item = RequestedItem(
        id=new_uuid(), description=description, status=ItemStatus.REQUESTED,
        created_at=ts, updated_at=ts,
    )
    state.items[item.id] = item
    _commit(root, state, _event(EventType.ITEM_REQUESTED, actor,
                                item_id=item.id, description=description))
    return item


def set_item_status(path: str, item_id: str, status: ItemStatus,
                    actor: str = "human") -> ProjectState:
    root, state = _load(path)
    if item_id not in state.items:
        raise KeyError(f"unknown item {item_id}")
    prev = state.items[item_id].status
    state.items[item_id].status = status
    state.items[item_id].updated_at = now_iso()
    return _commit(root, state, _event(EventType.ITEM_STATUS_CHANGED, actor,
                                       item_id=item_id, was=prev.value, now=status.value))


def record_evidence(path: str, kind: EvidenceKind, summary: str, *, detail: str = "",
                    source: str = "", item_id: Optional[str] = None,
                    actor: str = "human") -> Evidence:
    root, state = _load(path)
    ev = Evidence(id=new_uuid(), kind=kind, summary=summary, detail=detail,
                  source=source, captured_at=now_iso())
    state.evidence[ev.id] = ev
    if item_id and item_id in state.items:
        state.items[item_id].evidence_ids.append(ev.id)
    _commit(root, state, _event(EventType.EVIDENCE_RECORDED, actor,
                                evidence_id=ev.id, kind=kind.value, summary=summary))
    return ev


def record_decision(path: str, authority: Authority, verdict: Verdict, action: str, *,
                    conditions: Optional[List[str]] = None, rationale: str = "",
                    evidence_ids: Optional[List[str]] = None,
                    actor: str = "human") -> Decision:
    root, state = _load(path)
    g = state.git_state
    binding = DecisionBinding(
        repo_uuid=state.identity.psk_uuid,
        branch=g.branch,
        head_commit=g.head_commit,
        scope_version=(state.scope.version if state.scope else None),
        action=action,
    )
    dec = Decision(
        id=new_uuid(), authority=authority, verdict=verdict,
        conditions=list(conditions or []), rationale=rationale, binding=binding,
        evidence_ids=list(evidence_ids or []), created_at=now_iso(),
    )
    state.decisions[dec.id] = dec
    _commit(root, state, _event(EventType.DECISION_RECORDED, actor,
                                decision_id=dec.id, authority=authority.value,
                                verdict=verdict.value, action=action))
    return dec


def create_checkpoint(path: str, summary: str, *, implemented: Optional[List[str]] = None,
                      tested: Optional[List[str]] = None,
                      failures_resolved: Optional[List[str]] = None,
                      unresolved_risks: Optional[List[str]] = None,
                      next_safe_action: str = "", evidence_ids: Optional[List[str]] = None,
                      actor: str = "human") -> Checkpoint:
    root, state = _load(path)
    cp = Checkpoint(
        id=new_uuid(), summary=summary, implemented=list(implemented or []),
        tested=list(tested or []), failures_resolved=list(failures_resolved or []),
        git_state=_git_state(root), unresolved_risks=list(unresolved_risks or []),
        next_safe_action=next_safe_action, evidence_ids=list(evidence_ids or []),
        created_at=now_iso(),
    )
    state.checkpoints[cp.id] = cp
    state.last_checkpoint_id = cp.id
    state.git_state = cp.git_state
    _commit(root, state, _event(EventType.CHECKPOINT_CREATED, actor,
                                checkpoint_id=cp.id, summary=summary))
    return cp
