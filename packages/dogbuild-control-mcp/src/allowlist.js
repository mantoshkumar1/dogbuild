import { ControlError, ErrorClass } from "./errors.js";

const REPO_PART_RE = /^[A-Za-z0-9._-]+$/;

function assertRepoPart(value, name) {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    value.length > 100 ||
    !REPO_PART_RE.test(value) ||
    value === "." ||
    value === ".."
  ) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${name} is not a valid GitHub repository component.`);
  }
  return value;
}

export function parseAllowlist(env) {
  const raw = env && typeof env.ALLOWED_REPOS === "string" ? env.ALLOWED_REPOS.trim() : "";
  if (!raw) {
    throw new ControlError(
      ErrorClass.CONFIG_INVALID,
      "ALLOWED_REPOS is not configured; every repository is denied."
    );
  }

  const entries = raw.split(",").map((entry) => entry.trim());
  const normalized = [];
  for (const entry of entries) {
    if (!entry) {
      throw new ControlError(
        ErrorClass.CONFIG_INVALID,
        "ALLOWED_REPOS is malformed; every repository is denied."
      );
    }
    const parts = entry.split("/");
    if (parts.length !== 2) {
      throw new ControlError(
        ErrorClass.CONFIG_INVALID,
        "ALLOWED_REPOS is malformed; every repository is denied."
      );
    }
    try {
      assertRepoPart(parts[0], "owner");
      assertRepoPart(parts[1], "repo");
    } catch {
      throw new ControlError(
        ErrorClass.CONFIG_INVALID,
        "ALLOWED_REPOS is malformed; every repository is denied."
      );
    }
    normalized.push(entry.toLowerCase());
  }

  if (!normalized.length) {
    throw new ControlError(
      ErrorClass.CONFIG_INVALID,
      "ALLOWED_REPOS is malformed; every repository is denied."
    );
  }
  return [...new Set(normalized)];
}

export function assertRepoAllowed(env, owner, repo) {
  const validOwner = assertRepoPart(owner, "owner");
  const validRepo = assertRepoPart(repo, "repo");
  const requested = `${validOwner}/${validRepo}`.toLowerCase();
  if (!parseAllowlist(env).includes(requested)) {
    throw new ControlError(ErrorClass.ALLOWLIST_DENIED, "Repository is not on the configured allowlist.", {
      repository: `${validOwner}/${validRepo}`,
    });
  }
  return { owner: validOwner, repo: validRepo, fullName: `${validOwner}/${validRepo}` };
}
