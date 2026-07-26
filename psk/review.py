"""Reviewer-governance loop: request -> decision -> import -> gate, under a
versioned reviewer policy and the active Goal Contract.

Decisions depend on fixed policy + verified evidence, not ChatGPT tone. Requests
and decisions carry policy id/version/fingerprint and goal id/revision/fingerprint;
a decision under a missing/mismatched policy or a stale goal/state is REJECTED (not
treated as a warning). Full outcomes: APPROVE / APPROVE_WITH_CONDITIONS / VETO /
NEEDS_HUMAN. A VETO permits exactly one new-evidence revision before the human is
involved.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

from . import autonomy, gitutil, identity as identity_mod, policy as policy_mod, store
from .errors import ProjectMismatchError, StateNotFoundError, ValidationError
from .models import (Authority, Decision, DecisionBinding, Event, EventType,
                     SCHEMA_VERSION, Verdict)
from .util import new_uuid, now_iso

RESERVED_HUMAN_ACTIONS = [
    "push", "merge", "deploy", "publish", "delete data", "spend money",
    "external communication", "expose secrets", "production changes",
]


def _event(t, actor, **p):
    return Event(new_uuid(), t, now_iso(), actor, SCHEMA_VERSION, p)


def _norm(v):
    if v is None:
        return None
    v = str(v).strip()
    return None if v.lower() in ("null", "none", "") else v


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
    if lines and lines[0].strip() == "---":
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
    out, cap = [], False
    for line in text.splitlines():
        if line.strip().lower() == f"## {header}".lower():
            cap = True
            continue
        if cap and line.strip().startswith("## "):
            break
        if cap:
            out.append(line)
    return "\n".join(out).strip()


def _parse_conditions(text: str) -> List[str]:
    body = _section(text, "Conditions")
    if not body or body.strip().lower() == "none":
        return []
    conds = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("- "):
            conds.append(s[2:].strip())
        elif s and s.lower() != "none":
            conds.append(s)
    return conds


# --------------------------------------------------------------------------- #
# request
# --------------------------------------------------------------------------- #
def build_review_request(path: str, *, question: str, action: str,
                         recommendation: str = "", against: str = "",
                         machine_evidence: str = "", agent_claims: str = "",
                         goal_alignment: str = "IN_SCOPE",
                         founder_policy_alignment: str = "compliant",
                         uncertainty: str = "", revision_of: Optional[str] = None,
                         actor: str = "claude") -> Path:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    pol = policy_mod.load(root)
    gc = state.goal_contract
    git = gitutil.capture_git_state(root)
    if not state.scope or not state.scope.scope_id:
        raise ValidationError("no active scope with an id")
    if not gc:
        raise ValidationError("no active goal contract (import a project genesis first)")

    revision_count = 0
    if revision_of:
        parent = state.reviews.get(revision_of)
        revision_count = (parent.get("revision_count", 0) + 1) if parent else 1

    seq = max((r.get("seq", -1) for r in state.reviews.values()), default=-1) + 1
    pid = new_uuid()
    ts = now_iso()
    rec = {
        "packet_id": pid, "seq": seq, "packet_type": "review_request",
        "project_id": ident.project_id, "repository_id": ident.repository_id,
        "review_policy_id": pol["policy_id"],
        "review_policy_version": pol["policy_version"],
        "review_policy_fingerprint": pol["fingerprint"],
        "goal_contract_id": gc["goal_id"], "goal_contract_revision": gc["revision"],
        "goal_contract_fingerprint": gc["fingerprint"],
        "branch": git["branch"], "head_commit": git["head_commit"],
        "dirty_fingerprint": git["dirty_fingerprint"],
        "scope_id": state.scope.scope_id, "scope_revision": state.scope.version,
        "question": question, "action": action,
        "status": "pending", "verdict": None, "conditions": [],
        "revision_count": revision_count, "parent_packet": revision_of,
        "created_at": ts, "decision_id": None,
        "instruction_epoch": autonomy.current_epoch(root),
    }
    state.reviews[pid] = rec
    state.updated_at = ts
    store.save_state(root, state)
    store.append_event(root, _event(EventType.REVIEW_REQUESTED, actor,
                                    packet_id=pid, action=action, revision_of=revision_of))

    fp = git["dirty_fingerprint"] or "null"
    resp = f"""```yaml
schema_version: 1
packet_type: review_decision
packet_id: {pid}
project_id: {ident.project_id}
repository_id: {ident.repository_id}
review_policy_id: {pol['policy_id']}
review_policy_version: {pol['policy_version']}
review_policy_fingerprint: {pol['fingerprint']}
goal_contract_id: {gc['goal_id']}
goal_contract_revision: {gc['revision']}
goal_contract_fingerprint: {gc['fingerprint']}
reviewed_branch: {git['branch']}
reviewed_head: {git['head_commit']}
reviewed_diff_fingerprint: {fp}
scope_id: {state.scope.scope_id}
scope_revision: {state.scope.version}
reviewer: chatgpt
decision: APPROVE | APPROVE_WITH_CONDITIONS | VETO | NEEDS_HUMAN
reviewed_at: <ISO-8601>
```

