// Pure output accounting for get_raw_commit: Worker-portable byte counts,
// the degraded-result builder and predicate, request-id rules and the
// four-tier response writer. No I/O.

const UTF8 = new TextEncoder();
export const utf8Length = (text) => UTF8.encode(text).length;
export const jsonUtf8Length = (value) => utf8Length(JSON.stringify(value));

export const MAX_MCP_RESPONSE_BYTES = 524_288;
export const DEGRADED_MAX_BYTES = 8192;
export const RAW_SCHEMA = "dogbuild.raw_commit.v1";
export const ENTRIES_ENCODING_NAME = "dogbuild.raw_commit.entries.v1";

export const LIMITS = Object.freeze({
  max_gets: 3,
  max_response_bytes: 2_097_152,
  max_root_entries: 1000,
  max_recursive_entries: 20_000,
  deadline_ms: 45_000,
  max_mcp_response_bytes: MAX_MCP_RESPONSE_BYTES,
});

const SHA_RE = /^[0-9a-f]{40}$/;
const HEX64_RE = /^[0-9a-f]{64}$/;
const TOP_KEYS = [
  "schema", "status", "complete", "incomplete_reason", "requested_sha", "sha", "tree_sha",
  "parents", "parent_count", "parents_duplicate_present", "commit_object_rehash", "tree_proof", "limits",
];
const PROOF_KEYS = [
  "entries_encoding", "root_entry_count", "recursive_entry_count", "tree_count", "blob_count",
  "submodule_count", "subtree_hashes_verified", "entries", "entries_encoded_bytes", "entries_sha256",
];
const COUNT_KEYS = [
  "root_entry_count", "recursive_entry_count", "tree_count", "blob_count", "submodule_count",
  "subtree_hashes_verified",
];

const isPlainObject = (o) =>
  o !== null && typeof o === "object" && !Array.isArray(o) && Object.getPrototypeOf(o) === Object.prototype;

function sameKeys(o, keys) {
  const own = Reflect.ownKeys(o);
  return own.length === keys.length && keys.every((k) => Object.prototype.hasOwnProperty.call(o, k)) &&
    own.every((k) => typeof k === "string");
}

const isCount = (n) => Number.isSafeInteger(n) && n >= 0 && n <= LIMITS.max_recursive_entries;

/** Build the degraded INCOMPLETE/OUTPUT_CEILING_EXCEEDED form from a verified COMPLETE primary. */
export function buildDegraded(primary) {
  if (!primary || primary.status !== "COMPLETE" || primary.complete !== true || !primary.tree_proof) return null;
  return {
    schema: primary.schema,
    status: "INCOMPLETE",
    complete: false,
    incomplete_reason: "OUTPUT_CEILING_EXCEEDED",
    requested_sha: primary.requested_sha,
    sha: primary.sha,
    tree_sha: primary.tree_sha,
    parents: primary.parents,
    parent_count: primary.parent_count,
    parents_duplicate_present: primary.parents_duplicate_present,
    commit_object_rehash: primary.commit_object_rehash,
    tree_proof: { ...primary.tree_proof, entries: null },
    limits: primary.limits,
  };
}

