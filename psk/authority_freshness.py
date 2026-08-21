"""Deterministic authority/freshness classification for execution sources.

Seeing a branch, pull request, document, or command is not proof it is current
policy.  Adapters provide the live repository/task facts; this module makes the
precedence decision deterministic and intentionally never uses timestamps.
"""

from __future__ import annotations

import enum
from typing import Any, Dict, Iterable, Optional


class AuthorityClass(str, enum.Enum):
    CURRENT_AUTHORITATIVE = "CURRENT_AUTHORITATIVE"
    ACTIVE_AUTHORIZED_WIP = "ACTIVE_AUTHORIZED_WIP"
    PAUSED_UNMERGED = "PAUSED_UNMERGED"
    SUPERSEDED_OR_HISTORICAL = "SUPERSEDED_OR_HISTORICAL"
    UNKNOWN_OR_CONFLICTING = "UNKNOWN_OR_CONFLICTING"


def _present(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _same_task(source: Dict[str, Any], context: Dict[str, Any]) -> bool:
    return _present(source.get("task_id")) and source.get("task_id") == context.get("current_task_id")


def _promotion_matches(source: Dict[str, Any], context: Dict[str, Any]) -> bool:
    """Only a current, exact-scope founder/strategy promotion can pre-promote WIP."""
    promotion = source.get("explicit_promotion")
    if not isinstance(promotion, dict):
        return False
    return (
        promotion.get("current") is True
        and promotion.get("authority") in {"founder", "strategy"}
        and _present(promotion.get("decision_id"))
        and promotion.get("repository") == context.get("repository")
        and promotion.get("scope") in {"repository-policy", f"task:{context.get('current_task_id')}"}
    )


def classify_authority(source: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Classify one source against live, adapter-supplied authority facts.

    Required context: ``repository``, ``default_branch``, and
    ``current_authoritative_source``.  The source's ``observed_at`` timestamp is
    deliberately ignored: recency cannot promote non-authoritative work.
    """
    replacement = context.get("current_authoritative_source")
    result: Dict[str, Any] = {
        "source_id": source.get("source_id"),
        "classification": AuthorityClass.UNKNOWN_OR_CONFLICTING.value,
        "reason": "authority_evidence_incomplete",
        "authoritative_replacement": replacement,
    }
    if not isinstance(source, dict) or not isinstance(context, dict):
        return result
    if not _present(context.get("repository")) or not _present(context.get("default_branch")):
        return result
    if source.get("repository") != context.get("repository"):
        result["reason"] = "repository_mismatch"
        return result
    if source.get("conflicting_authority") is True:
        result["reason"] = "conflicting_authority_evidence"
        return result
    if source.get("superseded") is True or source.get("lineage_status") in {"superseded", "historical", "stale"}:
        result.update(
            classification=AuthorityClass.SUPERSEDED_OR_HISTORICAL.value,
            reason="superseded_or_historical_source",
        )
        return result
    if _promotion_matches(source, context):
        result.update(
            classification=AuthorityClass.CURRENT_AUTHORITATIVE.value,
            reason="current_exact_scope_founder_or_strategy_promotion",
            authoritative_replacement=source.get("source_id"),
        )
        return result

    merged = source.get("commit_in_authoritative_history") is True
    on_default_branch = source.get("branch") == context.get("default_branch")
    if merged and on_default_branch and source.get("current_revision", True) is True:
        result.update(
            classification=AuthorityClass.CURRENT_AUTHORITATIVE.value,
            reason="current_merged_authoritative_branch_source",
            authoritative_replacement=source.get("source_id"),
        )
        return result

    paused = source.get("paused") is True or source.get("task_lifecycle") == "paused"
    unmerged = source.get("pr_state") == "open" and not merged
    if paused and unmerged:
        result.update(
            classification=AuthorityClass.PAUSED_UNMERGED.value,
            reason="paused_unmerged_work_is_not_current_policy",
        )
        return result
    if source.get("pr_state") == "closed" and not merged:
        result.update(
            classification=AuthorityClass.SUPERSEDED_OR_HISTORICAL.value,
            reason="closed_unmerged_source_is_historical",
        )
        return result
    if unmerged and source.get("task_authorized") is True and _same_task(source, context):
        result.update(
            classification=AuthorityClass.ACTIVE_AUTHORIZED_WIP.value,
            reason="active_authorized_task_local_workstream",
        )
        return result
    if unmerged:
        result["reason"] = "unmerged_source_not_authorized_for_current_task"
        return result
    if merged and not on_default_branch:
        result["reason"] = "merged_commit_not_proven_current_default_branch_policy"
        return result
    return result


def may_use_as_current_policy(source: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Return a policy-use decision, preserving an authoritative replacement pointer."""
    classified = classify_authority(source, context)
    kind = classified["classification"]
    allowed = kind == AuthorityClass.CURRENT_AUTHORITATIVE.value
    if kind == AuthorityClass.ACTIVE_AUTHORIZED_WIP.value:
        allowed = (
            context.get("requested_scope") == "task-local"
            and _same_task(source, context)
            and source.get("task_authorized") is True
        )
    classified["allowed"] = allowed
    if allowed:
        classified["reason"] = (
            "current_authoritative_source" if kind == AuthorityClass.CURRENT_AUTHORITATIVE.value
            else "authorized_task_local_wip_only"
        )
    elif kind == AuthorityClass.PAUSED_UNMERGED.value:
        classified["reason"] = "capability_not_currently_implemented"
    elif kind == AuthorityClass.ACTIVE_AUTHORIZED_WIP.value:
        classified["reason"] = "active_wip_cannot_define_repository_wide_policy"
    return classified


def classify_referenced_sources(sources: Iterable[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Classify all load-bearing sources deterministically and fail closed on any denial."""
    decisions = [may_use_as_current_policy(source, context) for source in sources]
    return {
        "decisions": decisions,
        "safe_to_use": all(decision["allowed"] for decision in decisions),
        "authoritative_replacement": context.get("current_authoritative_source"),
    }
