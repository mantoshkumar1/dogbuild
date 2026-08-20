# Governance and execution boundaries

DogBuild uses three separate records with deliberately different authority.
They are not a bidirectionally synchronized database.

| Record | Owns | Does not own |
|---|---|---|
| Revenue Opportunity Lab | Product activation, commercial constraints, continue/park/kill decisions | DogBuild code, repository evidence, task completion |
| DogBuild repository and `.ai/` state | Product implementation, technical decisions, verified repository state, handoffs and authority gates | Portfolio prioritization or market validation claims |
| GitHub Project | Current work queue, priority, blockers and review status | Proof that implementation is complete |

## Flow of authority

1. The Lab may activate, constrain, park, or stop DogBuild.
2. Accepted constraints enter DogBuild as a reviewed, versioned snapshot.
3. DogBuild operates from its own repository state; it does not require the Lab
   checkout at runtime.
4. GitHub issues describe proposed and remaining work.
5. Repository commits and tests provide completion evidence; the project board
   reflects that result after verification.

## Pull-request presentation

DogBuild uses an issue-only GitHub Project ledger: the authoritative issue owns execution status, priority,
blockers, and review state. A PR must not become a duplicate Project item merely to make that information
visible. Instead, every PR body names the authoritative issue and current status, states that the issue is the
Project record, describes the PR's role, and says whether it is a partial slice or a full completion. CI checks
this structural contract from GitHub's local event payload whenever a pull request is opened or updated.

## Initialization rule

Every repository initialized by DogBuild is independent by default. Upstream
source metadata is recorded only when the operator explicitly provides both the
source context and record:

```bash
dogbuild init . \
  --objective "..." \
  --source-name "Opportunity Lab" \
  --source-record "https://example.test/product-record"
```

DogBuild must never inject Mantosh Kumar's private Revenue Opportunity Lab path
into repositories belonging to another project or user.

## Synchronization policy

There is no automatic two-way synchronization. That is intentional:

- Lab changes do not silently rewrite DogBuild scope.
- GitHub status changes do not override repository evidence.
- DogBuild does not claim commercial validation from implementation progress.

If repeated manual policy import becomes costly, a future read-only import
command may verify a source revision and create a reviewable snapshot. Automatic
write-back remains out of scope until a concrete need is demonstrated.