export function isValidDegraded(d) {
  if (!isPlainObject(d) || !sameKeys(d, TOP_KEYS)) return false;
  if (d.schema !== RAW_SCHEMA || d.status !== "INCOMPLETE" || d.complete !== false) return false;
  if (d.incomplete_reason !== "OUTPUT_CEILING_EXCEEDED" || d.commit_object_rehash !== "NOT_PERFORMED") return false;
  for (const key of ["requested_sha", "sha", "tree_sha"]) {
    if (typeof d[key] !== "string" || !SHA_RE.test(d[key])) return false;
  }
  if (d.requested_sha !== d.sha) return false;
  if (!Array.isArray(d.parents) || d.parents.some((p) => typeof p !== "string" || !SHA_RE.test(p))) return false;
  if (d.parent_count !== d.parents.length) return false;
  if (typeof d.parents_duplicate_present !== "boolean" ||
      d.parents_duplicate_present !== (new Set(d.parents).size !== d.parents.length)) return false;
  const p = d.tree_proof;
  if (!isPlainObject(p) || !sameKeys(p, PROOF_KEYS)) return false;
  if (p.entries !== null || p.entries_encoding !== ENTRIES_ENCODING_NAME) return false;
  if (!COUNT_KEYS.every((k) => isCount(p[k]))) return false;
  if (p.root_entry_count > LIMITS.max_root_entries || p.root_entry_count > p.recursive_entry_count) return false;
  if (p.tree_count + p.blob_count + p.submodule_count !== p.recursive_entry_count) return false;
  if (p.subtree_hashes_verified > p.tree_count) return false;
  const n = p.recursive_entry_count;
  if (!Number.isSafeInteger(p.entries_encoded_bytes) ||
      p.entries_encoded_bytes < 34 + 33 * n ||
      p.entries_encoded_bytes > 34 + 32 * n + LIMITS.max_response_bytes) return false;
  if (typeof p.entries_sha256 !== "string" || !HEX64_RE.test(p.entries_sha256)) return false;
  const l = d.limits;
  if (!isPlainObject(l) || !sameKeys(l, Object.keys(LIMITS))) return false;
  if (!Object.keys(LIMITS).every((k) => l[k] === LIMITS[k])) return false;
  return jsonUtf8Length(d) <= DEGRADED_MAX_BYTES;
}

/** Allowed JSON-RPC ids for get_raw_commit: string, null, or a safe integer (not -0). */
export function isAllowedRequestId(id) {
  if (id === null || typeof id === "string") return true;
  return typeof id === "number" && Number.isSafeInteger(id) && !Object.is(id, -0);
}

function assertAllowedId(id) {
  if (!isAllowedRequestId(id)) throw new TypeError("request id is not allowed");
}

export function serializeResult(id, value) {
  return JSON.stringify({
    jsonrpc: "2.0",
    id,
    result: { content: [{ type: "text", text: JSON.stringify(value) }] },
  });
}

export function serializeOutputCeilingError(id) {
  return JSON.stringify({
    jsonrpc: "2.0",
    id,
    error: {
      code: -32000,
      message: "MCP response exceeded the output ceiling.",
      data: { error_class: "UPSTREAM_ERROR", reason: "OUTPUT_CEILING_EXCEEDED" },
    },
  });
}

export const TIER4_BODY = "Output ceiling exceeded";

/**
 * Tier 1: primary. Tier 2: valid degraded form (only if one exists and fits).
 * Tier 3: fixed same-ID error. Tier 4: plain-text 500 (defense in depth).
 */
export function writeToolResponse(id, envelope, ceilingBytes = MAX_MCP_RESPONSE_BYTES) {
  assertAllowedId(id);
  const t1 = serializeResult(id, envelope.primary);
  if (utf8Length(t1) <= ceilingBytes) return { tier: 1, status: 200, contentType: "application/json", body: t1 };
  if (isValidDegraded(envelope.degraded)) {
    const t2 = serializeResult(id, envelope.degraded);
    if (utf8Length(t2) <= ceilingBytes) return { tier: 2, status: 200, contentType: "application/json", body: t2 };
  }
  const t3 = serializeOutputCeilingError(id);
  if (utf8Length(t3) <= ceilingBytes) return { tier: 3, status: 200, contentType: "application/json", body: t3 };
  return { tier: 4, status: 500, contentType: "text/plain", body: TIER4_BODY };
}

/** JSON-RPC error for a thrown controlled error, with the exact validated id. */
export function writeErrorResponse(id, controlled, ceilingBytes = MAX_MCP_RESPONSE_BYTES) {
  assertAllowedId(id);
  const body = JSON.stringify({
    jsonrpc: "2.0",
    id,
    error: { code: -32000, message: controlled.message, data: controlled.toJSON() },
  });
  if (utf8Length(body) <= ceilingBytes) return { tier: 0, status: 200, contentType: "application/json", body };
  const t3 = serializeOutputCeilingError(id);
  if (utf8Length(t3) <= ceilingBytes) return { tier: 3, status: 200, contentType: "application/json", body: t3 };
  return { tier: 4, status: 500, contentType: "text/plain", body: TIER4_BODY };
}
