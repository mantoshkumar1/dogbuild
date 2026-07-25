"""Working-agent declaration — an agent CLAIM, not canonical truth.

Latest declaration at `.ai/AGENT_DECLARATION.json`. The Orientation Brief compares
it against live git evidence and surfaces conflicts (it never silently trusts it).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import gitutil, store
from .models import Event, EventType, SCHEMA_VERSION
from .util import new_uuid, now_iso, pretty_json

DECL_FILE = "AGENT_DECLARATION.json"


def decl_path(root: str) -> Path:
    return Path(root) / store.AI_DIR / DECL_FILE


def record(root: str, *, building: str, changed: str, verified: str, failed: str,
           incomplete: str, next_action: str, actor_name: str = "claude") -> dict:
    root = gitutil.repo_root(root)
    live = gitutil.capture_git_state(root)
    d = {
        "actor_type": "ai_execution_agent",
        "actor_name": actor_name,
        "role": "execution_agent",
        "created_at": now_iso(),
        "claimed_head": live["head_commit"],  # what the agent believes HEAD is
        "building": building,
        "changed": changed,
        "verified": verified,
        "failed": failed,
        "incomplete": incomplete,
        "next_action": next_action,
    }
    decl_path(root).parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write(decl_path(root), pretty_json(d))
    store.append_event(root, Event(
        event_id=new_uuid(), type=EventType.DECLARATION_RECORDED, timestamp=now_iso(),
        actor=actor_name, schema_version=SCHEMA_VERSION,
        payload={"claimed_head": live["head_commit"]}))
    return d


def load_latest(root: str) -> Optional[dict]:
    p = decl_path(root)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
