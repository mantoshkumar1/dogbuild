// Pure Git tree validation and bottom-up Merkle reconciliation. No I/O.
import { ControlError, ErrorClass } from "./errors.js";
import { hexToBytes } from "./proof-encoding.js";

export const EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
const SHA_RE = /^[0-9a-f]{40}$/;
const UTF8 = new TextEncoder();

const MODE_TYPE = Object.freeze({
  "100644": "blob",
  "100755": "blob",
  "120000": "blob",
  "040000": "tree",
  "160000": "commit",
});

function malformed(reason, details = {}) {
  return new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub tree data failed verification.", {
    reason,
    ...details,
  });
}

/** True when the string has no lone UTF-16 surrogate (portable isWellFormed). */
export function isWellFormedString(text) {
  for (let i = 0; i < text.length; i += 1) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = text.charCodeAt(i + 1);
      if (!(d >= 0xdc00 && d <= 0xdfff)) return false;
      i += 1;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      return false;
    }
  }
  return true;
}

export function isValidPath(path) {
  if (typeof path !== "string" || path.length === 0) return false;
  if (path.includes("\u0000")) return false;
  if (path.startsWith("/") || path.endsWith("/") || path.includes("//")) return false;
  for (const segment of path.split("/")) {
    if (segment === "." || segment === "..") return false;
  }
  return isWellFormedString(path);
}

/** Unsigned bytewise comparison; a proper prefix sorts first. */
export function compareBytes(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return a.length - b.length;
}

/** Validate one API entry and return a normalized copy. */
export function normalizeEntry(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw malformed("ENTRY_SHAPE");
  const { path, mode, type, sha } = raw;
  if (typeof path !== "string" || typeof mode !== "string" || typeof type !== "string" || typeof sha !== "string") {
    throw malformed("ENTRY_SHAPE");
  }
  if (!SHA_RE.test(sha)) throw malformed("ENTRY_SHAPE");
  if (!Object.prototype.hasOwnProperty.call(MODE_TYPE, mode) || MODE_TYPE[mode] !== type) {
    throw malformed("UNSUPPORTED_MODE_OR_TYPE");
  }
  if (!isValidPath(path)) throw malformed("INVALID_PATH");
  return { path, mode, type, sha };
}

function parentDir(path) {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}

function concat(chunks) {
  let total = 0;
  for (const c of chunks) total += c.length;
  const out = new Uint8Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/** SHA-1 of the Git tree object for `children` ({name, mode, type, sha}). */
export async function gitTreeSha1(children) {
  const keyed = children.map((child) => {
    const name = UTF8.encode(child.name);
    const key = child.type === "tree" ? concat([name, new Uint8Array([0x2f])]) : name;
    return { child, name, key };
  });
  keyed.sort((x, y) => compareBytes(x.key, y.key));
  const parts = [];
  for (const { child, name } of keyed) {
    const gitMode = child.type === "tree" ? "40000" : child.mode;
    parts.push(UTF8.encode(`${gitMode} `), name, new Uint8Array([0]), hexToBytes(child.sha));
  }
  const body = concat(parts);
  const object = concat([UTF8.encode(`tree ${body.length}\u0000`), body]);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-1", object));
  let hex = "";
  for (let i = 0; i < digest.length; i += 1) hex += digest[i].toString(16).padStart(2, "0");
  return hex;
}

/**
 * Verify a complete recursive listing against `rootSha`.
 * `entries` are normalized ({path, mode, type, sha}). `tick` is called between
 * trees so the caller can enforce its deadline. Returns structural counts.
 */
export async function verifyRecursiveListing(entries, rootSha, tick = () => {}) {
  const byPath = new Map();
  for (const entry of entries) {
    if (byPath.has(entry.path)) throw malformed("DUPLICATE_PATH");
    byPath.set(entry.path, entry);
  }
  const children = new Map([["", []]]);
  for (const entry of entries) {
    const dir = parentDir(entry.path);
    if (dir !== "") {
      const parent = byPath.get(dir);
      if (!parent || parent.type !== "tree") throw malformed("ORPHAN_PATH");
    }
    const name = dir === "" ? entry.path : entry.path.slice(dir.length + 1);
    if (!children.has(dir)) children.set(dir, []);
    children.get(dir).push({ name, mode: entry.mode, type: entry.type, sha: entry.sha });
    if (entry.type === "tree" && !children.has(entry.path)) children.set(entry.path, []);
  }

  const dirs = [...children.keys()].filter((d) => d !== "");
  const dirBytes = new Map(dirs.map((d) => [d, UTF8.encode(d)]));
  dirs.sort((a, b) => compareBytes(dirBytes.get(a), dirBytes.get(b)));
  const order = ["", ...dirs];

  let verified = 0;
  for (let index = 0; index < order.length; index += 1) {
    tick();
    const dir = order[index];
    const computed = await gitTreeSha1(children.get(dir));
    const declared = dir === "" ? rootSha : byPath.get(dir).sha;
    if (computed !== declared) throw malformed("TREE_HASH_MISMATCH", { tree_index: index });
    if (dir !== "") verified += 1;
  }

  let treeCount = 0;
  let blobCount = 0;
  let submoduleCount = 0;
  let rootCount = 0;
  for (const entry of entries) {
    if (entry.type === "tree") treeCount += 1;
    else if (entry.type === "blob") blobCount += 1;
    else submoduleCount += 1;
    if (!entry.path.includes("/")) rootCount += 1;
  }
  return {
    root_entry_count: rootCount,
    recursive_entry_count: entries.length,
    tree_count: treeCount,
    blob_count: blobCount,
    submodule_count: submoduleCount,
    subtree_hashes_verified: verified,
  };
}

/** Sort normalized entries by UTF-8 path bytes and return [mode, sha, path] tuples. */
export function sortedTuples(entries) {
  const keyed = entries.map((e) => ({ e, key: UTF8.encode(e.path) }));
  keyed.sort((x, y) => compareBytes(x.key, y.key));
  return keyed.map(({ e }) => [e.mode, e.sha, e.path]);
}

export function entriesFromTuples(tuples) {
  return tuples.map(([mode, sha, path]) => ({ path, mode, type: MODE_TYPE[mode], sha }));
}
