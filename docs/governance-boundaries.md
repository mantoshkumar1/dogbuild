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
