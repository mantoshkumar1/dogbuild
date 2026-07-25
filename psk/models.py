"""Typed data models + (de)serialization for the canonical project state.

Design notes:
- Enums subclass `str` so members serialize natively to JSON strings and compare
  equal to their string values (simplifies round-tripping and validation).
- Timestamps are stored as ISO strings (see util.now_iso), not datetime objects,
  to keep serialization trivial and deterministic.
- `to_jsonable` converts dataclasses/enums recursively; `ProjectState.from_dict`
  reconstructs the typed tree from a plain dict (validated separately).
"""

from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ItemStatus(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class Verdict(str, enum.Enum):
    APPROVE = "APPROVE"
    APPROVE_WITH_CONDITIONS = "APPROVE_WITH_CONDITIONS"
    VETO = "VETO"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class Authority(str, enum.Enum):
    HUMAN = "human"
    CHATGPT = "chatgpt"


class EvidenceKind(str, enum.Enum):
    TEST = "test"
    COMMAND = "command"
    GIT = "git"
    FILE = "file"
    NOTE = "note"


class ReservedAction(str, enum.Enum):
    PUSH = "push"
    DEPLOY = "deploy"
    MERGE = "merge"
    PUBLISH = "publish"
    DELETE_DATA = "delete_data"
    SPEND = "spend"
    EXTERNAL_COMM = "external_comm"
    SECRETS_OR_PROD = "secrets_or_prod"
    SCOPE_CHANGE = "scope_change"


class EventType(str, enum.Enum):
    INITIALIZED = "initialized"
    GIT_CAPTURED = "git_captured"
    OBJECTIVE_SET = "objective_set"
    SCOPE_SET = "scope_set"
    ITEM_REQUESTED = "item_requested"
    ITEM_STATUS_CHANGED = "item_status_changed"
    EVIDENCE_RECORDED = "evidence_recorded"
    DECISION_RECORDED = "decision_recorded"
    CHECKPOINT_CREATED = "checkpoint_created"
    REVIEW_REQUESTED = "review_requested"
    REVIEW_IMPORTED = "review_imported"
    DECLARATION_RECORDED = "declaration_recorded"
    HANDOFF_CREATED = "handoff_created"
    HANDOFF_CONSUMED = "handoff_consumed"
    MODE_SET = "mode_set"


# Reserved human-only approvals — always require the human, never auto-performed.
DEFAULT_RESERVED: List[ReservedAction] = list(ReservedAction)


# --------------------------------------------------------------------------- #
# Dataclasses
# --------------------------------------------------------------------------- #
@dataclass
class RepositoryIdentity:
    psk_uuid: str
    root: str
    remotes: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class GitState:
    branch: str
    detached: bool
    head_commit: Optional[str]
    dirty: bool
    dirty_fingerprint: Optional[str]
    captured_at: str


@dataclass
class Objective:
    text: str
    version: int
    set_at: str


@dataclass
class Scope:
    description: str
    version: int
    set_at: str
    scope_id: str = ""  # stable across revisions; version is the revision number


@dataclass
class RequestedItem:
    id: str
    description: str
    status: ItemStatus
    created_at: str
    updated_at: str
    evidence_ids: List[str] = field(default_factory=list)
    decision_ids: List[str] = field(default_factory=list)


@dataclass
class Evidence:
    id: str
    kind: EvidenceKind
    summary: str
    detail: str
    source: str
    captured_at: str


@dataclass
class DecisionBinding:
    """The exact state a decision was made against (for staleness checks)."""
    repo_uuid: str
    branch: str
    head_commit: Optional[str]
    scope_version: Optional[int]
    action: str


@dataclass
class Decision:
    id: str
    authority: Authority
    verdict: Verdict
    conditions: List[str]
    rationale: str
    binding: DecisionBinding
    evidence_ids: List[str]
    created_at: str


@dataclass
class Checkpoint:
    id: str
    summary: str
    implemented: List[str]
    tested: List[str]
    failures_resolved: List[str]
    git_state: GitState
    unresolved_risks: List[str]
    next_safe_action: str
    evidence_ids: List[str]
    created_at: str


@dataclass
class ProjectState:
    schema_version: str
    identity: RepositoryIdentity
    git_state: GitState
    reserved_approvals: List[ReservedAction]
    updated_at: str
    objective: Optional[Objective] = None
    scope: Optional[Scope] = None
    items: Dict[str, RequestedItem] = field(default_factory=dict)
    evidence: Dict[str, Evidence] = field(default_factory=dict)
    decisions: Dict[str, Decision] = field(default_factory=dict)
    checkpoints: Dict[str, Checkpoint] = field(default_factory=dict)
    # Review requests keyed by packet_id (plain dicts — the review slice's records).
    reviews: Dict[str, dict] = field(default_factory=dict)
    # Agent handoff packets keyed by packet_id (plain dicts).
    handoffs: Dict[str, dict] = field(default_factory=dict)
    last_checkpoint_id: Optional[str] = None

    def to_dict(self) -> dict:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectState":
        return _state_from_dict(d)


@dataclass
class Event:
    event_id: str
    type: EventType
    timestamp: str
    actor: str
    schema_version: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return to_jsonable(self)


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #
def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, enum.Enum):
        return obj.value
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj


# --- typed reconstruction from plain dicts (validation happens separately) --- #
def _git_from(d: dict) -> GitState:
    return GitState(
        branch=d["branch"],
        detached=d["detached"],
        head_commit=d.get("head_commit"),
        dirty=d["dirty"],
        dirty_fingerprint=d.get("dirty_fingerprint"),
        captured_at=d["captured_at"],
    )


def _item_from(d: dict) -> RequestedItem:
    return RequestedItem(
        id=d["id"],
        description=d["description"],
        status=ItemStatus(d["status"]),
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        evidence_ids=list(d.get("evidence_ids", [])),
        decision_ids=list(d.get("decision_ids", [])),
    )


def _evidence_from(d: dict) -> Evidence:
    return Evidence(
        id=d["id"],
        kind=EvidenceKind(d["kind"]),
        summary=d["summary"],
        detail=d.get("detail", ""),
        source=d.get("source", ""),
        captured_at=d["captured_at"],
    )


def _decision_from(d: dict) -> Decision:
    b = d["binding"]
    return Decision(
        id=d["id"],
        authority=Authority(d["authority"]),
        verdict=Verdict(d["verdict"]),
        conditions=list(d.get("conditions", [])),
        rationale=d.get("rationale", ""),
        binding=DecisionBinding(
            repo_uuid=b["repo_uuid"],
            branch=b["branch"],
            head_commit=b.get("head_commit"),
            scope_version=b.get("scope_version"),
            action=b["action"],
        ),
        evidence_ids=list(d.get("evidence_ids", [])),
        created_at=d["created_at"],
    )


def _checkpoint_from(d: dict) -> Checkpoint:
    return Checkpoint(
        id=d["id"],
        summary=d["summary"],
        implemented=list(d.get("implemented", [])),
        tested=list(d.get("tested", [])),
        failures_resolved=list(d.get("failures_resolved", [])),
        git_state=_git_from(d["git_state"]),
        unresolved_risks=list(d.get("unresolved_risks", [])),
        next_safe_action=d.get("next_safe_action", ""),
        evidence_ids=list(d.get("evidence_ids", [])),
        created_at=d["created_at"],
    )


def _state_from_dict(d: dict) -> ProjectState:
    ident = d["identity"]
    return ProjectState(
        schema_version=d["schema_version"],
        identity=RepositoryIdentity(
            psk_uuid=ident["psk_uuid"],
            root=ident["root"],
            remotes=list(ident.get("remotes", [])),
            created_at=ident.get("created_at", ""),
        ),
        git_state=_git_from(d["git_state"]),
        reserved_approvals=[ReservedAction(a) for a in d.get("reserved_approvals", [])],
        updated_at=d["updated_at"],
        objective=(Objective(**d["objective"]) if d.get("objective") else None),
        scope=(Scope(**d["scope"]) if d.get("scope") else None),
        items={k: _item_from(v) for k, v in d.get("items", {}).items()},
        evidence={k: _evidence_from(v) for k, v in d.get("evidence", {}).items()},
        decisions={k: _decision_from(v) for k, v in d.get("decisions", {}).items()},
        checkpoints={k: _checkpoint_from(v) for k, v in d.get("checkpoints", {}).items()},
        reviews={k: dict(v) for k, v in d.get("reviews", {}).items()},
        handoffs={k: dict(v) for k, v in d.get("handoffs", {}).items()},
        last_checkpoint_id=d.get("last_checkpoint_id"),
    )
