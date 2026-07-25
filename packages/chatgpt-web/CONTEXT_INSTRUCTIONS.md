# ChatGPT Web — context instructions (manual MVP)

Paste/attach this alongside a Project State Keeper packet. **ChatGPT Web cannot
inspect** the local working directory, open browser windows, the local project
registry, or Claude/Cursor state. It knows only what the uploaded packet contains.

The standard request stays: **"Review the attached Project State Keeper packet."**
The user should not have to restate the repository manually.

## ChatGPT must:
1. **Read the project identity from the attached packet** (project_id,
   repository_id, project_name, repository_name, branch, head, scope).
2. **Repeat the project name and project ID in every structured decision.**
3. **Refuse to combine evidence from different projects.**
4. Flag conflicting identities as **`MISMATCH`**.
5. Flag missing identity as **`UNKNOWN`**.
6. **Ask one focused question** when multiple projects are plausible (list only the
   plausible ones).
7. **Never assume a chat's title proves repository identity.**
8. **Never treat an older chat summary as newer** than the uploaded repository
   packet — the packet is the source of truth.

## Decision format ChatGPT must return
```yaml
project_id: <uuid>            # copied from the packet, unchanged
repository_id: <uuid>         # copied from the packet, unchanged
project_name: <name>
branch: <branch>
head: <full-sha>
scope_revision: <int>
verdict: APPROVE | APPROVE_WITH_CONDITIONS | VETO | NEEDS_HUMAN
conditions: []
rationale: <short>
```
If the identity is missing or conflicting, return `UNKNOWN` / `MISMATCH` instead of
a verdict, and do not review. Local import will reject any decision whose
identifiers do not match the current repository state.