## Decision
<one of the allowed decisions>

## Rationale
<why>

## Conditions
None

## Required next action
{action}
"""
    packet = f"""# DogBuild — review request{' (revision)' if revision_of else ''}

> Review under reviewer policy `{pol['policy_id']}` v{pol['policy_version']}. Judge
> evidence against the Goal Contract, not tone. Upload with: "Review the attached
> Project State Keeper packet." No repository source code included.

```yaml
packet_type: review_request
packet_id: {pid}
project_id: {ident.project_id}
repository_id: {ident.repository_id}
review_policy_id: {pol['policy_id']}
review_policy_version: {pol['policy_version']}
review_policy_fingerprint: {pol['fingerprint']}
goal_contract_id: {gc['goal_id']}
goal_contract_revision: {gc['revision']}
goal_contract_fingerprint: {gc['fingerprint']}
branch: {git['branch']}
head: {git['head_commit']}
diff_fingerprint: {fp}
scope_id: {state.scope.scope_id}
scope_revision: {state.scope.version}
revision_count: {revision_count}
```

## Machine-collected evidence
{machine_evidence or '(none supplied)'}

## Execution-agent claims (not yet verified)
{agent_claims or recommendation or '(none supplied)'}

## Decision requested
{question}

## Exact proposed action
{action}

## Strongest case against
{against or 'None identified for this small, reversible action.'}

## Goal alignment
{goal_alignment}

## Founder-policy alignment
{founder_policy_alignment}

## Known uncertainty
{uncertainty or 'None material.'}

## Reserved human-only actions
{', '.join(RESERVED_HUMAN_ACTIONS)}

