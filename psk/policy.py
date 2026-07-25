"""Versioned reviewer policy — so decisions depend on fixed rules, not ChatGPT tone.

The canonical policy lives at `policies/dogbuild-default-reviewer.yaml`. Its content
is parsed to a normalized dict and fingerprinted deterministically; requests and
decisions carry the policy id/version/fingerprint so a decision made under a
different (or missing) policy is rejected.
"""

from __future__ import annotations

from pathlib import Path

from . import gitutil
from .errors import ValidationError
from .util import canonical_json, sha256_hex

POLICY_REL = "policies/dogbuild-default-reviewer.yaml"


def _coerce(v: str):
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    return v


def parse_policy(text: str) -> dict:
    """Indentation-aware parse: top-level scalars, top-level lists, and one nested
    map level (behavior:). Sufficient for the policy shape."""
    d: dict = {}
    cur = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0:
            if line.endswith(":"):
                cur = line[:-1].strip()
                d[cur] = None
            else:
                k, v = line.split(":", 1)
                d[k.strip()] = _coerce(v.strip())
                cur = None
        else:
            if line.startswith("- "):
                if not isinstance(d.get(cur), list):
                    d[cur] = []
                d[cur].append(line[2:].strip())
            elif ":" in line:
                if not isinstance(d.get(cur), dict):
                    d[cur] = {}
                k, v = line.split(":", 1)
                d[cur][k.strip()] = _coerce(v.strip())
    return d


def policy_path(root: str) -> Path:
    return Path(root) / POLICY_REL


def load(root: str) -> dict:
    root = gitutil.repo_root(root)
    p = policy_path(root)
    if not p.exists():
        # Fall back to the policy bundled with the package (default for any repo).
        p = Path(__file__).parent / "policies" / "dogbuild-default-reviewer.yaml"
    if not p.exists():
        raise ValidationError(f"reviewer policy not found ({POLICY_REL} or bundled default)")
    d = parse_policy(p.read_text(encoding="utf-8"))
    for k in ("policy_id", "policy_version", "allowed_decisions"):
        if k not in d:
            raise ValidationError(f"reviewer policy missing '{k}'")
    d["fingerprint"] = fingerprint(d)
    return d


def fingerprint(policy: dict) -> str:
    content = {k: v for k, v in policy.items() if k != "fingerprint"}
    return sha256_hex(canonical_json(content))


def show(root: str) -> dict:
    return load(root)


def verify(root: str) -> dict:
    d = load(root)
    checks = {
        "policy_present": True,
        "has_id": bool(d.get("policy_id")),
        "has_version": d.get("policy_version") is not None,
        "has_allowed_decisions": bool(d.get("allowed_decisions")),
        "fingerprint_stable": fingerprint(d) == d["fingerprint"],
    }
    return {"ok": all(checks.values()), "policy_id": d["policy_id"],
            "policy_version": d["policy_version"], "fingerprint": d["fingerprint"],
            "checks": checks}
