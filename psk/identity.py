"""Persistent project/repository identity: `.ai/PROJECT_IDENTITY.json`.

Identity survives moving the repository (paths are informational, not identity).
Authenticated remote URLs are never stored — only a hash fingerprint of the
sanitized remote(s), or null.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import gitutil, store
from .errors import StateNotFoundError, ValidationError
from .util import new_uuid, now_iso, pretty_json, sha256_hex

IDENTITY_FILE = "PROJECT_IDENTITY.json"
IDENTITY_SCHEMA_VERSION = 1


@dataclass
class ProjectIdentity:
    schema_version: int
    project_id: str
    display_name: str
    repository_id: str
    repository_name: str
    root_path: str
    remote_fingerprint: Optional[str]
    aliases: List[str] = field(default_factory=list)
    parent_system: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "display_name": self.display_name,
            "repository_id": self.repository_id,
            "repository_name": self.repository_name,
            "root_path": self.root_path,
            "remote_fingerprint": self.remote_fingerprint,
            "aliases": list(self.aliases),
            "parent_system": self.parent_system,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectIdentity":
        return cls(
            schema_version=d["schema_version"],
            project_id=d["project_id"],
            display_name=d["display_name"],
            repository_id=d["repository_id"],
            repository_name=d["repository_name"],
            root_path=d.get("root_path", ""),
            remote_fingerprint=d.get("remote_fingerprint"),
            aliases=list(d.get("aliases", [])),
            parent_system=d.get("parent_system"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
        )


def identity_path(root: str) -> Path:
    return Path(root) / store.AI_DIR / IDENTITY_FILE


def identity_exists(root: str) -> bool:
    return identity_path(root).exists()


def _remote_fingerprint(root: str) -> Optional[str]:
    remotes = gitutil.remotes(root)  # already credential-stripped
    if not remotes:
        return None
    return sha256_hex(";".join(sorted(remotes)))


def load_identity(root: str) -> ProjectIdentity:
    p = identity_path(root)
    if not p.exists():
        raise StateNotFoundError(f"no project identity at {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{IDENTITY_FILE} is not valid JSON: {exc}") from exc
    for key in ("project_id", "repository_id", "schema_version"):
        if key not in d:
            raise ValidationError(f"{IDENTITY_FILE} missing '{key}'")
    return ProjectIdentity.from_dict(d)


def _save(root: str, identity: ProjectIdentity) -> None:
    identity_path(root).parent.mkdir(parents=True, exist_ok=True)
    store.atomic_write(identity_path(root), pretty_json(identity.to_dict()))


def ensure_identity(root: str, *, display_name: Optional[str] = None,
                    aliases: Optional[List[str]] = None,
                    parent_name: Optional[str] = None,
                    parent_record: Optional[str] = None) -> ProjectIdentity:
    """Create the identity file if absent; otherwise refresh mutable, non-identity
    fields (root_path, updated_at) so identity survives repository moves."""
    if bool(parent_name) != bool(parent_record):
        raise ValidationError(
            "upstream source metadata requires both a name and a record"
        )
    requested_parent = (
        {"name": parent_name, "record": parent_record}
        if parent_name and parent_record
        else None
    )
    repo_name = os.path.basename(os.path.normpath(root))
    if identity_exists(root):
        ident = load_identity(root)
        changed = False
        if ident.root_path != root:
            ident.root_path = root
            changed = True
        if aliases:
            merged = sorted(set(ident.aliases) | set(aliases))
            if merged != ident.aliases:
                ident.aliases = merged
                changed = True
        if requested_parent and ident.parent_system != requested_parent:
            ident.parent_system = requested_parent
            changed = True
        if changed:
            ident.updated_at = now_iso()
            _save(root, ident)
        return ident

    ts = now_iso()
    ident = ProjectIdentity(
        schema_version=IDENTITY_SCHEMA_VERSION,
        project_id=new_uuid(),
        display_name=display_name or repo_name,
        repository_id=new_uuid(),
        repository_name=repo_name,
        root_path=root,
        remote_fingerprint=_remote_fingerprint(root),
        aliases=sorted(set(aliases or [])),
        parent_system=requested_parent,
        created_at=ts,
        updated_at=ts,
    )
    _save(root, ident)
    return ident
