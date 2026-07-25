"""Operating mode — which execution agent is active, reviewer, human override.

Stored at `.ai/OPERATING_MODE.json`. Single-executor for now (Claude); Codex
compatibility is preserved in the protocol but Codex is not required.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import store
from .util import now_iso, pretty_json

MODE_FILE = "OPERATING_MODE.json"

DEFAULT = {
    "active_execution_agent": "claude",
    "codex_status": "temporarily_unavailable",
    "cursor_status": "not_in_current_scope",
    "review_authority": "chatgpt",
    "human_override": "always",
}


def mode_path(root: str) -> Path:
    return Path(root) / store.AI_DIR / MODE_FILE


def load(root: str) -> dict:
    p = mode_path(root)
    if not p.exists():
        return dict(DEFAULT)
    return json.loads(p.read_text(encoding="utf-8"))


def save(root: str, mode: dict) -> None:
    mode_path(root).parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write(mode_path(root), pretty_json(mode))


def ensure(root: str) -> dict:
    p = mode_path(root)
    if not p.exists():
        save(root, dict(DEFAULT))
    return load(root)


def set_active_agent(root: str, agent: str) -> dict:
    mode = load(root)
    mode["active_execution_agent"] = agent
    mode["updated_at"] = now_iso()
    save(root, mode)
    return mode
