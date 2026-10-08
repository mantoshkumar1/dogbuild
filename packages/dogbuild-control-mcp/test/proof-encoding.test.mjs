import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ENTRIES_ENCODING, decodeEntries, encodeEntries, sha256Hex } from "../src/proof-encoding.js";
import { getRawCommit } from "../src/raw-commit.js";
import { sortedTuples } from "../src/tree-proof.js";
import {
  ENV, OWNER, REPO, SHA, flowRoutes, gitAvailable, hex40, independentVerify, installRoutes, makeTree,
} from "./raw-support.mjs";

// Separately written encoder (does not import the production encoder).
function referenceEncode(tuples) {
  const parts = [Buffer.from("dogbuild.raw_commit.entries.v1")];
  const count = Buffer.alloc(4);
  count.writeUInt32BE(tuples.length);
  parts.push(count);
  for (const [mode, sha, path] of tuples) {
    const m = Buffer.from(mode, "ascii");
    const p = Buffer.from(path, "utf8");
    const lm = Buffer.alloc(2); lm.writeUInt16BE(m.length);
    const lp = Buffer.alloc(4); lp.writeUInt32BE(p.length);
    parts.push(lm, m, lp, p, Buffer.from(sha, "hex"));
  }
  return Buffer.concat(parts);
}

const b40 = "b".repeat(40);
const equalBytes = (a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0;

test("the tag is exactly 30 ASCII bytes and the empty encoding is 34 bytes", () => {
  assert.equal(ENTRIES_ENCODING, "dogbuild.raw_commit.entries.v1");
  assert.equal(Buffer.byteLength(ENTRIES_ENCODING), 30);
  assert.equal(encodeEntries([]).length, 34);
});

test("row 13: the R341 line-format collision no longer collides", async () => {
  const lineFormat = (entries) => entries.map(([mode, sha, path]) => `${mode} ${sha}\t${path}\n`).join("");
  const one = [["100644", b40, `p\n100644 ${b40}\tq`]];
  const two = [["100644", b40, "p"], ["100644", b40, "q"]];
  // The superseded newline-delimited line format genuinely collides for these two inputs.
  assert.equal(lineFormat(one), lineFormat(two));
  assert.notDeepEqual(encodeEntries(one), encodeEntries(two));
  assert.notEqual(await sha256Hex(encodeEntries(one)), await sha256Hex(encodeEntries(two)));
  assert.deepEqual(decodeEntries(encodeEntries(one)), one);
  assert.deepEqual(decodeEntries(encodeEntries(two)), two);
});

const adversarialPaths = [
  "a b", "back\\slash", "cr\rhere", "ctl\u0001\u001f", "d\ni r/inner\tfile", "d\ni r/x", "p\n100644 " + b40 + "\tq",
  "plain", 'quo"te', "tab\there", "with\nnewline", "ünï", "日本語", "del\u007f", "c1\u0085", "sep  ",
  "nonchar￾￿", "😀", "é", "é", "a", "a b0", "～", "😀x",
];

test("row 13/15: adversarial paths round-trip through decode, re-encode, digest, Merkle and an independent encoder", async () => {
  const tree = makeTree(adversarialPaths.map((path) => ({ path, content: path })));
  const tuples = sortedTuples(tree.entries);
  const bytes = encodeEntries(tuples);
  assert.ok(equalBytes(bytes, referenceEncode(tuples)));
  const decoded = decodeEntries(bytes);
  assert.deepEqual(decoded, tuples);
  assert.ok(equalBytes(encodeEntries(decoded), bytes));
  assert.equal(await sha256Hex(bytes), createHash("sha256").update(referenceEncode(tuples)).digest("hex"));
  // serialized round trip through the production flow (JSON escapes) and the independent encoder
  installRoutes(flowRoutes({ sha: SHA, treeSha: tree.rootSha, parents: [], entries: tree.entries }));
  const { primary } = await getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA });
  assert.equal(primary.status, "COMPLETE");
  const reparsed = JSON.parse(JSON.stringify(primary)).tree_proof;
  const independent = referenceEncode(reparsed.entries);
  assert.equal(independent.length, reparsed.entries_encoded_bytes);
  assert.equal(createHash("sha256").update(independent).digest("hex"), reparsed.entries_sha256);
  assert.ok(independentVerify(reparsed.entries.map(([mode, sha, path]) => ({ mode, sha, path, type: mode === "040000" ? "tree" : mode === "160000" ? "commit" : "blob" })), tree.rootSha).ok);
});

test("row 13: NFC and NFD variants are distinct entries", () => {
  const tuples = [["100644", b40, "é"], ["100644", b40, "é"]];
  const sorted = sortedTuples(tuples.map(([mode, sha, path]) => ({ mode, sha, path, type: "blob" })));
  assert.equal(new Set(sorted.map((t) => t[2])).size, 2);
  assert.notDeepEqual(encodeEntries([tuples[0]]), encodeEntries([tuples[1]]));
});

