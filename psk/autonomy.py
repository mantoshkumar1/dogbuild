"""Owner-away autonomy + pending owner-input reconciliation.

A human-approved *Autonomy Contract* lets ChatGPT (master reviewer) and Claude
(execution agent) continue an already-approved milestone while the owner is away.
Owner messages that arrive mid-run are recorded, classified, and reconciled
before the next reviewer direction — they are never silently dropped.

State is kept in two isolated files so the core ProjectState model is untouched:
  .ai/autonomy.json     — contract + lifecycle status + instruction epoch
  .ai/owner_input.jsonl — append-only owner-message queue

This module intentionally uses JSON for the contract file (dependency-free and
robust); the field semantics match the reviewer's autonomy_contract spec.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import gitutil, identity as identity_mod, store
from .errors import ValidationError, StateNotFoundError
from .util import new_uuid, now_iso, pretty_json

AUTONOMY_FILE = "autonomy.json"
INPUT_FILE = "owner_input.jsonl"

LIFECYCLE = ("ACTIVE", "PAUSED", "STOPPED", "COMPLETED", "NEEDS_HUMAN", "STALE")
CLASSIFICATIONS = ("STATE_QUERY", "NON_BLOCKING_FEEDBACK", "MATERIAL_INSTRUCTION",
                   "PAUSE_OR_CANCEL", "HUMAN_DECISION", "AMBIGUOUS")
MSG_STATUS = ("PENDING", "ANSWERED", "APPLIED", "INVALIDATED", "NEEDS_CLARIFICATION")
OUTCOMES = ("ANSWERED_NO_EXECUTION_EFFECT", "APPLIED_AS_FEEDBACK",
            "INVALIDATED_IN_FLIGHT_WORK", "UPDATED_INSTRUCTION_EPOCH",
            "REQUIRES_CLARIFICATION", "RECORDED_HUMAN_DECISION")

GOAL_CONFIRM_PHRASE = "I approve updating the project goal as described above."

AUTHORITY_ORDER = [
    "latest explicit owner instruction",
    "live repository and verification evidence",
    "active Goal Contract and Autonomy Contract",
    "latest valid ChatGPT reviewer decision",
    "latest Claude execution report",
    "older summaries",
]


# --------------------------------------------------------------------------- #
# storage
# --------------------------------------------------------------------------- #
def _apath(root: str) -> Path:
    return Path(gitutil.repo_root(root)) / store.AI_DIR / AUTONOMY_FILE


def _ipath(root: str) -> Path:
    return Path(gitutil.repo_root(root)) / store.AI_DIR / INPUT_FILE


def _default_autonomy() -> dict:
    return {"schema_version": 1, "contract": None, "status": "INACTIVE",
            "instruction_epoch": 1, "revision": 0, "consecutive_failures": 0,
            "updated_at": None}


def load_autonomy(root: str) -> dict:
    p = _apath(root)
    if not p.exists():
        return _default_autonomy()
    return json.loads(p.read_text(encoding="utf-8"))


def _save_autonomy(root: str, data: dict) -> dict:
    data["updated_at"] = now_iso()
    p = _apath(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write(p, pretty_json(data))
    return data


# --------------------------------------------------------------------------- #
# instruction epoch
# --------------------------------------------------------------------------- #
def current_epoch(root: str) -> int:
    return int(load_autonomy(root)["instruction_epoch"])


def bump_epoch(root: str) -> int:
    a = load_autonomy(root)
    a["instruction_epoch"] = int(a["instruction_epoch"]) + 1
    _save_autonomy(root, a)
    return a["instruction_epoch"]


# --------------------------------------------------------------------------- #
# autonomy contract lifecycle
# --------------------------------------------------------------------------- #
def _load_contract_text(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        inner = []
        for line in lines[1:]:
            if line.strip().startswith("```"):
                break
            inner.append(line)
        t = "\n".join(inner).strip()
    if not t.startswith("{"):
        raise ValidationError("autonomy contract must be JSON (optionally fenced)")
    return json.loads(t)


def start(root: str, contract_file: str) -> dict:
    root = gitutil.repo_root(root)
    p = Path(contract_file)
    if not p.exists():
        raise StateNotFoundError(f"autonomy contract not found: {contract_file}")
    d = _load_contract_text(p.read_text(encoding="utf-8"))
    if d.get("packet_type") != "autonomy_contract":
        raise ValidationError("packet_type must be 'autonomy_contract'")
    if str(d.get("human_approved")).lower() != "true":
        raise ValidationError("autonomy contract requires human_approved: true before activation")
    a = load_autonomy(root)
    a["contract"] = d
    a["status"] = "ACTIVE"
    a["revision"] = int(d.get("autonomy_contract_revision", 1))
    a["instruction_epoch"] = max(int(a["instruction_epoch"]),
                                 int(d.get("instruction_epoch", 1)))
    a["consecutive_failures"] = 0
    _save_autonomy(root, a)
    return status(root)


def _set_status(root: str, new: str) -> dict:
    if new not in LIFECYCLE:
        raise ValidationError(f"invalid autonomy status '{new}'")
    a = load_autonomy(root)
    if a["status"] == "INACTIVE" and new != "ACTIVE":
        raise ValidationError("no active autonomy contract")
    a["status"] = new
    _save_autonomy(root, a)
    return status(root)


def pause(root: str) -> dict:
    return _set_status(root, "PAUSED")


def resume(root: str) -> dict:
    a = load_autonomy(root)
    if a["status"] not in ("PAUSED", "NEEDS_HUMAN", "STALE"):
        raise ValidationError(f"cannot resume from status {a['status']}")
    return _set_status(root, "ACTIVE")


def stop(root: str) -> dict:
    return _set_status(root, "STOPPED")


def status(root: str) -> dict:
    a = load_autonomy(root)
    c = a.get("contract") or {}
    pending = [m for m in list_messages(root) if m["status"] in ("PENDING", "NEEDS_CLARIFICATION")]
    return {
        "status": a["status"],
        "autonomy_contract_revision": a["revision"],
        "instruction_epoch": a["instruction_epoch"],
        "current_milestone": c.get("current_milestone"),
        "exact_next_action": c.get("exact_next_action"),
        "pending_owner_messages": len(pending),
        "consecutive_failures": a.get("consecutive_failures", 0),
    }


# --------------------------------------------------------------------------- #
# owner-input queue
# --------------------------------------------------------------------------- #
def _has(text: str, *needles) -> bool:
    t = text.lower()
    return any(n in t for n in needles)


def classify(text: str) -> str:
    t = text.lower().strip()
    # explicit pause/cancel (but not "stop working on <feature>", which is material)
    if (_has(t, "pause", "cancel", "abort", "halt")
            or t in ("stop", "stop.", "stop it", "stop it.", "hold on", "wait")):
        return "PAUSE_OR_CANCEL"
    # human decision selecting a pending option / approvals
    if _has(t, "i approve", "i choose", "i pick", "i select", "go with option",
            "option a", "option b", "option c", "i approve updating the project goal"):
        return "HUMAN_DECISION"
    # material instruction: changes scope/goal/milestone/exclusions/repo
    if _has(t, "do not add", "don't add", "dont add", "no api", "no apis",
            "change the milestone", "change the goal", "different repo",
            "stop working on", "add this to", "add to the scope", "remove the",
            "use a different", "switch to", "must not", "no longer"):
        return "MATERIAL_INSTRUCTION"
    # state query
    if (t.endswith("?") and _has(t, "what", "where", "did", "is ", "are ", "status")) \
            or _has(t, "what's happening", "whats happening", "what is happening",
                    "where are we", "did tests pass", "what remains",
                    "what is claude doing", "what's the status", "status?"):
        return "STATE_QUERY"
    # non-blocking style feedback
    if _has(t, "shorter", "keep it short", "keep responses", "keep the answer",
            "plain english", "less technical", "too technical", "i prefer",
            "briefer", "more concise", "simpler"):
        return "NON_BLOCKING_FEEDBACK"
    # vague dislike -> ambiguous
    if _has(t, "i don't like", "i dont like", "change it", "this is wrong",
            "redo", "not good", "hate this", "no good"):
        return "AMBIGUOUS"
    return "AMBIGUOUS"


_INITIAL_STATUS = {
    "STATE_QUERY": "ANSWERED",
    "NON_BLOCKING_FEEDBACK": "PENDING",
    "MATERIAL_INSTRUCTION": "PENDING",
    "PAUSE_OR_CANCEL": "PENDING",
    "HUMAN_DECISION": "PENDING",
    "AMBIGUOUS": "NEEDS_CLARIFICATION",
}

_NORMALIZED = {
    "STATE_QUERY": "Owner asked for status; answer in plain English, no execution effect.",
    "NON_BLOCKING_FEEDBACK": "Apply to the next relevant response/detail; unrelated work stays valid.",
    "MATERIAL_INSTRUCTION": "Changes scope/goal/milestone; epoch incremented, in-flight work invalidated, autonomy paused.",
    "PAUSE_OR_CANCEL": "Stop promptly; checkpoint; preserve exact safe resume action.",
    "HUMAN_DECISION": "Owner selected an option for a pending decision; verify before resuming.",
    "AMBIGUOUS": "Meaning unclear; ask one focused question before changing execution.",
}

_AFFECTS = {
    "STATE_QUERY": ["response_style"],
    "NON_BLOCKING_FEEDBACK": ["response_style"],
    "MATERIAL_INSTRUCTION": ["active_task", "current_milestone", "autonomy_contract"],
    "PAUSE_OR_CANCEL": ["active_task", "autonomy_contract"],
    "HUMAN_DECISION": ["active_task"],
    "AMBIGUOUS": ["response_style"],
}


def _material_effect(root: str, text: str) -> str:
    """Classify a material instruction's effect: a redirection (changes the
    active goal/milestone/scope) always invalidates; a pure exclusion only
    invalidates if it conflicts with the current milestone/next action."""
    t = text.lower()
    if _has(t, "change the milestone", "change the goal", "different repo",
            "use a different", "switch to", "stop working on", "add this to",
            "add to the scope", "no longer", "remove the"):
        return "redirect"
    a = load_autonomy(root)
    c = a.get("contract") or {}
    ctx = " ".join(str(c.get(k, "")) for k in ("current_milestone", "exact_next_action")).lower()
    body = t
    for w in ("do not add", "don't add", "dont add", "no ", "must not"):
        body = body.replace(w, " ")
    tokens = [w.strip(".,!?") for w in body.split() if len(w) > 3]
    conflict = any(tok in ctx for tok in tokens)
    return "exclusion_conflict" if conflict else "exclusion_noconflict"


def add_message(root: str, text: str, *, classification=None, actor_name="owner") -> dict:
    root = gitutil.repo_root(root)
    cls = classification or classify(text)
    if cls not in CLASSIFICATIONS:
        raise ValidationError(f"unknown classification '{cls}'")
    epoch = current_epoch(root)
    msg = {
        "message_id": new_uuid(),
        "received_at": now_iso(),
        "instruction_epoch_at_receipt": epoch,
        "source": {"actor_type": "human", "actor_name": actor_name, "role": "human_owner"},
        "classification": {"type": cls},
        "raw_message": text,                     # preserved exactly, unaltered
        "normalized_effect": _NORMALIZED[cls],
        "status": _INITIAL_STATUS[cls],
        "affects": list(_AFFECTS[cls]),
        "reconciled": False,
    }
    # side effects that must happen at receipt (in-flight race protection)
    if cls == "MATERIAL_INSTRUCTION":
        effect = _material_effect(root, text)
        msg["material_effect"] = effect
        if effect in ("redirect", "exclusion_conflict"):
            bump_epoch(root)                     # stamps every prior packet stale
            msg["instruction_epoch_after"] = current_epoch(root)
            a = load_autonomy(root)
            if a["status"] == "ACTIVE":
                a["status"] = "PAUSED"
                _save_autonomy(root, a)
        else:
            msg["affects"] = ["explicit_exclusions"]
            msg["normalized_effect"] = ("Recorded as a binding exclusion; it does not "
                                        "conflict with current work, so nothing is invalidated.")
    elif cls == "PAUSE_OR_CANCEL":
        a = load_autonomy(root)
        if a["status"] == "ACTIVE":
            a["status"] = "PAUSED"
            _save_autonomy(root, a)
    p = _ipath(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(msg, sort_keys=True) + "\n")
    return msg


def list_messages(root: str, *, pending_only: bool = False) -> list:
    p = _ipath(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    if pending_only:
        out = [m for m in out if m["status"] in ("PENDING", "NEEDS_CLARIFICATION")]
    return out


def _rewrite_messages(root: str, msgs: list) -> None:
    p = _ipath(root)
    store.atomic_write(p, "".join(json.dumps(m, sort_keys=True) + "\n" for m in msgs))


_OUTCOME = {
    "STATE_QUERY": ("ANSWERED_NO_EXECUTION_EFFECT", "ANSWERED"),
    "NON_BLOCKING_FEEDBACK": ("APPLIED_AS_FEEDBACK", "APPLIED"),
    "MATERIAL_INSTRUCTION": ("UPDATED_INSTRUCTION_EPOCH", "APPLIED"),
    "PAUSE_OR_CANCEL": ("INVALIDATED_IN_FLIGHT_WORK", "APPLIED"),
    "HUMAN_DECISION": ("RECORDED_HUMAN_DECISION", "APPLIED"),
    "AMBIGUOUS": ("REQUIRES_CLARIFICATION", "NEEDS_CLARIFICATION"),
}


def reconcile(root: str) -> dict:
    """Build the Reviewer Reconciliation Context and record how each pending
    owner message affects the next reviewer direction. Never drops input."""
    root = gitutil.repo_root(root)
    msgs = list_messages(root)
    try:
        state = store.load_state(root)
        gc = state.goal_contract or {}
    except Exception:
        gc = {}
    git = gitutil.capture_git_state(root)
    a = load_autonomy(root)

    considered = []
    for m in msgs:
        if m.get("reconciled") and m["status"] != "NEEDS_CLARIFICATION":
            continue
        cls = m["classification"]["type"]
        if cls == "MATERIAL_INSTRUCTION" and m.get("material_effect") == "exclusion_noconflict":
            outcome, new_status = "APPLIED_AS_FEEDBACK", "APPLIED"
        else:
            outcome, new_status = _OUTCOME[cls]
        m["reconciled"] = True
        m["status"] = new_status
        m["reconciled_outcome"] = outcome
        considered.append({
            "message_id": m["message_id"],
            "classification": cls,
            "status": m["status"],
            "raw_message": m["raw_message"],
            "outcome": outcome,
        })
    _rewrite_messages(root, msgs)

    return {
        "generated_at": now_iso(),
        "instruction_epoch": a["instruction_epoch"],
        "autonomy": {"status": a["status"], "revision": a["revision"]},
        "live_evidence": {"branch": git["branch"], "head_commit": git["head_commit"],
                          "dirty": git["dirty"]},
        "goal_contract": {"goal_id": gc.get("goal_id"),
                          "revision": gc.get("revision"),
                          "fingerprint": gc.get("fingerprint")},
        "authority_order": list(AUTHORITY_ORDER),
        "pending_owner_messages": considered,
        "unresolved": [c for c in considered if c["outcome"] == "REQUIRES_CLARIFICATION"],
    }


# --------------------------------------------------------------------------- #
# in-flight approval race protection
# --------------------------------------------------------------------------- #
def approval_is_current(root: str, epoch_at_approval: int) -> bool:
    """A material owner instruction bumps the epoch, staling any packet/approval
    stamped at an older epoch. State queries / non-blocking feedback do not."""
    return current_epoch(root) == int(epoch_at_approval)


# --------------------------------------------------------------------------- #
# self-repair / verification-failure limit
# --------------------------------------------------------------------------- #
def note_verification_failure(root: str) -> dict:
    a = load_autonomy(root)
    limit = int(((a.get("contract") or {}).get("limits") or {})
                .get("maximum_self_repair_attempts_per_failure", 2))
    a["consecutive_failures"] = int(a.get("consecutive_failures", 0)) + 1
    escalate = a["consecutive_failures"] > limit
    if escalate and a["status"] != "INACTIVE":
        a["status"] = "NEEDS_HUMAN"
    _save_autonomy(root, a)
    return {"consecutive_failures": a["consecutive_failures"], "limit": limit,
            "action": "NEEDS_HUMAN" if escalate else "attempt_in_scope_repair",
            "status": a["status"]}


def note_verification_success(root: str) -> None:
    a = load_autonomy(root)
    a["consecutive_failures"] = 0
    _save_autonomy(root, a)


# --------------------------------------------------------------------------- #
# goal-change confirmation
# --------------------------------------------------------------------------- #
def is_goal_change_confirmation(text: str) -> bool:
    return text.strip() == GOAL_CONFIRM_PHRASE


# --------------------------------------------------------------------------- #
# continuation packet + owner-return brief
# --------------------------------------------------------------------------- #
def _display_name(root: str):
    try:
        return getattr(identity_mod.load_identity(root), "display_name", None)
    except Exception:
        return None


def _last_checkpoint_summary(root: str):
    try:
        state = store.load_state(root)
        if state.last_checkpoint_id and state.last_checkpoint_id in state.checkpoints:
            return state.checkpoints[state.last_checkpoint_id].summary
    except Exception:
        pass
    return None


def continuation(root: str) -> dict:
    """Everything a fresh session needs to continue from repository evidence
    alone — no retold conversation required."""
    root = gitutil.repo_root(root)
    a = load_autonomy(root)
    c = a.get("contract") or {}
    git = gitutil.capture_git_state(root)
    pending = list_messages(root, pending_only=True)
    return {
        "generated_at": now_iso(),
        "project": _display_name(root),
        "branch": git["branch"],
        "head_commit": git["head_commit"],
        "dirty": git["dirty"],
        "autonomy_status": a["status"],
        "autonomy_contract_revision": a["revision"],
        "instruction_epoch": a["instruction_epoch"],
        "current_milestone": c.get("current_milestone"),
        "exact_next_action": c.get("exact_next_action"),
        "last_completed": _last_checkpoint_summary(root),
        "pending_owner_messages": pending,
        "resume_hint": "Read this continuation, refresh live git evidence, reconcile "
                       "pending owner input, then continue the exact next action if permitted.",
    }


def owner_return_brief(root: str) -> dict:
    root = gitutil.repo_root(root)
    a = load_autonomy(root)
    c = a.get("contract") or {}
    git = gitutil.capture_git_state(root)
    pending = list_messages(root, pending_only=True)
    blocked = a["status"] in ("PAUSED", "NEEDS_HUMAN", "STALE") or bool(pending)
    human_needed = a["status"] in ("NEEDS_HUMAN", "STALE") or any(
        m["classification"]["type"] in ("HUMAN_DECISION", "AMBIGUOUS") for m in pending)
    return {
        "project": _display_name(root),
        "stage": a["status"],
        "current_milestone": c.get("current_milestone"),
        "completed_while_away": _last_checkpoint_summary(root),
        "verified": f"{git['branch']} @ {git['head_commit'][:12]}"
                    + ("" if git["dirty"] else "; worktree clean"),
        "current_task": c.get("exact_next_action"),
        "exact_next_action": c.get("exact_next_action"),
        "anything_blocked": "yes" if blocked else "no",
        "human_decision_needed": "yes" if human_needed else "no",
        "pending_owner_messages": [m["raw_message"] for m in pending],
    }
