# DogBuild

[![CI](https://github.com/mantoshkumar1/dogbuild/actions/workflows/ci.yml/badge.svg)](https://github.com/mantoshkumar1/dogbuild/actions/workflows/ci.yml)

An experimental **deterministic control and orchestration layer** for coordinating multiple AI coding agents through GitHub and curated MCP interfaces, without requiring a human to manually relay context between them.

## The Problem

AI agents can implement and review work. Without a durable control plane, the human becomes the message bus:

- Implementation agent completes work → human copies result to reviewer
- Reviewer provides findings → human carries feedback back to implementer
- Every round of fixes requires manual relay

**DogBuild explores how intent, authority, evidence, routing, and handoffs can become deterministic and auditable.**

---

## Intended Architecture

```text
Founder intent
    ↓
Strategy layer (planning, authority, routing)
    ↓
GitHub control/task state (durable, append-only)
    ↓
Deterministic DogBuild reconciliation
    ↓
Authorized Claude/Codex worker (implementation)
    ↓
Append-only GitHub evidence
    ↓
Independent review (ChatGPT)
    ↓
Strategy reconciliation
```

**Key principle:** DogBuild contains no AI and makes no semantic product decisions. It enforces boundaries—founder authority, append-only evidence, exact identity validation—while workers do their work.

---

## Current Status (September 2026)

**DogBuild is under active development and is not yet a production-ready autonomous-agent platform.**

This documentation reflects lived dogfooding, not theoretical design. Every status claim below links to its authoritative GitHub issue or PR.

### Component Status Legend

- `COMPLETE` — shipped, in use, independently reviewed
- `IMPLEMENTED / NOT DEPLOYED` — code merged, not yet live
- `IN REVIEW` — under independent verification
- `PLANNED` — designed, not yet implemented
- `DEFERRED` — identified, safety findings, waiting for re-admission

---

## Completed Work

| Component | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| GitHub-first control-board | `COMPLETE` | [#180](https://github.com/mantoshkumar1/dogbuild/issues/180) | Durable source of truth; append-only evidence |
| Three-server Cloudflare MCP portal | `COMPLETE` | [#169 comment 5721849420](https://github.com/mantoshkumar1/dogbuild/issues/169#issuecomment-5721849420) | Validated end-to-end; portal live |
| MCP tool inventory and Matrix V3 classification (53 tools) | `COMPLETE` | [#169 comment 5721849420](https://github.com/mantoshkumar1/dogbuild/issues/169#issuecomment-5721849420) | Design-clean; live enforcement pending |
| Founder/Strategy/worker authority model | `COMPLETE` | [#180 architecture](https://github.com/mantoshkumar1/dogbuild/issues/180) | GitHub-documented; enforced in practice |
| Append-only communication and evidence rules | `COMPLETE` | [#180 settled architecture](https://github.com/mantoshkumar1/dogbuild/issues/180) | Lived through all corrections |

### In-Development / Under Review

| Component | Status | Evidence | Blocker / Next |
|-----------|--------|----------|-----------------|
| DogBuild Control MCP package (read-only) | `IMPLEMENTED / NOT DEPLOYED` | [PR #173](https://github.com/mantoshkumar1/dogbuild/pull/173) (merged) | Awaiting #175 proof before deployment |
| Exact-SHA CI aggregation (`get_commit_ci`) | `IN REVIEW` | [PR #184](https://github.com/mantoshkumar1/dogbuild/pull/184) (draft), [#175 finding](https://github.com/mantoshkumar1/dogbuild/issues/175#issuecomment-5722270203) | Producer correction required; see #175 |
| Comment-policy tool (`handle_comment_change_request`) | `BLOCKED / FINDING` | [PR #174](https://github.com/mantoshkumar1/dogbuild/pull/174) (open) | Unresolved review status; awaiting bounded correction |
| Schema 4 listener prototype | `DEFERRED / FINDING` | [PingStep PR #630](https://github.com/mantoshkumar1/pingstep/pull/630) (draft) | Safety findings; deferred pending re-admission in #466 |

### Planned

| Component | Target | Relates To |
|-----------|--------|-----------|
| Exact-SHA CI staging-push evidence | Reviewed and correct | [#175](https://github.com/mantoshkumar1/dogbuild/issues/175) |
| Least-privilege identity and repository-scope proof | Foundation for bounded agent execution | [#167](https://github.com/mantoshkumar1/dogbuild/issues/167) |
| Pre-write authorization gateway | Revalidate exact authority before GitHub mutations | [#176](https://github.com/mantoshkumar1/dogbuild/issues/176) |
| Reusable onboarding and session conformance | Blank-session entry points and boundaries | [#170](https://github.com/mantoshkumar1/dogbuild/issues/170) |
| Fourth-server deployable surface | Future custom MCP server (no deployment authority yet) | [#164](https://github.com/mantoshkumar1/dogbuild/issues/164) |
| Real agent invocation | Only after listener safety findings are repaired and re-admitted | [#466](https://github.com/mantoshkumar1/pingstep/issues/466) |

---

## Design Principles

DogBuild operates on these settled principles:

- **GitHub is the durable source of truth.** Chat is a control/wake interface only; evidence and state live on GitHub.
- **DogBuild contains no AI and makes no semantic product decisions.** It enforces boundaries and routes work; humans and specialized agents make product calls.
- **Strategy carries founder intent and assigns work.** The human decides anything irreversible.
- **Workers do not self-start or broaden their authority.** Every task is explicitly bounded and reviewed.
- **Worker plans, findings, and verdicts are append-only on GitHub.** Corrections supersede earlier evidence without silently rewriting history.
- **Exact identity must be revalidated before writes.** Repository, task, role, generation, target, and requested effect are all subject to fresh validation.
- **Missing or conflicting evidence fails closed.** When truth is unclear, the system stops rather than guessing.
- **Implementation and independent review are separate roles.** The same session does not both implement and approve.
- **Infrastructure-critical functionality receives adversarial testing before deployment.** Happy-path passing tests are insufficient; security-negative, fault-injection, and high-volume cases must be proven.
- **Tool availability is capability, not authorization.** A tool being present does not mean a task is approved.

---

## Immediate Roadmap

In order of planned execution:

1. **Correct and independently review PR #184** ([#175](https://github.com/mantoshkumar1/dogbuild/issues/175))
   - Restore all pre-existing test lines
   - Add real same-run rerun-attempt regression test
   - Model production `filter=latest` semantics
   - Complete adversarial/high-volume/coverage evidence
   - Producer self-review before new independent review

2. **Reconcile or exclude PR #174** ([#174](https://github.com/mantoshkumar1/dogbuild/pull/174))
   - Bounded producer correction if issue remains open
   - Clear resolution on scope vs. future work

3. **Complete least-privilege identity and repository-scope proof** ([#167](https://github.com/mantoshkumar1/dogbuild/issues/167))
   - Restricted identity separate from founder credentials
   - Repository allowlist mechanically enforced

4. **Implement deterministic pre-write gateway** ([#176](https://github.com/mantoshkumar1/dogbuild/issues/176))
   - Revalidate exact authority before every mutation
   - Fail closed on identity/scope mismatch

5. **Complete onboarding and fresh-session conformance** ([#170](https://github.com/mantoshkumar1/dogbuild/issues/170))
   - Reusable entry points for blank sessions
   - Explicit session boundary acknowledgement

6. **Decide and review fourth-server deployable surface** ([#164](https://github.com/mantoshkumar1/dogbuild/issues/164))
   - Define exact scope for any additional custom MCP server
   - Independent review of design and scope

7. **Deploy only with explicit authorization and rollback evidence**
   - Founder-only gate for any live registration
   - Rollback and kill-switch proven before go-live

8. **Repair and re-admit listener before real agent invocation** ([#630](https://github.com/mantoshkumar1/pingstep/pull/630))
   - Address webhook authenticity, state safety, schema validation findings
   - Re-review exact head when re-admitted

9. **Prove complete workflow through real-system boundaries**
   - End-to-end canary: task → plan → branch → implementation → review → merge
   - No human relay, verified evidence, founder approval gates intact

---

## What This Is NOT (Yet)

- **Not a production-ready autonomous-agent platform.** It is under active development and explicitly defers deployment of several components.
- **Not a claim of exactly-once distributed execution.** That bar is not met by current test evidence; see #175.
- **Not an unrestricted GitHub administration layer.** Repository protections and authorization gates remain enforced.
- **Not a replacement for repository protections, CI, or human judgment.** Those remain authoritative.
- **Not a deployed fourth MCP server.** Custom control server exists but is not yet deployed.
- **Not a finished commercial product.** Payment, demand, pricing, and distribution are explicitly unvalidated.

---

## Milestones Achieved

These incremental steps show progress toward the eventual vision:

- Defined founder/Strategy/worker authority model ([#180](https://github.com/mantoshkumar1/dogbuild/issues/180))
- Made GitHub the durable communication and evidence layer ([#180](https://github.com/mantoshkumar1/dogbuild/issues/180))
- Built and validated three-server MCP portal path ([#169](https://github.com/mantoshkumar1/dogbuild/issues/169))
- Inventoried and classified live 53-tool MCP surface ([#169 comment 5721849420](https://github.com/mantoshkumar1/dogbuild/issues/169#issuecomment-5721849420))
- Implemented narrow read-only DogBuild control-server package ([PR #173](https://github.com/mantoshkumar1/dogbuild/pull/173))
- Implemented exact-SHA CI aggregate candidate ([PR #184](https://github.com/mantoshkumar1/dogbuild/pull/184))
- Proved visibility of real staging-push workflow evidence (through existing Actions API)
- Built deterministic listener prototype and identified its safety gaps ([PingStep PR #630](https://github.com/mantoshkumar1/pingstep/pull/630))
- Defined future pre-write authorization gateway ([#176](https://github.com/mantoshkumar1/dogbuild/issues/176))
- Began adversarial verification and admission work (ongoing)

---

## Quick Links

| Purpose | Link |
|---------|------|
| Control board (live strategy and routing) | [#180](https://github.com/mantoshkumar1/dogbuild/issues/180) |
| Documentation source-of-truth task | [#183](https://github.com/mantoshkumar1/dogbuild/issues/183) |
| MCP tool curation | [#169](https://github.com/mantoshkumar1/dogbuild/issues/169) |
| Exact-SHA CI proof | [#175](https://github.com/mantoshkumar1/dogbuild/issues/175) |
| Least-privilege identity | [#167](https://github.com/mantoshkumar1/dogbuild/issues/167) |
| Listener refinement (deferred) | [PingStep #630](https://github.com/mantoshkumar1/pingstep/pull/630) |
| Vision and motivating example | [vision.md](https://github.com/mantoshkumar1/dogbuild/blob/main/vision.md) |
| Related article on the problem | [Why Am I Still the Message Bus Between My AI Agents?](https://mantoshkumar1.github.io/insights/message-bus-between-ai-agents.html) |

---

## About the Builder

**Mantosh Kumar** is a Staff Software Engineer based in Toronto, specializing in platform engineering, automation, and distributed systems validation.

- **GitHub:** [mantoshkumar1](https://github.com/mantoshkumar1)
- **Website:** [mantoshkumar1.github.io](https://mantoshkumar1.github.io)
- **Article on this problem:** [Why Am I Still the Message Bus Between My AI Agents?](https://mantoshkumar1.github.io/insights/message-bus-between-ai-agents.html)

DogBuild is built and actively dogfooded in public. It represents one engineer's approach to a real coordination problem; it is not affiliated with any employer and does not represent an organizational position.

---

## Further Reading

- [**vision.md**](https://github.com/mantoshkumar1/dogbuild/blob/main/vision.md) — Full product vision: coordination/control layer, roles, control loop, first prototype vs. eventual product, milestone roadmap.
- [**AGENTS.md**](https://github.com/mantoshkumar1/dogbuild/blob/main/AGENTS.md) — Role boundaries, responsibilities, and expectations for human, Strategy, and worker agents.
- [**Control Board #180**](https://github.com/mantoshkumar1/dogbuild/issues/180) — Live routing, current lanes, admission gates, and immediate next steps.