test("row 13: ordering is by UTF-8 bytes, not UTF-16 units; a prefix sorts first", () => {
  const entries = ["～", "😀", "a b", "a"].map((path) => ({ path, mode: "100644", type: "blob", sha: b40 }));
  assert.deepEqual(sortedTuples(entries).map((t) => t[2]), ["a", "a b", "～", "😀"]);
  // UTF-16 code unit order would put the emoji (0xD83D) before U+FF5E.
  assert.deepEqual(["～", "😀"].sort(), ["😀", "～"]);
});

test("row 13: corrupted encodings fail to decode", () => {
  const good = encodeEntries([["100644", b40, "x"], ["040000", b40, "y"]]);
  const mutate = (fn) => { const copy = Buffer.from(good); return fn(copy) ?? copy; };
  const cases = {
    appended: Buffer.concat([good, Buffer.from([0])]),
    truncated: good.subarray(0, good.length - 1),
    wrongTag: mutate((b) => { b[0] ^= 1; }),
    countHigh: mutate((b) => { b.writeUInt32BE(3, 30); }),
    countLow: mutate((b) => { b.writeUInt32BE(1, 30); }),
    pathLenPastBuffer: mutate((b) => { b.writeUInt32BE(1_000_000, 30 + 4 + 2 + 6); }),
    modeLenNotClosedSet: mutate((b) => { b.writeUInt16BE(5, 34); }),
    unknownMode: mutate((b) => { b.write("100664", 36, "ascii"); }),
    tooShort: good.subarray(0, 10),
  };
  for (const [name, bytes] of Object.entries(cases)) {
    assert.throws(() => decodeEntries(new Uint8Array(bytes)), /malformed/, name);
  }
  assert.throws(() => encodeEntries([["100664", b40, "x"]]));
  assert.throws(() => encodeEntries([["100644", "B".repeat(40), "x"]]));
});

function gitReferenceTree() {
  const dir = mkdtempSync(join(tmpdir(), "dogbuild-ref-"));
  const env = { PATH: process.env.PATH, HOME: dir, GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: "/dev/null", LC_ALL: "C" };
  const git = (args, input) => {
    const r = spawnSync("git", args, { cwd: dir, env, input, encoding: "utf8", maxBuffer: 1 << 26 });
    assert.equal(r.status, 0, r.stderr);
    return r.stdout;
  };
  try {
    git(["init", "-q", "--object-format=sha1"]);
    const files = [
      "a b", "back\\slash", "cr\rhere", "ctl\u0001\u001f", "d\ni r/inner\tfile", "d\ni r/x",
      `p\n100644 ${b40}\tq`, "plain", 'quo"te', "tab\there", "with\nnewline", "ünï", "日本語",
    ];
    let index = "";
    for (const p of files) index += `100644 ${git(["hash-object", "-w", "--stdin"], p).trim()}\t${p}\0`;
    index += `160000 95d1bdf3b8757e97f2ca33fc5de33aff343fddb1\tsubmod\0`;
    git(["update-index", "--add", "-z", "--index-info"], index);
    const tree = git(["write-tree"]).trim();
    const listing = git(["ls-tree", "-r", "-t", "-z", tree]);
    const entries = listing.split("\0").filter(Boolean).map((line) => {
      const tab = line.indexOf("\t");
      const [mode, type, sha] = line.slice(0, tab).split(" ");
      return { mode, type, sha, path: line.slice(tab + 1) };
    });
    return { tree, entries };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test("row 15: the real-Git reference fixture (R343) reproduces its pinned identities", async () => {
  assert.ok(gitAvailable(), "git is required; this test never skips");
  const ref = gitReferenceTree();
  assert.equal(ref.tree, "40e2860c82498d9523f740c1250fe400414bd4e6");
  assert.equal(ref.entries.length, 15);
  installRoutes(flowRoutes({ sha: SHA, treeSha: ref.tree, parents: [], entries: ref.entries }));
  const { primary } = await getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA });
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.tree_proof.entries_encoded_bytes, 669);
  assert.equal(primary.tree_proof.entries_sha256, "2dc616459cfb3cba97175fcbfe5cc6cfc63f9a8f34ba186d86e606a912155a18");
  assert.ok(equalBytes(referenceEncode(primary.tree_proof.entries), encodeEntries(primary.tree_proof.entries)));
  assert.ok(independentVerify(ref.entries, ref.tree).ok);
  // negative controls on the same data
  for (const mutate of [
    (es) => es.filter((e) => e.path !== "with\nnewline"),
    (es) => es.filter((e) => !e.path.startsWith("p\n")),
    (es) => es.map((e) => (e.path === "plain" ? { ...e, sha: hex40(1) } : e)),
  ]) {
    installRoutes(flowRoutes({ sha: SHA, treeSha: ref.tree, parents: [], entries: mutate(ref.entries) }));
    await assert.rejects(getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA }), (e) => e.details.reason === "TREE_HASH_MISMATCH");
  }
});
