"""Low-level utilities: ids, timestamps, hashing, canonical JSON.

Decisions (documented assumptions):
- UUIDs use uuid4 (random); persistent per-repo, generated once at init.
- Timestamps are UTC, second precision, ISO-8601 with a trailing 'Z'.
- Fingerprints/hashes use SHA-256.
- Canonical JSON = sorted keys, compact separators, UTF-8 preserved. Used where a
  byte-stable representation matters (fingerprints, events.jsonl lines).
- Stored files (state.json) use pretty JSON (sorted keys, 2-space indent) for
  human diffability; still deterministic given the same state.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


def new_uuid() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    """UTC, second precision, e.g. '2026-07-25T12:34:56Z'. The value is a
    real-time fact (not deterministic across runs); the *format* is fixed."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_hex(data: "str | bytes") -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Byte-stable JSON for fingerprints and append-only event lines."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def pretty_json(obj: Any) -> str:
    """Human-diffable JSON for state.json (still deterministic per state)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
