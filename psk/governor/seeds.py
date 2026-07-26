"""Seed policies — deterministic fixtures for testing and documentation.

The PhotoSahi research policy demonstrates the common pattern: read-only
public web research is auto-approved, repository writes require approval,
and external actions are denied.
"""

from __future__ import annotations

from .policy import ActionLevel, ExecutionPolicy, PolicyBoundaries, PolicyScope, create_policy


def photosahi_research_policy(
    repository_root: str = "/Users/example/project/photosahi",
    scratch_dir: str = "/private/tmp/dogbuild/photosahi",
) -> ExecutionPolicy:
    """Create the PhotoSahi Canadian-passport research seed policy."""
    return create_policy(
        project_id="photosahi",
        repository_root=repository_root,
        task_id="research-canadian-passport",
        branch="codex/photosahi-phases-3-12",
        permissions={
            "public_web_research": "auto",
            "repository_read": "auto",
            "temporary_file_write": "auto",
            "repository_write": "task_scoped",
            "dependency_install": "approval",
            "tests_and_builds": "auto",
            "local_server": "auto",
            "git_status_and_diff": "auto",
            "git_commit": "task_scoped",
            "branch_create": "task_scoped",
            "branch_change": "approval",
            "git_push": "deny",
            "merge": "deny",
            "deploy": "deny",
            "secrets_access": "deny",
            "destructive_commands": "approval",
            "production_access": "deny",
        },
        allowed_domains=[
            "canada.ca",
            "www.canada.ca",
            "passportindia.gov.in",
            "cgitoronto.gov.in",
        ],
        allowed_write_roots=[
            scratch_dir,
            repository_root,
        ],
        protected_paths=[
            ".env",
            "~/.ssh",
            "~/.aws",
            "production/",
        ],
        created_by="human",
    )


# The original compound command from the specification.
CLAUDE_COMPOUND_CURL = (
    'cd /some/temp/path 2>/dev/null || cd /tmp; '
    'curl -sSL -o page.html "https://www.canada.ca/en/immigration-refugees-citizenship/'
    'services/canadian-passports/photos.html"; '
    'ls -la page.html; '
    'pwd'
)
