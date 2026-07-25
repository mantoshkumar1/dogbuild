"""Project Genesis — turn a mature AI discussion into an explicit, human-approved
project contract, then activate it as the Goal Contract.

An AI must never silently activate a project: import requires `human_approved: true`.
No conversation scraping / ChatGPT automation here — the packet arrives as a file.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from . import gitutil, identity as identity_mod, store
from .errors import ValidationError
from .models import Event, EventType, Scope, SCHEMA_VERSION
from .util import canonical_json, new_uuid, now_iso, sha256_hex

LIST_KEYS = {"acceptance_criteria", "explicit_exclusions", "unresolved_assumptions",
             "parked_ideas"}
REQUIRED_SCALARS = ("project_name", "core_repository", "problem", "target_user",
                    "desired_outcome", "current_milestone", "exact_first_action")


def _strip_fence(text: str) -> List[str]:
    lines = text.splitlines()
    for i, l in enumerate(lines):
        if l.strip().startswith("```") and "yaml" in l.strip():
            body = []
            for l2 in lines[i + 1:]:
                if l2.strip().startswith("```"):
                    return body
                body.append(l2)
    return lines


def parse_genesis(text: str) -> dict:
    """Minimal YAML-ish parser: top-level `key: value` scalars and `key:` /
    `key: []` lists of `- item`. Sufficient for the Genesis Packet shape."""
    d: dict = {}
    cur_list = None
    for raw in _strip_fence(text):
        line = raw.rstrip()
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("- ") and cur_list is not None:
            d.setdefault(cur_list, []).append(s[2:].strip())
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if v == "[]":
            d[k] = []
            cur_list = None
        elif v == "" and k in LIST_KEYS:
            d[k] = []
            cur_list = k
        else:
            d[k] = v
            cur_list = None
    return d


def validate_genesis(d: dict) -> None:
    if d.get("packet_type") != "project_genesis":
        raise ValidationError("packet_type must be 'project_genesis'")
    if str(d.get("schema_version")) != "1":
        raise ValidationError("unsupported genesis schema_version")
    for k in REQUIRED_SCALARS:
        if not isinstance(d.get(k), str) or not d.get(k):
            raise ValidationError(f"genesis missing required field '{k}'")
    if str(d.get("human_approved")).lower() != "true":
        raise ValidationError("genesis requires human_approved: true before import")


def _build_goal_contract(d: dict, ident, revision: int, approved_at: str) -> dict:
    content = {
        "product_name": d["project_name"],
        "core_repository": d["core_repository"],
        "problem": d["problem"],
        "target_user": d["target_user"],
        "desired_outcome": d["desired_outcome"],
        "why_now": d.get("why_now", ""),
        "current_milestone": d["current_milestone"],
        "acceptance_criteria": list(d.get("acceptance_criteria", [])),
        "explicit_exclusions": list(d.get("explicit_exclusions", [])),
        "unresolved_assumptions": list(d.get("unresolved_assumptions", [])),
        "human_only_decisions": [],
        "exact_next_action": d["exact_first_action"],
        "project_id": ident.project_id,
        "repository_id": ident.repository_id,
        "created_by": d.get("created_by", ""),
        "human_approved": True,
        "approved_at": approved_at,
    }
    fingerprint = sha256_hex(canonical_json(content))
    return {"goal_id": new_uuid(), "revision": revision, "fingerprint": fingerprint,
            "created_at": now_iso(), **content}


def import_genesis(path: str, packet_file: str, actor: str = "human",
                   approved_at: str = "") -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    state = store.load_state(root)

    pf = Path(packet_file)
    if not pf.exists():
        raise ValidationError(f"genesis packet not found: {packet_file}")
    text = pf.read_text(encoding="utf-8")
    d = parse_genesis(text)
    validate_genesis(d)

    revision = (state.goal_contract["revision"] + 1) if state.goal_contract else 1
    contract = _build_goal_contract(d, ident, revision, approved_at or now_iso())
    state.goal_contract = contract

    # Active scope now serves this milestone + goal revision.
    sid = state.scope.scope_id if (state.scope and state.scope.scope_id) else new_uuid()
    sver = (state.scope.version + 1) if state.scope else 1
    state.scope = Scope(description=contract["current_milestone"], version=sver,
                        set_at=now_iso(), scope_id=sid, goal_revision=revision)

    # Park any ideas listed in the genesis (do not implement them).
    for title in d.get("parked_ideas", []):
        state.parked_ideas.append({
            "id": new_uuid(), "title": title,
            "reason": "listed as out-of-scope in the project genesis",
            "phase": "future", "source_agent": d.get("created_by", "chatgpt"),
            "timestamp": now_iso(), "status": "parked"})

    state.updated_at = now_iso()
    store.save_state(root, state)

    # Preserve the original packet UNCHANGED.
    arch = Path(root) / store.AI_DIR / "exchange" / "archive" / "genesis"
    arch.mkdir(parents=True, exist_ok=True)
    store.atomic_write(arch / f"{contract['goal_id']}.md", text)

    store.append_event(root, Event(new_uuid(), EventType.GENESIS_IMPORTED, now_iso(),
                                   actor, SCHEMA_VERSION,
                                   {"goal_id": contract["goal_id"], "revision": revision}))
    store.append_event(root, Event(new_uuid(), EventType.GOAL_SET, now_iso(),
                                   actor, SCHEMA_VERSION,
                                   {"revision": revision, "fingerprint": contract["fingerprint"]}))
    return contract


def show(path: str) -> dict:
    root = gitutil.repo_root(path)
    state = store.load_state(root)
    if not state.goal_contract:
        raise ValidationError("no project genesis / goal contract imported yet")
    return state.goal_contract
