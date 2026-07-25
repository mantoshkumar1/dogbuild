"""Idea Parking Lot — persist out-of-scope ideas without disturbing the milestone.

Parking must never change the current milestone, acceptance criteria, exact next
action, or active scope. It only appends to `parked_ideas`.
"""

from __future__ import annotations

from typing import List

from . import gitutil, store
from .models import Event, EventType, SCHEMA_VERSION
from .util import new_uuid, now_iso


def add(path: str, *, title: str, reason: str, phase: str,
        source_agent: str = "claude") -> dict:
    root = gitutil.repo_root(path)
    state = store.load_state(root)
    idea = {
        "id": new_uuid(),
        "title": title,
        "reason": reason,
        "phase": phase,
        "source_agent": source_agent,
        "timestamp": now_iso(),
        "status": "parked",
    }
    state.parked_ideas.append(idea)  # scope / goal / milestone untouched by design
    state.updated_at = now_iso()
    store.save_state(root, state)
    store.append_event(root, Event(new_uuid(), EventType.IDEA_PARKED, now_iso(),
                                   source_agent, SCHEMA_VERSION, {"title": title}))
    return idea


def lst(path: str) -> List[dict]:
    root = gitutil.repo_root(path)
    return store.load_state(root).parked_ideas
