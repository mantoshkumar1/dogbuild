"""Deterministic local CLI (Day 2).

`statekeeper` (installed entry point) == `python -m psk`. Subcommands over
`psk.core` with stable exit codes (see psk/exit_codes.py). Human output by default;
`--json` for machine-readable output where applicable.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import (__version__, context, core, gitutil, identity as identity_mod,
               registry, review, store)
from .errors import (
    AmbiguousContextError,
    IncompatibleStateError,
    NotAGitRepoError,
    ProjectMismatchError,
    PSKError,
    StateExistsError,
    StateNotFoundError,
    ValidationError,
)
from .exit_codes import (
    AMBIGUOUS_CONTEXT,
    INTERNAL_ERROR,
    INVALID_USAGE,
    MALFORMED_STATE,
    NO_REPOSITORY,
    NOT_INITIALIZED,
    PROJECT_MISMATCH,
    SUCCESS,
)
from .projection import render_markdown

PARENT_NAME = "Revenue Opportunity Lab"
PARENT_RECORD = "~/Desktop/project/revenue-opportunity-lab/projects/project-state-keeper.md"


def _emit(obj_human: str, obj_json, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj_json, indent=2, sort_keys=True))
    else:
        print(obj_human, end="" if obj_human.endswith("\n") else "\n")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def _cmd_init(args) -> int:
    state = core.initialize(
        args.path, objective=args.objective, force=args.force,
        display_name=args.name, aliases=args.alias or None,
        parent_name=PARENT_NAME, parent_record=PARENT_RECORD,
    )
    ident = identity_mod.load_identity(state.identity.root)
    registry.register(ident, branch=state.git_state.branch,
                      head=state.git_state.head_commit)
    _emit(f"Initialized {store.AI_DIR}/ state and identity "
          f"(project {ident.display_name}, id {ident.project_id}) at {state.identity.root}",
          {"initialized": True, "project_id": ident.project_id,
           "repository_id": ident.repository_id, "root": state.identity.root},
          args.json)
    return SUCCESS


def _cmd_show(args) -> int:
    root = gitutil.repo_root(args.path)
    print(render_markdown(store.load_state(root)), end="")
    return SUCCESS


def _cmd_status(args) -> int:
    card = context.context_card(args.path)
    _emit(context.render_card_text(card), card, args.json)
    return SUCCESS


def _cmd_ctx_identify(args) -> int:
    res = context.identify_local(args.path)
    _emit(f"{res['result']}: {res['project_name']} ({res['project_id']}), "
          f"repo {res['repository_name']}, freshness {res['freshness']}",
          res, args.json)
    return SUCCESS


def _cmd_ctx_show(args) -> int:
    card = context.context_card(args.path)
    _emit(context.render_card_text(card), card, args.json)
    return SUCCESS


def _cmd_ctx_list(args) -> int:
    entries = registry.list_entries()
    safe = [{k: e.get(k) for k in ("project_id", "repository_id", "display_name",
                                    "current_local_path", "aliases", "last_seen_branch",
                                    "last_seen_head", "last_used")} for e in entries]
    if args.json:
        print(json.dumps(safe, indent=2, sort_keys=True))
    else:
        if not safe:
            print("(no projects registered)")
        for e in safe:
            print(f"- {e['display_name']}  ({e['project_id']})  "
                  f"path={e['current_local_path']}  branch={e['last_seen_branch']}")
    return SUCCESS


def _cmd_ctx_register(args) -> int:
    root = gitutil.repo_root(args.path)
    ident = identity_mod.ensure_identity(
        root, display_name=args.name, aliases=args.alias or None,
        parent_name=PARENT_NAME, parent_record=PARENT_RECORD,
    )
    git = gitutil.capture_git_state(root)
    registry.register(ident, branch=git["branch"], head=git["head_commit"])
    _emit(f"Registered {ident.display_name} ({ident.project_id})",
          {"project_id": ident.project_id, "repository_id": ident.repository_id},
          args.json)
    return SUCCESS


def _cmd_ctx_export(args) -> int:
    if args.for_ != "chatgpt":
        print("error: only --for chatgpt is supported", file=sys.stderr)
        return 2
    out = context.export_context_packet(args.path, purpose=args.purpose or "")
    _emit(f"Wrote context packet: {out}", {"packet": str(out)}, args.json)
    return SUCCESS


def _cmd_review_request(args) -> int:
    out = review.build_review_request(
        args.path, question=args.question, action=args.action,
        recommendation=args.recommendation or "", against=args.against or "",
        evidence=args.evidence or "", uncertainty=args.uncertainty or "",
    )
    _emit(f"Wrote review request packet: {out}\nUpload it to ChatGPT with: "
          f"\"Review the attached Project State Keeper packet.\"",
          {"packet": str(out)}, args.json)
    return SUCCESS


def _cmd_review_import(args) -> int:
    summary = review.import_decision(args.path, args.decision_file)
    _emit(f"Imported {summary['verdict']} for action: {summary['action']} "
          f"(packet {summary['packet_id']}; archived to {summary['archived_to']})",
          summary, args.json)
    return SUCCESS


def _cmd_review_gate(args) -> int:
    g = review.gate(args.path, packet_id=args.packet)
    human = (
        f"Result: {g['result']}\n"
        f"Decision: {g['decision']} by {g['reviewer']}\n"
        f"Approved action: {g['approved_action']}\n"
        f"Packet: {g['packet_id']}\n"
        f"Project: {g['project']}\n"
        f"Branch/HEAD: {g['branch']} @ {g['head']}\n"
        f"Scope: {g['scope']}\n"
        f"Approval current: {g['approval_current']}\n"
        f"{g['note']}\n"
    )
    _emit(human, g, args.json)
    return SUCCESS


def _cmd_reserved(args) -> int:
    print(f"'{args._reserved}' is reserved for a later day (import/selection "
          f"logic). Not implemented in this MVP build.", file=sys.stderr)
    return SUCCESS


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="statekeeper",
                                description="Project State Keeper — local CLI")
    p.add_argument("--version", action="version", version=f"statekeeper {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="initialize .ai/ state + identity in a git repo")
    pi.add_argument("path", nargs="?", default=".")
    pi.add_argument("--objective", default=None)
    pi.add_argument("--name", default=None, help="display name")
    pi.add_argument("--alias", action="append", help="repeatable alias")
    pi.add_argument("--force", action="store_true")
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(func=_cmd_init)

    ps = sub.add_parser("show", help="print the Markdown projection of state")
    ps.add_argument("path", nargs="?", default=".")
    ps.set_defaults(func=_cmd_show)

    pst = sub.add_parser("status", help="print a concise context/status card")
    pst.add_argument("path", nargs="?", default=".")
    pst.add_argument("--json", action="store_true")
    pst.set_defaults(func=_cmd_status)

    pc = sub.add_parser("context", help="project context resolution")
    csub = pc.add_subparsers(dest="ctx_cmd", required=True)

    ci = csub.add_parser("identify", help="identify the local project from cwd + git")
    ci.add_argument("path", nargs="?", default=".")
    ci.add_argument("--json", action="store_true")
    ci.set_defaults(func=_cmd_ctx_identify)

    cs = csub.add_parser("show", help="print a concise context card")
    cs.add_argument("path", nargs="?", default=".")
    cs.add_argument("--json", action="store_true")
    cs.set_defaults(func=_cmd_ctx_show)

    cl = csub.add_parser("list", help="known local projects (no secrets)")
    cl.add_argument("--json", action="store_true")
    cl.set_defaults(func=_cmd_ctx_list)

    cr = csub.add_parser("register", help="ensure identity + add/update local registry")
    cr.add_argument("path", nargs="?", default=".")
    cr.add_argument("--name", default=None)
    cr.add_argument("--alias", action="append")
    cr.add_argument("--json", action="store_true")
    cr.set_defaults(func=_cmd_ctx_register)

    ce = csub.add_parser("export", help="write an uploadable ChatGPT context packet")
    ce.add_argument("path", nargs="?", default=".")
    ce.add_argument("--for", dest="for_", required=True, choices=["chatgpt"])
    ce.add_argument("--purpose", default=None)
    ce.add_argument("--json", action="store_true")
    ce.set_defaults(func=_cmd_ctx_export)

    for name in ("choose", "verify"):
        rp = csub.add_parser(name, help="(reserved for a later day)")
        rp.add_argument("rest", nargs="*")
        rp.set_defaults(func=_cmd_reserved, _reserved=name)

    # review: one APPROVE round-trip (request -> import -> gate)
    pr = sub.add_parser("review", help="ChatGPT review round-trip (Day 3 slice)")
    rsub = pr.add_subparsers(dest="review_cmd", required=True)

    rr = rsub.add_parser("request", help="generate a ChatGPT review packet")
    rr.add_argument("path", nargs="?", default=".")
    rr.add_argument("--question", required=True)
    rr.add_argument("--action", required=True)
    rr.add_argument("--recommendation", default=None)
    rr.add_argument("--against", default=None)
    rr.add_argument("--evidence", default=None)
    rr.add_argument("--uncertainty", default=None)
    rr.add_argument("--json", action="store_true")
    rr.set_defaults(func=_cmd_review_request)

    rim = rsub.add_parser("import", help="import + validate a ChatGPT decision file")
    rim.add_argument("decision_file")
    rim.add_argument("path", nargs="?", default=".")
    rim.add_argument("--json", action="store_true")
    rim.set_defaults(func=_cmd_review_import)

    rg = rsub.add_parser("gate", help="evaluate the imported decision (APPROVE->PROCEED)")
    rg.add_argument("path", nargs="?", default=".")
    rg.add_argument("--packet", default=None)
    rg.add_argument("--json", action="store_true")
    rg.set_defaults(func=_cmd_review_gate)

    return p


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except NotAGitRepoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return NO_REPOSITORY
    except StateExistsError as exc:
        print(f"error: already initialized — {exc} (use --force to reinitialize)",
              file=sys.stderr)
        return INVALID_USAGE
    except StateNotFoundError as exc:
        print(f"error: not initialized — {exc}", file=sys.stderr)
        return NOT_INITIALIZED
    except AmbiguousContextError as exc:
        print(f"ambiguous: {exc}", file=sys.stderr)
        return AMBIGUOUS_CONTEXT
    except ProjectMismatchError as exc:
        print(f"mismatch: {exc}", file=sys.stderr)
        return PROJECT_MISMATCH
    except (ValidationError, IncompatibleStateError) as exc:
        print(f"malformed: {exc}", file=sys.stderr)
        return MALFORMED_STATE
    except PSKError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return INTERNAL_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
