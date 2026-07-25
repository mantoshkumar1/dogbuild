"""Git inspection: identity, state, dirty-worktree fingerprinting.

Assumptions (documented):
- We shell out to the `git` binary (ubiquitous, avoids a libgit2 dependency).
- Remote URLs are sanitized to strip credentials/tokens before storage
  (userinfo in `scheme://user:pass@host/...` is removed). scp-like `git@host:path`
  has no secret and is kept as-is. Unparseable remotes are redacted.
- An unborn branch (no commits yet) yields head_commit == None.
- Detached HEAD is recorded with detached=True and branch left as the raw ref.
- Dirty fingerprint = SHA-256 of `git status --porcelain=v1` output; None when clean.
"""

from __future__ import annotations

import subprocess
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

from .errors import GitError, NotAGitRepoError
from .util import now_iso, sha256_hex


def _run(repo: str, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def is_git_repo(path: str) -> bool:
    proc = _run(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def repo_root(path: str) -> str:
    if not is_git_repo(path):
        raise NotAGitRepoError(f"{path} is not inside a git work tree")
    return _run(path, ["rev-parse", "--show-toplevel"]).stdout.strip()


def current_branch(path: str) -> str:
    # symbolic-ref works even on an unborn branch (no commits yet); it fails only
    # on a detached HEAD, where we report the literal "HEAD".
    proc = _run(path, ["symbolic-ref", "--short", "-q", "HEAD"], check=False)
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return "HEAD"


def is_detached(path: str) -> bool:
    # symbolic-ref fails on detached HEAD (and returns a ref otherwise).
    proc = _run(path, ["symbolic-ref", "-q", "HEAD"], check=False)
    return proc.returncode != 0


def head_commit(path: str) -> Optional[str]:
    proc = _run(path, ["rev-parse", "HEAD"], check=False)
    if proc.returncode != 0:
        return None  # unborn branch, no commits yet
    return proc.stdout.strip()


def porcelain_status(path: str) -> str:
    return _run(path, ["status", "--porcelain=v1"]).stdout


def sanitize_remote_url(url: str) -> str:
    """Strip credentials/tokens from a remote URL before we store it."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if parts.scheme and parts.netloc and "@" in parts.netloc:
            host = parts.netloc.split("@", 1)[1]  # drop userinfo (user:pass / token)
            return urlunsplit((parts.scheme, host, parts.path, "", ""))
        return url  # scp-like git@host:path has no secret; keep as-is
    except Exception:
        return "<unparseable-remote-redacted>"


def remotes(path: str) -> List[str]:
    proc = _run(path, ["remote"], check=False)
    if proc.returncode != 0:
        return []
    out: List[str] = []
    for name in [n for n in proc.stdout.split() if n]:
        got = _run(path, ["remote", "get-url", name], check=False)
        if got.returncode == 0:
            out.append(sanitize_remote_url(got.stdout.strip()))
    return sorted(set(out))


def capture_git_state(path: str) -> dict:
    """A plain-dict snapshot of the repo's git state (facts, at capture time)."""
    detached = is_detached(path)
    porcelain = porcelain_status(path)
    dirty = bool(porcelain.strip())
    return {
        "branch": current_branch(path),
        "detached": detached,
        "head_commit": head_commit(path),
        "dirty": dirty,
        "dirty_fingerprint": sha256_hex(porcelain) if dirty else None,
        "captured_at": now_iso(),
    }
