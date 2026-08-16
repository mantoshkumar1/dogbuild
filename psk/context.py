"""Project Context Resolver — which project/repository does this belong to?

Day 2 implements the LOCAL path: identify the repository from the working
directory + `.ai/PROJECT_IDENTITY.json`, report freshness, and export an
uploadable context packet. Cross-packet AMBIGUOUS/STALE/MISMATCH resolution during
import lands in later days; the outcome vocabulary and helpers are defined here.
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Optional

from . import authority_freshness, gitutil, identity as identity_mod, store
from .util import new_uuid, now_iso, sha256_hex


class ContextResult(str, enum.Enum):
    IDENTIFIED = "IDENTIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    MISMATCH = "MISMATCH"


def classify_execution_sources(sources: list[dict], authority_context: dict) -> dict:
    """Classify load-bearing referenced sources before bootstrap uses them.

    Managed-project adapters supply the live authority facts.  This wrapper keeps
    bootstrap/reconstruction callers on the same fail-closed primitive used by
    handoff validation without teaching context resolution GitHub-specific rules.
    """
    return authority_freshness.classify_referenced_sources(sources, authority_context)


def freshness(root: str) -> str:
    """'current' if live git matches the last-captured state, else 'stale'."""
    try:
        state = store.load_state(root)
    except Exception:
        return "unknown"
    live = gitutil.capture_git_state(root)
    same = (
        state.git_state.head_commit == live["head_commit"]
        and state.git_state.dirty == live["dirty"]
        and state.git_state.dirty_fingerprint == live["dirty_fingerprint"]
    )
    return "current" if same else "stale"


def identify_local(path: str) -> dict:
    """Resolve the local project from cwd + identity file.

    Raises NotAGitRepoError (no repo) or StateNotFoundError (not initialized) —
    the CLI maps these to exit codes 10 / 11. Returns a dict on success.
    """
    root = gitutil.repo_root(path)                 # NotAGitRepoError if not a repo
    ident = identity_mod.load_identity(root)       # StateNotFoundError if no identity
    return {
        "result": ContextResult.IDENTIFIED.value,
        "project_id": ident.project_id,
        "project_name": ident.display_name,
        "repository_id": ident.repository_id,
        "repository_name": ident.repository_name,
        "root_path": root,
        "freshness": freshness(root),
        "evidence": "cwd + .ai/PROJECT_IDENTITY.json",
    }


def context_card(path: str) -> dict:
    root = gitutil.repo_root(path)
    ident = identity_mod.load_identity(root)
    live = gitutil.capture_git_state(root)
    scope = "(not set)"
    objective = "(not set)"
    counts = {}
    try:
        state = store.load_state(root)
        if state.scope:
            scope = state.scope.description
        if state.objective:
            objective = state.objective.text
        counts = {
            "items": len(state.items),
            "decisions": len(state.decisions),
            "checkpoints": len(state.checkpoints),
        }
    except Exception:
        pass
    return {
        "project": ident.display_name,
        "project_id": ident.project_id,
        "repository": ident.repository_name,
        "repository_id": ident.repository_id,
        "branch": live["branch"],
        "head": live["head_commit"],
        "dirty_fingerprint": live["dirty_fingerprint"],
        "scope": scope,
        "objective": objective,
        "state_summary": counts,
        "freshness": freshness(root),
    }


def render_card_text(card: dict) -> str:
    return (
        f"Project: {card['project']}\n"
        f"Project ID: {card['project_id']}\n"
        f"Repository: {card['repository']}\n"
        f"Branch: {card['branch']}\n"
        f"HEAD: {card['head'] or 'unborn'}\n"
        f"Scope: {card['scope']}\n"
        f"State freshness: {card['freshness']}\n"
    )


def export_context_packet(path: str, *, purpose: str = "") -> Path:
    """Write an uploadable ChatGPT context packet under .ai/exchange/outbox/.
    Safe to upload without repository contents."""
    root = gitutil.repo_root(path)
    card = context_card(path)
    packet_id = new_uuid()
    ts = now_iso()
    out_dir = Path(root) / store.AI_DIR / "exchange" / "outbox"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{packet_id}-chat-context.md"

    lines = [
        "# DogBuild — chat context packet\n",
        "\n> Upload this to ChatGPT with: \"Review the attached DogBuild "
        "packet.\" It is safe to upload — it contains no repository "
        "source.\n\n",
        "```yaml\n",
        f"packet_id: {packet_id}\n",
        f"project_id: {card['project_id']}\n",
        f"repository_id: {card['repository_id']}\n",
        f"project_name: {card['project']}\n",
        f"repository_name: {card['repository']}\n",
        f"branch: {card['branch']}\n",
        f"head: {card['head'] or 'unborn'}\n",
        f"dirty_fingerprint: {card['dirty_fingerprint'] or 'null'}\n",
        f"packet_created_at: {ts}\n",
        "```\n\n",
        f"- **Active scope:** {card['scope']}\n",
        f"- **Current objective:** {card['objective']}\n",
        f"- **State summary:** {card['state_summary']}\n",
        f"- **State freshness:** {card['freshness']}\n",
        f"- **Purpose of this ChatGPT conversation:** {purpose or '(unspecified)'}\n",
        "\n## Freshness rules\n",
        "- Treat this packet as the source of truth over any older chat summary.\n",
        "- If your reply's project_id/repository_id/branch/head do not match this "
        "packet, it is `MISMATCH`/`STALE` and must be rejected on import.\n",
        "- Do not combine evidence from a different project.\n",
    ]
    store.atomic_write(out_path, "".join(lines))
    return out_path