## Required response format
{resp}
"""
    out_dir = Path(root) / store.AI_DIR / "exchange" / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pid}-chatgpt-review.md"
    store.atomic_write(out_path, packet)
    return out_path


# --------------------------------------------------------------------------- #
# import
# --------------------------------------------------------------------------- #
def validate_decision(record: dict, ident, pol: dict, gc: dict, d: dict) -> str:
    if d.get("packet_type") != "review_decision":
        raise ValidationError("packet_type must be 'review_decision'")
    # policy binding
    if (d.get("review_policy_id") != pol["policy_id"]
            or str(d.get("review_policy_version")) != str(pol["policy_version"])
            or d.get("review_policy_fingerprint") != pol["fingerprint"]):
        raise ValidationError("review policy is missing or mismatched")
    # goal binding
    if (d.get("goal_contract_id") != gc["goal_id"]
            or str(d.get("goal_contract_revision")) != str(gc["revision"])
            or d.get("goal_contract_fingerprint") != gc["fingerprint"]):
        raise ValidationError("goal contract is stale or mismatched")
    # identity
    if d.get("project_id") != ident.project_id:
        raise ProjectMismatchError("decision project_id does not match this repository")
    if d.get("repository_id") != ident.repository_id:
        raise ProjectMismatchError("decision repository_id does not match this repository")
    # freshness
    if d.get("reviewed_branch") != record["branch"]:
        raise ValidationError("reviewed_branch does not match the request")
    if d.get("reviewed_head") != record["head_commit"]:
        raise ValidationError("reviewed_head is stale")
    if _norm(d.get("reviewed_diff_fingerprint")) != _norm(record["dirty_fingerprint"]):
        raise ValidationError("reviewed_diff_fingerprint does not match")
    if d.get("scope_id") != record["scope_id"] or str(d.get("scope_revision")) != str(record["scope_revision"]):
        raise ValidationError("scope does not match the request")
    if d.get("reviewer") != "chatgpt":
        raise ValidationError("unrecognized reviewer")
    verdict = d.get("decision")
    if verdict not in pol["allowed_decisions"]:
        raise ValidationError(f"decision '{verdict}' not allowed by policy")
    return verdict


def import_decision(path: str, decision_file: str, actor: str = "human") -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)
    pol = policy_mod.load(root)
    gc = state.goal_contract
    if not gc:
        raise ValidationError("no active goal contract")

    dfile = Path(decision_file)
    if not dfile.exists():
        raise StateNotFoundError(f"decision file not found: {decision_file}")
    text = dfile.read_text(encoding="utf-8")
    d = parse_decision(text)

    pid = d.get("packet_id")
    rec = state.reviews.get(pid)
    if rec is None:
        raise ValidationError(f"unknown packet_id '{pid}'")
    if rec.get("status") != "pending":
        raise ValidationError(f"packet '{pid}' is not pending")

    verdict = validate_decision(rec, ident, pol, gc, d)
    conditions = _parse_conditions(text) if verdict == "APPROVE_WITH_CONDITIONS" else []

    arch = Path(root) / store.AI_DIR / "exchange" / "archive" / pid
    arch.mkdir(parents=True, exist_ok=True)
    req = Path(root) / store.AI_DIR / "exchange" / "outbox" / f"{pid}-chatgpt-review.md"
    if req.exists():
        shutil.copyfile(req, arch / "request.md")
    shutil.copyfile(dfile, arch / "decision.md")

    dec = Decision(
        id=new_uuid(), authority=Authority.CHATGPT, verdict=Verdict(verdict),
        conditions=list(conditions), rationale=_section(text, "Rationale"),
        binding=DecisionBinding(repo_uuid=ident.project_id, branch=rec["branch"],
                                head_commit=rec["head_commit"],
                                scope_version=rec["scope_revision"], action=rec["action"]),
        evidence_ids=[], created_at=now_iso())
    state.decisions[dec.id] = dec
    rec.update({"status": "imported", "verdict": verdict, "decision_id": dec.id,
                "imported_at": now_iso(),
                "conditions": [{"text": c, "status": "open"} for c in conditions]})
    state.reviews[pid] = rec
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, _event(EventType.REVIEW_IMPORTED, actor,
                                    packet_id=pid, verdict=verdict))
    return {"packet_id": pid, "verdict": verdict, "conditions": conditions,
            "action": rec["action"]}


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #
def _latest_imported(state):
    imp = [r for r in state.reviews.values() if r.get("status") == "imported"]
    # legacy (pre-seq) records rank below new ones via the -1 default.
    return sorted(imp, key=lambda r: r.get("seq", -1))[-1] if imp else None


def gate(path: str, packet_id: Optional[str] = None) -> dict:
    root = gitutil.repo_root(path)
    state = store.load_state(root)
    pol = policy_mod.load(root)
    rec = (state.reviews.get(packet_id) if packet_id else _latest_imported(state))
    if not rec or rec.get("status") != "imported":
        raise ValidationError("no imported decision to gate")

    live = gitutil.capture_git_state(root)
    is_current = (live["head_commit"] == rec["head_commit"]
                  and _norm(live["dirty_fingerprint"]) == _norm(rec["dirty_fingerprint"]))
    policy_current = rec["review_policy_fingerprint"] == pol["fingerprint"]
    verdict = rec["verdict"]

    if not policy_current:
        result = "STOP_POLICY_MISMATCH"        # policy changed under the decision (blocking)
    elif not is_current:
        result = "STOP_STATE_CHANGED"          # historical/stale => a warning, not a blocker
    elif verdict == "VETO":
        result = "STOP_VETO"                   # current veto is blocking
    elif verdict == "NEEDS_HUMAN":
        result = "STOP_NEEDS_HUMAN"
    elif verdict == "APPROVE":
        result = "PROCEED"
    elif verdict == "APPROVE_WITH_CONDITIONS":
        result = "PROCEED_WITH_CONDITIONS"
    else:
        result = "STOP_STATE_CHANGED"

    return {"result": result, "verdict": verdict, "approved_action": rec["action"],
            "packet_id": rec["packet_id"], "conditions": rec.get("conditions", []),
            "approval_current": is_current, "policy_current": policy_current,
            "revision_count": rec.get("revision_count", 0),
            "note": "Authorizes only the exact approved action; never push/merge/deploy/"
                    "publish/delete/spend/external/secrets/production."}


# --------------------------------------------------------------------------- #
# one-revision veto loop
# --------------------------------------------------------------------------- #
def revise(path: str, packet_id: str, new_evidence: str, actor: str = "claude") -> Path:
    root = gitutil.repo_root(path)
    state = store.load_state(root)
    rec = state.reviews.get(packet_id)
    if not rec or rec.get("status") != "imported":
        raise ValidationError("can only revise an imported decision")
    if rec.get("verdict") != "VETO":
        raise ValidationError("revision is only allowed after a VETO")
    if rec.get("revision_count", 0) >= 1:
        raise ValidationError("only one automatic revision is allowed; escalate to human")
    if not new_evidence.strip():
        raise ValidationError("a revision requires new, machine-verifiable evidence")

    rec["status"] = "revised"
    state.reviews[packet_id] = rec
    store.save_state(root, state)
    store.append_event(root, _event(EventType.REVIEW_REVISED, actor, packet_id=packet_id))
    return build_review_request(
        root, question=rec["question"], action=rec["action"],
        machine_evidence=new_evidence,
        agent_claims="Revised after VETO with new machine-verifiable evidence.",
        revision_of=packet_id, actor=actor)
