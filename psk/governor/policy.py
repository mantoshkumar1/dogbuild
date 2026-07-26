"""Task-scoped execution policy model.

A policy is a machine-readable document that specifies which actions an agent
may perform automatically, which require approval, and which are denied —
all scoped to a specific project, repository, task, and branch.

Policies are stored in `.ai/execution_policy.json` and expire when the task
completes or is cancelled.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util import now_iso, new_uuid


class ActionLevel(str, enum.Enum):
    """Permission level for an action class."""
    AUTO = "auto"                # DogBuild handles without user interaction
    TASK_SCOPED = "task_scoped"  # Allowed within the current task's scope
    APPROVAL = "approval"        # Requires explicit user approval
    DENY = "deny"                # Blocked entirely


# Default action-class permissions (conservative).
DEFAULT_PERMISSIONS: Dict[str, ActionLevel] = {
    "public_web_research": ActionLevel.APPROVAL,
    "repository_read": ActionLevel.AUTO,
    "temporary_file_write": ActionLevel.AUTO,
    "repository_write": ActionLevel.APPROVAL,
    "dependency_install": ActionLevel.APPROVAL,
    "tests_and_builds": ActionLevel.AUTO,
    "local_server": ActionLevel.AUTO,
    "git_status_and_diff": ActionLevel.AUTO,
    "git_commit": ActionLevel.APPROVAL,
    "branch_create": ActionLevel.APPROVAL,
    "branch_change": ActionLevel.APPROVAL,
    "git_push": ActionLevel.DENY,
    "merge": ActionLevel.DENY,
    "deploy": ActionLevel.DENY,
    "secrets_access": ActionLevel.DENY,
    "destructive_commands": ActionLevel.APPROVAL,
    "production_access": ActionLevel.DENY,
}


@dataclass
class PolicyScope:
    """Identifies the exact project/task/branch this policy applies to."""
    project_id: str
    repository_root: str
    task_id: str
    branch: str


@dataclass
class PolicyBoundaries:
    """Filesystem and network boundaries."""
    allowed_domains: List[str] = field(default_factory=list)
    allowed_write_roots: List[str] = field(default_factory=list)
    protected_paths: List[str] = field(default_factory=lambda: [
        ".env", "~/.ssh", "~/.aws", "production/",
    ])


@dataclass
class ExecutionPolicy:
    """A complete task-scoped execution policy."""
    policy_id: str
    version: int
    scope: PolicyScope
    permissions: Dict[str, ActionLevel]
    boundaries: PolicyBoundaries
    created_at: str
    created_by: str
    expires_at: Optional[str] = None
    active: bool = True

    def to_dict(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "scope": {
                "project_id": self.scope.project_id,
                "repository_root": self.scope.repository_root,
                "task_id": self.scope.task_id,
                "branch": self.scope.branch,
            },
            "permissions": {k: v.value for k, v in self.permissions.items()},
            "boundaries": {
                "allowed_domains": self.boundaries.allowed_domains,
                "allowed_write_roots": self.boundaries.allowed_write_roots,
                "protected_paths": self.boundaries.protected_paths,
            },
            "created_at": self.created_at,
            "created_by": self.created_by,
            "expires_at": self.expires_at,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExecutionPolicy":
        scope = d["scope"]
        bounds = d.get("boundaries", {})
        perms = {k: ActionLevel(v) for k, v in d.get("permissions", {}).items()}
        return cls(
            policy_id=d["policy_id"],
            version=d.get("version", 1),
            scope=PolicyScope(
                project_id=scope["project_id"],
                repository_root=scope["repository_root"],
                task_id=scope["task_id"],
                branch=scope["branch"],
            ),
            permissions=perms,
            boundaries=PolicyBoundaries(
                allowed_domains=bounds.get("allowed_domains", []),
                allowed_write_roots=bounds.get("allowed_write_roots", []),
                protected_paths=bounds.get("protected_paths", []),
            ),
            created_at=d.get("created_at", ""),
            created_by=d.get("created_by", "human"),
            expires_at=d.get("expires_at"),
            active=d.get("active", True),
        )

    def permission_for(self, action_class: str) -> ActionLevel:
        """Look up the permission level for an action class."""
        return self.permissions.get(
            action_class,
            DEFAULT_PERMISSIONS.get(action_class, ActionLevel.APPROVAL),
        )

    def domain_allowed(self, domain: str) -> bool:
        """Check if a domain is in the allowed list."""
        if not self.boundaries.allowed_domains:
            return False
        d = domain.lower().lstrip(".")
        for allowed in self.boundaries.allowed_domains:
            a = allowed.lower().lstrip(".")
            if d == a or d.endswith("." + a):
                return True
        return False

    def path_in_write_root(self, path: str) -> bool:
        """Check if a path falls within an allowed write root."""
        from os.path import abspath, expanduser
        p = abspath(expanduser(path))
        for root in self.boundaries.allowed_write_roots:
            r = abspath(expanduser(root))
            if p == r or p.startswith(r + "/"):
                return True
        return False

    def path_is_protected(self, path: str) -> bool:
        """Check if a path matches a protected pattern."""
        from os.path import expanduser
        for pattern in self.boundaries.protected_paths:
            expanded = expanduser(pattern)
            if path == expanded or path.endswith("/" + pattern) or ("/" + pattern + "/") in path:
                return True
            if path.startswith(expanded):
                return True
        return False


def create_policy(
    *,
    project_id: str,
    repository_root: str,
    task_id: str,
    branch: str,
    permissions: Optional[Dict[str, str]] = None,
    allowed_domains: Optional[List[str]] = None,
    allowed_write_roots: Optional[List[str]] = None,
    protected_paths: Optional[List[str]] = None,
    created_by: str = "human",
) -> ExecutionPolicy:
    """Create a new task-scoped execution policy."""
    perms = dict(DEFAULT_PERMISSIONS)
    if permissions:
        for k, v in permissions.items():
            perms[k] = ActionLevel(v)

    bounds = PolicyBoundaries(
        allowed_domains=list(allowed_domains or []),
        allowed_write_roots=list(allowed_write_roots or []),
        protected_paths=list(protected_paths or PolicyBoundaries().protected_paths),
    )

    return ExecutionPolicy(
        policy_id=new_uuid(),
        version=1,
        scope=PolicyScope(
            project_id=project_id,
            repository_root=repository_root,
            task_id=task_id,
            branch=branch,
        ),
        permissions=perms,
        boundaries=bounds,
        created_at=now_iso(),
        created_by=created_by,
    )


# --- Storage ---

POLICY_FILE = "execution_policy.json"


def policy_path(repo_root: str) -> Path:
    from .. import store
    return store.ai_dir(repo_root) / POLICY_FILE


def save_policy(repo_root: str, pol: ExecutionPolicy) -> None:
    from .. import store
    from ..util import pretty_json
    store.atomic_write(policy_path(repo_root), pretty_json(pol.to_dict()))


def load_policy(repo_root: str) -> Optional[ExecutionPolicy]:
    p = policy_path(repo_root)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return ExecutionPolicy.from_dict(d)


def clear_policy(repo_root: str) -> None:
    p = policy_path(repo_root)
    if p.exists():
        p.unlink()
