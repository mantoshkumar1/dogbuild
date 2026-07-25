"""Deterministic local CLI (Day 2).

`statekeeper` (installed entry point) == `python -m psk`. Subcommands over
`psk.core` with stable exit codes (see psk/exit_codes.py). Human output by default;
`--json` for machine-readable output where applicable.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import (__version__, agentmode, brief as brief_mod, context, core,
               declaration, genesis as genesis_mod, gitutil, goal as goal_mod,
               handoff as handoff_mod, human as human_mod, identity as identity_mod,
               install as install_mod, park as park_mod, policy as policy_mod,
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
        machine_evidence=args.evidence or "", uncertainty=args.uncertainty or "",
    )
    _emit(f"Wrote review request packet: {out}\nUpload it to ChatGPT with: "
          f"\"Review the attached Project State Keeper packet.\"",
          {"packet": str(out)}, args.json)
    return SUCCESS


def _cmd_review_import(args) -> int:
    s = review.import_decision(args.path, args.decision_file)
    _emit(f"Imported {s['verdict']} (packet {s['packet_id']}); "
          f"conditions: {s['conditions'] or 'None'}", s, args.json)
    return SUCCESS


def _cmd_review_gate(args) -> int:
    g = review.gate(args.path, packet_id=args.packet)
    human = (
        f"Result: {g['result']}\n"
        f"Verdict: {g['verdict']}\n"
        f"Approved action: {g['approved_action']}\n"
        f"Packet: {g['packet_id']}\n"
        f"Conditions: {g['conditions'] or 'None'}\n"
        f"Approval current: {g['approval_current']} | policy current: {g['policy_current']}\n"
        f"{g['note']}\n"
    )
    _emit(human, g, args.json)
    return SUCCESS


def _cmd_review_revise(args) -> int:
    out = review.revise(args.path, args.packet, args.evidence)
    _emit(f"Created ONE revised request after VETO: {out}", {"packet": str(out)}, args.json)
    return SUCCESS


def _cmd_policy_show(args) -> int:
    _emit_json_or(policy_mod.show(args.path), args.json,
                  lambda p: f"{p['policy_id']} v{p['policy_version']} "
                            f"(fingerprint {p['fingerprint'][:12]})")
    return SUCCESS


def _cmd_policy_verify(args) -> int:
    v = policy_mod.verify(args.path)
    human = f"policy verify: {'OK' if v['ok'] else 'FAILED'} " \
            f"({v['policy_id']} v{v['policy_version']})\n" + \
            "".join(f"  {k}: {val}\n" for k, val in v["checks"].items())
    _emit(human, v, args.json)
    return SUCCESS


def _cmd_human_show(args) -> int:
    b = human_mod.show(args.path)
    human = (f"Why you are needed: {b['why_needed']}\n"
             f"Decision required:  {b['decision_required']}\n"
             f"Options:            {b['options']}\n"
             f"Recommendation:     {b['recommendation']}\n"
             f"Paused step:        {b['paused_step']}\n"
             f"Project:            {b['project']}  HEAD: {b['current_head']}  "
             f"goal rev: {b['goal_contract_revision']}\n")
    _emit(human, b, args.json)
    return SUCCESS


def _cmd_human_decide(args) -> int:
    rec = human_mod.decide(args.path, args.decision_file)
    _emit(f"Recorded human decision: {rec['choice']} (scope_changed={rec['scope_changed']})",
          rec, args.json)
    return SUCCESS


def _cmd_resume_verify(args) -> int:
    r = human_mod.resume_verify(args.path, decision_id=args.decision)
    _emit(f"resume verify: {r['result']} (choice: {r['choice']})", r, args.json)
    return SUCCESS


def _cmd_brief(args) -> int:
    fields, warnings = brief_mod.build(args.path)
    _emit(brief_mod.render_text(fields, warnings),
          {**fields, "warnings": warnings}, args.json)
    return SUCCESS


def _cmd_genesis_import(args) -> int:
    gc = genesis_mod.import_genesis(args.path, args.packet_file, approved_at=args.approved_at or "")
    _emit(f"Imported project genesis: {gc['product_name']} (goal rev {gc['revision']}, "
          f"fingerprint {gc['fingerprint'][:12]}); milestone: {gc['current_milestone']}",
          gc, args.json)
    return SUCCESS


def _cmd_genesis_show(args) -> int:
    _emit_json_or(genesis_mod.show(args.path), args.json,
                  lambda gc: f"{gc['product_name']} — milestone: {gc['current_milestone']}")
    return SUCCESS


def _cmd_goal_show(args) -> int:
    _emit_json_or(goal_mod.show(args.path), args.json,
                  lambda gc: f"{gc['product_name']} goal rev {gc['revision']}: {gc['current_milestone']}")
    return SUCCESS


def _cmd_goal_verify(args) -> int:
    v = goal_mod.verify(args.path)
    human = f"goal verify: {'OK' if v['ok'] else 'FAILED'} (rev {v['revision']})\n" + \
            "".join(f"  {k}: {val}\n" for k, val in v["checks"].items())
    _emit(human, v, args.json)
    return SUCCESS


def _cmd_park_add(args) -> int:
    idea = park_mod.add(args.path, title=args.title, reason=args.reason, phase=args.phase)
    _emit(f"Parked: {idea['title']} (phase: {idea['phase']})", idea, args.json)
    return SUCCESS


def _cmd_park_list(args) -> int:
    ideas = park_mod.lst(args.path)
    if args.json:
        print(json.dumps(ideas, indent=2, sort_keys=True))
    else:
        if not ideas:
            print("(no parked ideas)")
        for i in ideas:
            print(f"- [{i['status']}] {i['title']}  (phase: {i['phase']})")
    return SUCCESS


def _emit_json_or(obj, as_json, human_fn) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
    else:
        print(human_fn(obj))


def _cmd_declare(args) -> int:
    agentmode.ensure(gitutil.repo_root(args.path))
    d = declaration.record(
        args.path, building=args.building, changed=args.changed,
        verified=args.verified, failed=args.failed, incomplete=args.incomplete,
        next_action=args.next_action, actor_name=args.actor or "claude",
        alignment_status=args.alignment, goal_revision=args.goal_rev,
        alignment_explanation=args.alignment_why or "",
    )
    _emit(f"Recorded declaration by {d['actor_name']} (claimed_head "
          f"{(d['claimed_head'] or 'unborn')[:12]})", d, args.json)
    return SUCCESS


def _cmd_handoff_create(args) -> int:
    agentmode.ensure(gitutil.repo_root(args.path))
    pid, out = handoff_mod.create(
        args.path, to_agent=args.to, task=args.task,
        acceptance=args.acceptance or "", next_action=args.next_action or "")
    _emit(f"Created handoff to {args.to}: {out}", {"packet_id": pid, "path": str(out)},
          args.json)
    return SUCCESS


def _cmd_handoff_show(args) -> int:
    rec = handoff_mod.show(args.path)
    human = (f"Handoff {rec['packet_id']} -> {rec['target_agent']} "
             f"[{rec['status']}]\nTask: {rec['task']}\n"
             f"Branch/HEAD: {rec['branch']} @ {rec['head_commit']}\n"
             f"Instruction source: {rec['instruction_source']}\n")
    _emit(human, rec, args.json)
    return SUCCESS


def _cmd_handoff_consume(args) -> int:
    rec = handoff_mod.consume(args.path, packet_id=args.packet, as_agent=args.as_agent)
    _emit(f"Consumed handoff {rec['packet_id']} as {rec['consumed_by']}; "
          f"active agent now {rec['target_agent']}", rec, args.json)
    return SUCCESS


def _cmd_reserved(args) -> int:
    print(f"'{args._reserved}' is reserved for a later day (import/selection "
          f"logic). Not implemented in this MVP build.", file=sys.stderr)
    return SUCCESS


def _cmd_install_claude(args) -> int:
    res = install_mod.install_claude_skill(skills_root=args.dest, dry_run=args.dry_run)
    verb = {
        "up_to_date": "already up to date",
        "installed": "installed",
        "updated": "updated",
        "would_install": "would install",
        "would_update": "would update",
    }[res["status"]]
    n = len(res["changed"])
    detail = ""
    if n:
        detail = f" ({n} file(s) {'to write' if args.dry_run else 'written'})"
    _emit(f"DogBuild Claude skill {verb}: {res['dest']}{detail}\n", res, args.json)
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

    rg = rsub.add_parser("gate", help="evaluate the imported decision (full outcomes)")
    rg.add_argument("path", nargs="?", default=".")
    rg.add_argument("--packet", default=None)
    rg.add_argument("--json", action="store_true")
    rg.set_defaults(func=_cmd_review_gate)

    rrv = rsub.add_parser("revise", help="one new-evidence revision after a VETO")
    rrv.add_argument("packet")
    rrv.add_argument("path", nargs="?", default=".")
    rrv.add_argument("--evidence", required=True)
    rrv.add_argument("--json", action="store_true")
    rrv.set_defaults(func=_cmd_review_revise)

    # Orientation Brief (brief == where-am-i)
    for name in ("brief", "where-am-i"):
        b = sub.add_parser(name, help="one-screen orientation: where am I / what's next")
        b.add_argument("path", nargs="?", default=".")
        b.add_argument("--json", action="store_true")
        b.set_defaults(func=_cmd_brief)

    # working-agent declaration (an agent claim, not canonical truth)
    dcl = sub.add_parser("declare", help="record a working-agent declaration")
    dcl.add_argument("path", nargs="?", default=".")
    dcl.add_argument("--building", required=True)
    dcl.add_argument("--changed", required=True)
    dcl.add_argument("--verified", required=True)
    dcl.add_argument("--failed", default="None")
    dcl.add_argument("--incomplete", default="None")
    dcl.add_argument("--next", dest="next_action", required=True)
    dcl.add_argument("--actor", default="claude")
    dcl.add_argument("--alignment", default="IN_SCOPE",
                     choices=["IN_SCOPE", "PARKED_IDEA", "NEEDS_HUMAN_SCOPE_CHANGE"])
    dcl.add_argument("--goal-rev", dest="goal_rev", type=int, default=None)
    dcl.add_argument("--alignment-why", dest="alignment_why", default=None)
    dcl.add_argument("--json", action="store_true")
    dcl.set_defaults(func=_cmd_declare)

    # generic handoff (agent-neutral: claude now, codex later)
    ph = sub.add_parser("handoff", help="agent handoff packets")
    hsub = ph.add_subparsers(dest="handoff_cmd", required=True)

    hc = hsub.add_parser("create", help="create a handoff packet")
    hc.add_argument("path", nargs="?", default=".")
    hc.add_argument("--to", required=True, choices=["claude", "codex"])
    hc.add_argument("--task", required=True)
    hc.add_argument("--acceptance", default=None)
    hc.add_argument("--next", dest="next_action", default=None)
    hc.add_argument("--json", action="store_true")
    hc.set_defaults(func=_cmd_handoff_create)

    hs = hsub.add_parser("show", help="show the latest handoff")
    hs.add_argument("path", nargs="?", default=".")
    hs.add_argument("--json", action="store_true")
    hs.set_defaults(func=_cmd_handoff_show)

    hco = hsub.add_parser("consume", help="validate + consume a handoff (receiving agent)")
    hco.add_argument("path", nargs="?", default=".")
    hco.add_argument("--packet", default=None)
    hco.add_argument("--as", dest="as_agent", default=None)
    hco.add_argument("--json", action="store_true")
    hco.set_defaults(func=_cmd_handoff_consume)

    # genesis: turn an approved discussion into a project contract
    pg = sub.add_parser("genesis", help="project genesis (approved contract) import/show")
    gsub = pg.add_subparsers(dest="genesis_cmd", required=True)
    gi = gsub.add_parser("import", help="import an approved Genesis Packet")
    gi.add_argument("packet_file")
    gi.add_argument("path", nargs="?", default=".")
    gi.add_argument("--approved-at", dest="approved_at", default=None)
    gi.add_argument("--json", action="store_true")
    gi.set_defaults(func=_cmd_genesis_import)
    gs = gsub.add_parser("show", help="show the imported genesis / goal contract")
    gs.add_argument("path", nargs="?", default=".")
    gs.add_argument("--json", action="store_true")
    gs.set_defaults(func=_cmd_genesis_show)

    # goal: the active Goal Contract
    pgl = sub.add_parser("goal", help="active goal contract show/verify")
    glsub = pgl.add_subparsers(dest="goal_cmd", required=True)
    gls = glsub.add_parser("show", help="show the active goal contract")
    gls.add_argument("path", nargs="?", default=".")
    gls.add_argument("--json", action="store_true")
    gls.set_defaults(func=_cmd_goal_show)
    glv = glsub.add_parser("verify", help="verify the active goal contract")
    glv.add_argument("path", nargs="?", default=".")
    glv.add_argument("--json", action="store_true")
    glv.set_defaults(func=_cmd_goal_verify)

    # park: idea parking lot
    pp = sub.add_parser("park", help="idea parking lot")
    psub = pp.add_subparsers(dest="park_cmd", required=True)
    pa = psub.add_parser("add", help="park an out-of-scope idea")
    pa.add_argument("path", nargs="?", default=".")
    pa.add_argument("--title", required=True)
    pa.add_argument("--reason", required=True)
    pa.add_argument("--phase", default="future")
    pa.add_argument("--json", action="store_true")
    pa.set_defaults(func=_cmd_park_add)
    pl = psub.add_parser("list", help="list parked ideas")
    pl.add_argument("path", nargs="?", default=".")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=_cmd_park_list)

    # policy: versioned reviewer policy
    ppol = sub.add_parser("policy", help="reviewer policy show/verify")
    polsub = ppol.add_subparsers(dest="policy_cmd", required=True)
    pols = polsub.add_parser("show", help="show the reviewer policy + fingerprint")
    pols.add_argument("path", nargs="?", default=".")
    pols.add_argument("--json", action="store_true")
    pols.set_defaults(func=_cmd_policy_show)
    polv = polsub.add_parser("verify", help="verify the reviewer policy")
    polv.add_argument("path", nargs="?", default=".")
    polv.add_argument("--json", action="store_true")
    polv.set_defaults(func=_cmd_policy_verify)

    # human: focused human-decision workflow
    phu = sub.add_parser("human", help="focused human-decision workflow")
    husub = phu.add_subparsers(dest="human_cmd", required=True)
    hush = husub.add_parser("show", help="show the current human-decision brief")
    hush.add_argument("path", nargs="?", default=".")
    hush.add_argument("--json", action="store_true")
    hush.set_defaults(func=_cmd_human_show)
    hud = husub.add_parser("decide", help="record a human decision from a file")
    hud.add_argument("decision_file")
    hud.add_argument("path", nargs="?", default=".")
    hud.add_argument("--json", action="store_true")
    hud.set_defaults(func=_cmd_human_decide)

    # resume: safe resume verification
    prs = sub.add_parser("resume", help="safe resume verification")
    rssub = prs.add_subparsers(dest="resume_cmd", required=True)
    rsv = rssub.add_parser("verify", help="verify a recorded human decision is still current")
    rsv.add_argument("path", nargs="?", default=".")
    rsv.add_argument("--decision", default=None)
    rsv.add_argument("--json", action="store_true")
    rsv.set_defaults(func=_cmd_resume_verify)

    # install: put the canonical Claude skill in the user-level skills dir (offline)
    pins = sub.add_parser("install", help="install DogBuild integrations (offline)")
    inssub = pins.add_subparsers(dest="install_cmd", required=True)
    insc = inssub.add_parser("claude", help="install/update the DogBuild Claude skill")
    insc.add_argument("--dest", default=None,
                      help="skills root (default: ~/.claude/skills or $CLAUDE_SKILLS_DIR)")
    insc.add_argument("--dry-run", action="store_true", help="show changes; write nothing")
    insc.add_argument("--json", action="store_true")
    insc.set_defaults(func=_cmd_install_claude)

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
