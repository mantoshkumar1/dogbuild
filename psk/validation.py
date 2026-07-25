"""Structural validation for state and events.

Rejects malformed or incompatible state safely (raises typed errors) rather than
letting downstream code act on garbage. Kept as hand-rolled checks to preserve
the zero-runtime-dependency goal (no jsonschema at runtime); JSON Schema files
under psk/schemas/ document the same contract for interop.
"""

from __future__ import annotations

from typing import Any

from .errors import IncompatibleStateError, ValidationError
from .models import (
    SCHEMA_VERSION,
    Authority,
    EvidenceKind,
    EventType,
    ItemStatus,
    ReservedAction,
    Verdict,
)


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def _major(version: str) -> str:
    return str(version).split(".", 1)[0]


def check_compatible(state: dict) -> None:
    ver = state.get("schema_version")
    _require(isinstance(ver, str) and ver, "state.schema_version missing")
    if _major(ver) != _major(SCHEMA_VERSION):
        raise IncompatibleStateError(
            f"state schema_version {ver} is incompatible with {SCHEMA_VERSION}"
        )


def _check_enum(value: Any, enum_cls, field_name: str) -> None:
    valid = {m.value for m in enum_cls}
    _require(value in valid, f"{field_name} '{value}' not one of {sorted(valid)}")


def validate_state(state: Any) -> None:
    _require(isinstance(state, dict), "state must be an object")
    check_compatible(state)

    for key in ("identity", "git_state", "reserved_approvals", "updated_at"):
        _require(key in state, f"state missing required key '{key}'")

    ident = state["identity"]
    _require(isinstance(ident, dict), "identity must be an object")
    for key in ("psk_uuid", "root", "created_at"):
        _require(key in ident, f"identity missing '{key}'")
    _require(bool(ident["psk_uuid"]), "identity.psk_uuid must be non-empty")

    git = state["git_state"]
    _require(isinstance(git, dict), "git_state must be an object")
    for key in ("branch", "detached", "dirty", "captured_at"):
        _require(key in git, f"git_state missing '{key}'")

    for action in state["reserved_approvals"]:
        _check_enum(action, ReservedAction, "reserved_approvals[]")

    for iid, item in state.get("items", {}).items():
        _require(isinstance(item, dict), f"item {iid} must be an object")
        _require("status" in item, f"item {iid} missing status")
        _check_enum(item["status"], ItemStatus, f"item[{iid}].status")

    for eid, ev in state.get("evidence", {}).items():
        _require("kind" in ev, f"evidence {eid} missing kind")
        _check_enum(ev["kind"], EvidenceKind, f"evidence[{eid}].kind")

    for did, dec in state.get("decisions", {}).items():
        _require("authority" in dec and "verdict" in dec and "binding" in dec,
                 f"decision {did} missing authority/verdict/binding")
        _check_enum(dec["authority"], Authority, f"decision[{did}].authority")
        _check_enum(dec["verdict"], Verdict, f"decision[{did}].verdict")
        _require(isinstance(dec["binding"], dict), f"decision {did} binding must be object")


def validate_event(event: Any) -> None:
    _require(isinstance(event, dict), "event must be an object")
    for key in ("event_id", "type", "timestamp", "actor", "schema_version"):
        _require(key in event, f"event missing '{key}'")
    _check_enum(event["type"], EventType, "event.type")
