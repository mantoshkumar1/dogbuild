// get_raw_commit: exact commit parents plus a Merkle-verified recursive tree
// proof, read through three allowlisted GET requests.
import { assertRepoAllowed } from "./allowlist.js";
import { ControlError, ErrorClass } from "./errors.js";
import { SHA_RE, assertWithinDeadline, boundedGet, newBoundedSession } from "./github.js";
import {
  ENTRIES_ENCODING,
  decodeEntries,
  encodeEntries,
  sha256Hex,
} from "./proof-encoding.js";
import { LIMITS, RAW_SCHEMA, buildDegraded } from "./output.js";
import {
  entriesFromTuples,
  normalizeEntry,
  sortedTuples,
  verifyRecursiveListing,
} from "./tree-proof.js";

const ARG_KEYS = ["owner", "repo", "sha"];

export function parseRawCommitArgs(args) {
  const invalid = () => new ControlError(ErrorClass.INVALID_INPUT, "Invalid get_raw_commit arguments.", {
    reason: "INVALID_ARGUMENTS",
  });
  if (args === null || typeof args !== "object" || Array.isArray(args) ||
      Object.getPrototypeOf(args) !== Object.prototype) {
    throw invalid();
  }
  const own = Object.keys(args);
  let ok = own.length === ARG_KEYS.length;
  for (const key of ARG_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(args, key)) ok = false;
  }
  if (!ok) throw invalid();
  return { owner: args.owner, repo: args.repo, sha: args.sha };
}

