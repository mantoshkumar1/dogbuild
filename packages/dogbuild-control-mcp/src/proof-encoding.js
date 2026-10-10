// Canonical, injective byte encoding of the returned tree entries
// (dogbuild.raw_commit.entries.v1). Pure; uses only Web-standard globals.

export const ENTRIES_ENCODING = "dogbuild.raw_commit.entries.v1";
export const ENTRY_MODES = Object.freeze(["100644", "100755", "120000", "040000", "160000"]);

const UTF8 = new TextEncoder();
const TAG_BYTES = UTF8.encode(ENTRIES_ENCODING);
const SHA_HEX_RE = /^[0-9a-f]{40}$/;
const MODE_SET = new Set(ENTRY_MODES);

export function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) out[i] = parseInt(hex.slice(2 * i, 2 * i + 2), 16);
  return out;
}

export function bytesToHex(bytes) {
  let out = "";
  for (let i = 0; i < bytes.length; i += 1) out += bytes[i].toString(16).padStart(2, "0");
  return out;
}

export async function sha256Hex(bytes) {
  return bytesToHex(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)));
}

/** entries: array of [mode, sha, path] in the caller's (already sorted) order. */
export function encodeEntries(entries) {
  const encoded = entries.map(([mode, sha, path]) => {
    if (!MODE_SET.has(mode) || !SHA_HEX_RE.test(sha) || typeof path !== "string") {
      throw new Error("entry is outside the closed encoding domain");
    }
    return { mode: UTF8.encode(mode), sha: hexToBytes(sha), path: UTF8.encode(path) };
  });
  let total = TAG_BYTES.length + 4;
  for (const e of encoded) total += 2 + e.mode.length + 4 + e.path.length + 20;
  const out = new Uint8Array(total);
  const view = new DataView(out.buffer);
  out.set(TAG_BYTES, 0);
  let offset = TAG_BYTES.length;
  view.setUint32(offset, encoded.length, false);
  offset += 4;
  for (const e of encoded) {
    view.setUint16(offset, e.mode.length, false);
    offset += 2;
    out.set(e.mode, offset);
    offset += e.mode.length;
    view.setUint32(offset, e.path.length, false);
    offset += 4;
    out.set(e.path, offset);
    offset += e.path.length;
    out.set(e.sha, offset);
    offset += 20;
  }
  return out;
}

/** Strict inverse of encodeEntries. Throws on any deviation. */
export function decodeEntries(bytes) {
  if (!(bytes instanceof Uint8Array)) throw new Error("decode input must be bytes");
  const fail = () => { throw new Error("malformed entries encoding"); };
  if (bytes.length < TAG_BYTES.length + 4) fail();
  for (let i = 0; i < TAG_BYTES.length; i += 1) if (bytes[i] !== TAG_BYTES[i]) fail();
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let offset = TAG_BYTES.length;
  const count = view.getUint32(offset, false);
  offset += 4;
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const entries = [];
  for (let i = 0; i < count; i += 1) {
    if (offset + 2 > bytes.length) fail();
    const modeLen = view.getUint16(offset, false);
    offset += 2;
    if (modeLen !== 6 || offset + modeLen > bytes.length) fail();
    const mode = decoder.decode(bytes.subarray(offset, offset + modeLen));
    offset += modeLen;
    if (!MODE_SET.has(mode)) fail();
    if (offset + 4 > bytes.length) fail();
    const pathLen = view.getUint32(offset, false);
    offset += 4;
    if (offset + pathLen + 20 > bytes.length) fail();
    const path = decoder.decode(bytes.subarray(offset, offset + pathLen));
    offset += pathLen;
    const sha = bytesToHex(bytes.subarray(offset, offset + 20));
    offset += 20;
    entries.push([mode, sha, path]);
  }
  if (offset !== bytes.length) fail();
  return entries;
}
