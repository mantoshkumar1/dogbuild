"""Test helpers: build throwaway git repositories in temp dirs."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    )
    return proc.stdout


def make_repo(with_commit: bool = True) -> str:
    d = tempfile.mkdtemp(prefix="psk-test-")
    git(d, "init", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "Test")
    if with_commit:
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# test\n")
        git(d, "add", "-A")
        git(d, "commit", "-m", "init")
    return d


def cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)


MIN_GENESIS = """schema_version: 1
packet_type: project_genesis
project_name: DogBuild
core_repository: dogbuild
problem: solo devs lose context across AI tools and repos
target_user: solo developers using ChatGPT + Claude/Codex
desired_outcome: keep agents aligned to an approved contract
current_milestone: complete one short reliable local control loop
acceptance_criteria: []
explicit_exclusions: []
unresolved_assumptions: []
parked_ideas: []
exact_first_action: build the reviewer-governance loop
created_by: chatgpt
human_approved: true
"""


def import_min_genesis(root: str):
    """Init + import a minimal approved genesis so a Goal Contract exists."""
    from psk import genesis
    fd, p = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w") as fh:
        fh.write(MIN_GENESIS)
    try:
        return genesis.import_genesis(root, p, approved_at="2026-07-25T00:00:00Z")
    finally:
        os.remove(p)


def build_review_decision(rec, ident, pol, goal, *, decision="APPROVE",
                          conditions_block="None", **ov) -> str:
    """A policy+goal+identity+freshness-bound review decision (a test fixture)."""
    fp = rec["dirty_fingerprint"] or "null"
    fields = {
        "schema_version": "1", "packet_type": "review_decision",
        "packet_id": rec["packet_id"],
        "project_id": ident.project_id, "repository_id": ident.repository_id,
        "review_policy_id": pol["policy_id"],
        "review_policy_version": pol["policy_version"],
        "review_policy_fingerprint": pol["fingerprint"],
        "goal_contract_id": goal["goal_id"],
        "goal_contract_revision": goal["revision"],
        "goal_contract_fingerprint": goal["fingerprint"],
        "reviewed_branch": rec["branch"], "reviewed_head": rec["head_commit"],
        "reviewed_diff_fingerprint": fp,
        "scope_id": rec["scope_id"], "scope_revision": rec["scope_revision"],
        "reviewer": "chatgpt", "decision": decision,
        "reviewed_at": "2026-07-25T00:00:00Z",
    }
    fields.update(ov)
    yaml = "\n".join(f"{k}: {v}" for k, v in fields.items())
    return (f"```yaml\n{yaml}\n```\n\n## Decision\n{decision}\n\n## Rationale\nok\n\n"
            f"## Conditions\n{conditions_block}\n\n## Required next action\n{rec['action']}\n")