function malformed(reason, message = "GitHub returned an unexpected response shape.") {
  return new ControlError(ErrorClass.UPSTREAM_MALFORMED, message, { reason });
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function incompleteResult(reason, requestedSha, known = {}) {
  return {
    schema: RAW_SCHEMA,
    status: "INCOMPLETE",
    complete: false,
    incomplete_reason: reason,
    requested_sha: requestedSha,
    sha: known.sha ?? null,
    tree_sha: known.tree_sha ?? null,
    parents: known.parents ?? null,
    parent_count: known.parents ? known.parents.length : null,
    parents_duplicate_present: known.parents ? new Set(known.parents).size !== known.parents.length : null,
    commit_object_rehash: "NOT_PERFORMED",
    tree_proof: null,
    limits: { ...LIMITS },
  };
}

function parseCommit(body, requestedSha) {
  if (!isObject(body)) throw malformed("COMMIT_SHAPE");
  if (body.sha !== requestedSha) {
    throw new ControlError(ErrorClass.HEAD_MISMATCH, "GitHub returned a different commit than requested.", {
      reason: "COMMIT_SHA_MISMATCH",
    });
  }
  if (!isObject(body.tree) || typeof body.tree.sha !== "string" || !SHA_RE.test(body.tree.sha)) {
    throw malformed("COMMIT_TREE_SHAPE");
  }
  if (!Array.isArray(body.parents)) throw malformed("PARENTS_MISSING");
  const parents = [];
  for (const parent of body.parents) {
    if (!isObject(parent) || typeof parent.sha !== "string" || !SHA_RE.test(parent.sha)) {
      throw malformed("PARENT_SHAPE");
    }
    parents.push(parent.sha);
  }
  return { sha: body.sha, tree_sha: body.tree.sha, parents };
}

function parseTreeResponse(body, treeSha) {
  if (!isObject(body)) throw malformed("TREE_SHAPE");
  if (body.sha !== treeSha) {
    throw new ControlError(ErrorClass.HEAD_MISMATCH, "GitHub returned a different tree than requested.", {
      reason: "ROOT_TREE_SHA_MISMATCH",
    });
  }
  if (typeof body.truncated !== "boolean") throw malformed("TRUNCATED_FLAG_MISSING");
  if (!Array.isArray(body.tree)) throw malformed("TREE_SHAPE");
  return { rawEntries: body.tree, truncated: body.truncated };
}

function sameSet(rootEntries, recursiveTopLevel) {
  if (rootEntries.length !== recursiveTopLevel.length) return false;
  const key = (e) => JSON.stringify([e.path, e.mode, e.type, e.sha]);
  const left = new Set(rootEntries.map(key));
  if (left.size !== rootEntries.length) return false;
  return recursiveTopLevel.every((e) => left.has(key(e)));
}

export async function getRawCommit(env, args) {
  const params = parseRawCommitArgs(args);

  let allowed;
  try {
    allowed = assertRepoAllowed(env, params.owner, params.repo);
  } catch (error) {
    if (error instanceof ControlError && error.class === ErrorClass.ALLOWLIST_DENIED) {
      throw new ControlError(ErrorClass.ALLOWLIST_DENIED, "Repository is not on the configured allowlist.", {
        reason: "REPOSITORY_NOT_ALLOWED",
      });
    }
    throw error;
  }
  if (typeof params.sha !== "string" || !SHA_RE.test(params.sha)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "sha must be exactly 40 lowercase hexadecimal characters.", {
      reason: "INVALID_SHA",
    });
  }
  const sha = params.sha;
  const session = newBoundedSession();
  const base = `/repos/${encodeURIComponent(allowed.owner)}/${encodeURIComponent(allowed.repo)}/git`;
  const done = (primary) => ({ primary, degraded: buildDegraded(primary) });

  // 1. Raw commit object.
  const commitResult = await boundedGet(env, `${base}/commits/${sha}`, session);
  assertWithinDeadline(session);
  if (commitResult.incomplete) return done(incompleteResult(commitResult.incomplete, sha));
  const commit = parseCommit(commitResult.json, sha);
  const known = { sha: commit.sha, tree_sha: commit.tree_sha, parents: commit.parents };

  // 2. Root tree (non-recursive).
  const rootResult = await boundedGet(env, `${base}/trees/${commit.tree_sha}`, session);
  assertWithinDeadline(session);
  if (rootResult.incomplete) return done(incompleteResult(rootResult.incomplete, sha, known));
  const root = parseTreeResponse(rootResult.json, commit.tree_sha);
  if (root.rawEntries.length > LIMITS.max_root_entries) {
    return done(incompleteResult("ROOT_ENTRY_CAP_EXCEEDED", sha, known));
  }
  if (root.truncated) return done(incompleteResult("GITHUB_TRUNCATED", sha, known));
  const rootEntries = root.rawEntries.map(normalizeEntry);
  if (rootEntries.some((e) => e.path.includes("/"))) throw malformed("INVALID_PATH");

  // 3. Recursive tree.
  const recResult = await boundedGet(env, `${base}/trees/${commit.tree_sha}?recursive=1`, session);
  assertWithinDeadline(session);
  if (recResult.incomplete) return done(incompleteResult(recResult.incomplete, sha, known));
  const rec = parseTreeResponse(recResult.json, commit.tree_sha);
  if (rec.rawEntries.length > LIMITS.max_recursive_entries) {
    return done(incompleteResult("RECURSIVE_ENTRY_CAP_EXCEEDED", sha, known));
  }
  if (rec.truncated) return done(incompleteResult("GITHUB_TRUNCATED", sha, known));
  const recEntries = rec.rawEntries.map(normalizeEntry);

  const counts = await verifyRecursiveListing(recEntries, commit.tree_sha, () => assertWithinDeadline(session));
  if (!sameSet(rootEntries, recEntries.filter((e) => !e.path.includes("/")))) {
    throw malformed("ROOT_RECURSIVE_DISAGREEMENT");
  }

  const tuples = sortedTuples(recEntries);
  const bytes = encodeEntries(tuples);
  const digest = await sha256Hex(bytes);
  assertWithinDeadline(session);

  const primary = {
    schema: RAW_SCHEMA,
    status: "COMPLETE",
    complete: true,
    requested_sha: sha,
    sha: commit.sha,
    tree_sha: commit.tree_sha,
    parents: commit.parents,
    parent_count: commit.parents.length,
    parents_duplicate_present: new Set(commit.parents).size !== commit.parents.length,
    commit_object_rehash: "NOT_PERFORMED",
    tree_proof: {
      entries_encoding: ENTRIES_ENCODING,
      ...counts,
      entries: tuples,
      entries_encoded_bytes: bytes.length,
      entries_sha256: digest,
    },
    limits: { ...LIMITS },
  };

  await proofSelfCheck(primary, bytes, commit.tree_sha, session);
  return done(primary);
}

async function proofSelfCheck(primary, bytes, treeSha, session) {
  const fail = () => new ControlError(ErrorClass.UPSTREAM_ERROR, "Internal error.", {
    reason: "PROOF_SELF_CHECK_FAILED",
  });
  try {
    const decoded = decodeEntries(bytes);
    if (JSON.stringify(decoded) !== JSON.stringify(primary.tree_proof.entries)) throw fail();
    const again = encodeEntries(decoded);
    if (again.length !== bytes.length || again.some((b, i) => b !== bytes[i])) throw fail();
    const reparsed = JSON.parse(JSON.stringify(primary)).tree_proof.entries;
    const third = encodeEntries(reparsed);
    if (third.length !== bytes.length || third.some((b, i) => b !== bytes[i])) throw fail();
    if ((await sha256Hex(third)) !== primary.tree_proof.entries_sha256) throw fail();
    await verifyRecursiveListing(entriesFromTuples(decoded), treeSha, () => assertWithinDeadline(session));
  } catch (error) {
    if (error instanceof ControlError && error.details && error.details.reason === "PROOF_SELF_CHECK_FAILED") throw error;
    if (error instanceof ControlError && error.class === ErrorClass.TIMEOUT) throw error;
    throw fail();
  }
}
