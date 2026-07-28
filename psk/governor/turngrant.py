"""Turn-scoped owner authorization — the smallest grant that lets a direct
human instruction authorize one narrow, safe execution turn.

Motivating defect: with autonomy STOPPED, a direct owner instruction such as

    Inspect Git status, run the unit tests, summarize the result, and make no changes.

was denied, and the owner was told to run the tests by hand. Requiring a full
Autonomy Contract and a demonstration policy for a read-and-verify request is
the wrong floor: the demonstration policy is *broader* than the instruction.

A turn grant is deliberately tiny and hostile to reuse:

- created only from a current, direct human instruction that clearly asks for
  inspection and/or existing local verification and does not ask for changes;
- bound to the repository, its HEAD, the instruction epoch, and one Claude turn;
- allows exactly `repository_read` and `tests_and_builds`; never writes,
  commits, dependency changes, network, secrets, or anything outward-facing;
- expires when the turn completes, fails, is interrupted, or DogBuild exits,
  and cannot survive a new HEAD or a new instruction epoch;
- recorded in the permission audit.

It is NOT a Goal Contract revision and NOT an Autonomy Contract revision. It
grants no authority beyond one turn of looking and testing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GRANT_FILE = "turn_grant.json"

# The only action classes a turn grant may ever permit.
ALLOWED_ACTION_CLASSES: Tuple[str, ...] = ("repository_read", "tests_and_builds")

# Risk tiers a turn grant may ever permit (read-only and reversible-local).
MAX_TIER = 1


# ------------------------------------------------------------------ #
# Eligibility — conservative by construction
# ------------------------------------------------------------------ #

# Asking to look at something.
_INSPECT_VERBS = re.compile(
    r"\b(inspect|examine|read|review|look at|list|show|display|search|grep|"
    r"find|scan|audit|summari[sz]e|summary|describe|explain|report|"
    r"analyz\w*|analys\w*|diff|check)\b"
)

# Asking to run existing local verification.
_VERIFY_REQUEST = re.compile(
    r"\b(run|execute|re-?run)\b[^.;]{0,40}?\b(tests?|test suite|unit tests?|"
    r"suite|build|lint|checks?|verification)\b"
    r"|\b(verify|verification)\b"
)

# Any hint that the owner wants something changed, installed, sent, or shipped.
_MUTATION_INTENT = re.compile(
    r"\b(edit|modify|change|update|patch|write|create|make|add|append|insert|"
    r"remove|delete|drop|rename|move|refactor|rewrite|fix|repair|implement|"
    r"build me|generate|scaffold|commit|stage|amend|push|pull|merge|rebase|"
    r"reset|revert|checkout|switch|cherry-?pick|tag|release|deploy|publish|"
    r"ship|install|uninstall|upgrade|downgrade|migrate|seed|"
    r"curl|wget|fetch|download|upload|post to|send|email|api key|token|"
    r"secret|credential|password|sudo)\b"
)

# Owner assurances that no change is wanted. Stripped before the mutation scan,
# so "make no changes" does not read as "make".
_NO_CHANGE_ASSURANCE = re.compile(
    r"\b(make no changes?|no changes?|don'?t change (anything|any files?)?|"
    r"do not change (anything|any files?)?|without changing (anything)?|"
    r"do not modify (anything)?|don'?t modify (anything)?|"
    r"no modifications?|without modifying (anything)?|"
    r"do not edit (anything)?|don'?t edit (anything)?|"
    r"do not write (anything)?|make no edits?|no edits?|"
    r"read[- ]only|non-?destructive|leave everything as is|change nothing)\b"
)

# Too short to be an unambiguous instruction.
_MIN_WORDS = 4


def eligibility(message: str) -> Tuple[bool, List[str]]:
    """Decide whether *message* may create a turn grant. Returns (ok, reasons).

    Ambiguity always loses: anything that is not clearly a look-and-verify
    request gets no grant.
    """
    text = (message or "").strip()
    if not text:
        return False, ["empty instruction"]

    lowered = text.lower()
    if len(lowered.split()) < _MIN_WORDS:
        return False, ["instruction is too short to be unambiguous"]

    inspect = bool(_INSPECT_VERBS.search(lowered))
    verify = bool(_VERIFY_REQUEST.search(lowered))
    if not (inspect or verify):
        return False, ["no inspection or verification request found"]

    # Strip owner assurances before looking for mutation intent, so a promise
    # not to change anything is not itself read as a change request.
    probe = _NO_CHANGE_ASSURANCE.sub(" ", lowered)
    mutation = _MUTATION_INTENT.search(probe)
    if mutation:
        return False, [f"instruction also requests a change: '{mutation.group(0)}'"]

    reasons = []
    if inspect:
        reasons.append("requests repository inspection")
    if verify:
        reasons.append("requests existing local verification")
    reasons.append("requests no edit, commit, install, network, or outward action")
    return True, reasons


def eligible(message: str) -> bool:
    """True if *message* may create a turn grant."""
    return eligibility(message)[0]


# ------------------------------------------------------------------ #
# Grant lifecycle
# ------------------------------------------------------------------ #

def grant_path(root: str) -> Path:
    from .. import store
    return store.ai_dir(root) / GRANT_FILE


def _live_head(root: str) -> str:
    from .. import gitutil
    try:
        return gitutil.capture_git_state(root).get("head_commit") or ""
    except Exception:
        return ""


def _live_epoch(root: str) -> int:
    try:
        from .. import autonomy as autonomy_mod
        return int(autonomy_mod.current_epoch(root))
    except Exception:
        return 1


def _identity(root: str) -> Tuple[str, str]:
    try:
        from .. import identity as identity_mod
        ident = identity_mod.load_identity(root)
        return ident.project_id, ident.repository_id
    except Exception:
        return "", ""


def create(root: str, message: str, *, turn_id: Optional[str] = None) -> Optional[dict]:
    """Create a turn grant for *message*, or None if it is not eligible.

    The grant is written to `.ai/turn_grant.json` so the PreToolUse broker —
    which runs as a separate process — can enforce it directly.
    """
    ok, reasons = eligibility(message)
    if not ok:
        return None

    from .. import store, util

    project_id, repository_id = _identity(root)
    grant = {
        "turn_id": turn_id or util.new_uuid(),
        "project_id": project_id,
        "repository_id": repository_id,
        "repository_head": _live_head(root),
        "instruction_epoch": _live_epoch(root),
        "owner_message_hash": util.sha256_hex(message),
        "created_at": util.now_iso(),
        "expires_after_turn": True,
        "allowed_action_classes": list(ALLOWED_ACTION_CLASSES),
        "write_allowed": False,
        "network_allowed": False,
        "commit_allowed": False,
        "granted_because": reasons,
        "authority": "direct_human_instruction",
        "kind": "turn_scoped_owner_grant",
    }
    store.atomic_write(grant_path(root),
                       json.dumps(grant, indent=2, sort_keys=True) + "\n")
    return grant


def load(root: str) -> Optional[dict]:
    """Load the recorded grant verbatim, without validating it."""
    path = grant_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and data.get("kind") == "turn_scoped_owner_grant":
        return data
    return None


def expire(root: str, *, reason: str = "turn complete") -> Optional[dict]:
    """Remove the grant. Returns the grant that was removed, if any."""
    grant = load(root)
    path = grant_path(root)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        return grant
    if grant:
        grant = {**grant, "expired_reason": reason}
    return grant


def active(root: str) -> Optional[dict]:
    """Return the grant only if it is still valid for the live repository.

    A grant cannot survive a new HEAD or a new instruction epoch; when either
    has moved, the stale grant is removed rather than honoured.
    """
    grant = load(root)
    if not grant:
        return None

    if grant.get("repository_head") != _live_head(root):
        expire(root, reason="repository HEAD moved")
        return None

    if int(grant.get("instruction_epoch", -1)) != _live_epoch(root):
        expire(root, reason="instruction epoch changed")
        return None

    project_id, repository_id = _identity(root)
    if grant.get("repository_id") and grant["repository_id"] != repository_id:
        expire(root, reason="grant belongs to a different repository")
        return None
    if grant.get("project_id") and grant["project_id"] != project_id:
        expire(root, reason="grant belongs to a different project")
        return None

    return grant


# ------------------------------------------------------------------ #
# Enforcement helper — used by the PreToolUse broker
# ------------------------------------------------------------------ #

def permits(grant: Optional[Dict[str, Any]], action_class: str, tier_index: int) -> bool:
    """True if *grant* covers an action of *action_class* at *tier_index*."""
    if not grant:
        return False
    if tier_index > MAX_TIER:
        return False
    allowed = grant.get("allowed_action_classes") or []
    if action_class not in allowed:
        return False
    # Belt and braces: these flags are always false today, but a grant that
    # somehow carried them must still not widen past the allowed classes.
    if action_class not in ALLOWED_ACTION_CLASSES:
        return False
    return True


def describe(grant: Optional[Dict[str, Any]]) -> str:
    """Short human-readable description of a grant, for audit and messages."""
    if not grant:
        return "no turn grant"
    return (
        f"turn grant {str(grant.get('turn_id', ''))[:8]} "
        f"(read + existing tests, one turn, head "
        f"{str(grant.get('repository_head', ''))[:12]}, "
        f"epoch {grant.get('instruction_epoch')})"
    )
