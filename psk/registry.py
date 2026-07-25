"""Local project registry — `~/.project-state-keeper/projects.json` (or the dir in
env `PSK_REGISTRY_DIR`, used by tests to avoid touching HOME).

Local-only convenience index. No source code, secrets, or conversation content.
Not required for portable repository state — each repo's `.ai/` is authoritative.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from . import store
from .identity import ProjectIdentity
from .util import now_iso, pretty_json

REGISTRY_ENV = "PSK_REGISTRY_DIR"
REGISTRY_SCHEMA_VERSION = 1


def registry_dir() -> Path:
    override = os.environ.get(REGISTRY_ENV)
    return Path(override) if override else (Path.home() / ".project-state-keeper")


def registry_path() -> Path:
    return registry_dir() / "projects.json"


def load() -> dict:
    p = registry_path()
    if not p.exists():
        return {"schema_version": REGISTRY_SCHEMA_VERSION, "projects": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    registry_dir().mkdir(parents=True, exist_ok=True)
    store.atomic_write(registry_path(), pretty_json(data))


def register(identity: ProjectIdentity, *, branch: Optional[str] = None,
             head: Optional[str] = None) -> dict:
    """Upsert a project by project_id. Returns the stored entry."""
    entry = {
        "project_id": identity.project_id,
        "repository_id": identity.repository_id,
        "display_name": identity.display_name,
        "current_local_path": identity.root_path,
        "aliases": list(identity.aliases),
        "remote_fingerprint": identity.remote_fingerprint,
        "last_seen_branch": branch,
        "last_seen_head": head,
        "last_used": now_iso(),
        "parent_record": (identity.parent_system or {}).get("record")
        if identity.parent_system else None,
    }
    data = load()
    projects = [p for p in data.get("projects", []) if p.get("project_id") != identity.project_id]
    projects.append(entry)
    data["projects"] = projects
    _save(data)
    return entry


def list_entries() -> List[dict]:
    return load().get("projects", [])
