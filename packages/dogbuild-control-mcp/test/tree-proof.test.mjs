import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ControlError } from "../src/errors.js";
import {
  EMPTY_TREE_SHA, compareBytes, gitTreeSha1, isValidPath, isWellFormedString, normalizeEntry,
  sortedTuples, verifyRecursiveListing,
} from "../src/tree-proof.js";
import { ENV, OWNER, REPO, SHA, flowRoutes, gitAvailable, hex40, independentVerify, installRoutes, makeTree } from "./raw-support.mjs";
import { getRawCommit } from "../src/raw-commit.js";

const b40 = "b".repeat(40);
const entry = (path, extra = {}) => ({ path, mode: "100644", type: "blob", sha: b40, ...extra });

test("row 14: invalid paths are rejected as INVALID_PATH without echoing the path", () => {
  const invalid = ["", "a\u0000b", "/lead", "trail/", "a//b", "./x", "a/./b", "a/..", "..", ".", "\ud800", "x\udc00y", "a\ud800b/c"];
  for (const path of invalid) {
    assert.equal(isValidPath(path), false, JSON.stringify(path));
    assert.throws(() => normalizeEntry(entry(path)), (e) => e instanceof ControlError && e.details.reason === "INVALID_PATH"
      && !JSON.stringify(e.toJSON()).includes("lead"));
  }
  for (const path of ["a", "a b", "a\nb", "a\tb", "ünï", "😀", "..x", "x..", ".hidden", "a/b/c"]) {
    assert.equal(isValidPath(path), true, JSON.stringify(path));
  }
  assert.equal(isWellFormedString("\ud800"), false);
  assert.equal(isWellFormedString("\udc00\ud800"), false);
  assert.equal(isWellFormedString("a😀"), true);
});

test("row 14: two different lone surrogates both fail rather than collapsing to one digest", () => {
  for (const path of ["x\ud800", "x\udc00"]) assert.throws(() => normalizeEntry(entry(path)));
});

test("row 14: lone surrogates in a response fail the whole flow as INVALID_PATH", async () => {
  const tree = makeTree([{ path: "ok", content: "1" }]);
  const entries = [...tree.entries, entry("bad")];
  const body = JSON.stringify({ sha: tree.rootSha, tree: entries.map((e) => ({ ...e, path: e.path === "bad" ? "\\ud800" : e.path })), truncated: false })
    .replace(/\\\\ud800/g, "\\ud800");
  assert.ok(body.includes('"\\ud800"'));
  const { jsonResponse, GIT } = await import("./raw-support.mjs");
  const routes = flowRoutes({ sha: SHA, treeSha: tree.rootSha, parents: [], entries: tree.entries });
  routes[`${GIT}/trees/${tree.rootSha}?recursive=1`] = jsonResponse(body);
  installRoutes(routes);
  await assert.rejects(getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA }), (e) => e.details.reason === "INVALID_PATH");
});

test("mode/type and sha shape are enforced", () => {
  for (const [mode, type] of [["100664", "blob"], ["100644", "tree"], ["040000", "blob"], ["160000", "blob"], ["0100644", "blob"], ["", "blob"]]) {
    assert.throws(() => normalizeEntry({ path: "a", mode, type, sha: b40 }), (e) => e.details.reason === "UNSUPPORTED_MODE_OR_TYPE");
  }
  for (const sha of ["B".repeat(40), "b".repeat(39), 5, undefined]) {
    assert.throws(() => normalizeEntry({ path: "a", mode: "100644", type: "blob", sha }), (e) => e.details.reason === "ENTRY_SHAPE");
  }
  for (const bad of [null, [], "x", 5]) assert.throws(() => normalizeEntry(bad), (e) => e.details.reason === "ENTRY_SHAPE");
});

test("the empty tree hashes to the well-known SHA and the root of an empty listing verifies", async () => {
  assert.equal(await gitTreeSha1([]), EMPTY_TREE_SHA);
  const counts = await verifyRecursiveListing([], EMPTY_TREE_SHA);
  assert.equal(counts.recursive_entry_count, 0);
  await assert.rejects(verifyRecursiveListing([], hex40(1)), (e) => e.details.reason === "TREE_HASH_MISMATCH");
});

test("tree-as-name-slash ordering: a, a.b, a.txt, a-b, a0 hash exactly as Git does", async () => {
  const tree = makeTree([
    { path: "a/b/f.txt", content: "1\n" }, { path: "a.txt", content: "2\n" }, { path: "a.b/x", content: "3\n" },
    { path: "a-b", content: "6\n" }, { path: "a0", content: "7\n" },
  ]);
  const entries = tree.entries.map(({ path, mode, type, sha }) => ({ path, mode, type, sha }));
  const counts = await verifyRecursiveListing(entries, tree.rootSha);
  assert.equal(counts.tree_count, 3);
  assert.equal(counts.subtree_hashes_verified, 3);
  assert.ok(independentVerify(entries, tree.rootSha).ok);
  // swapping which entry is a directory breaks the ordering and therefore the hash
  assert.equal(compareBytes(new TextEncoder().encode("a/"), new TextEncoder().encode("a.txt")) > 0, true);
});

test("the R340 real-Git reference tree is reproduced and verified", async () => {
  assert.ok(gitAvailable(), "git is required; this test never skips");
  const dir = mkdtempSync(join(tmpdir(), "dogbuild-r340-"));
  const env = { PATH: process.env.PATH, HOME: dir, GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: "/dev/null", LC_ALL: "C" };
  const git = (args, input) => {
    const r = spawnSync("git", args, { cwd: dir, env, input, encoding: "utf8", maxBuffer: 1 << 26 });
    assert.equal(r.status, 0, r.stderr);
    return r.stdout;
  };
  try {
    git(["init", "-q", "--object-format=sha1"]);
    const files = [
      ["100644", "a/b/f.txt", "1\n"], ["100644", "a.txt", "2\n"], ["100644", "a.b/x", "3\n"], ["100644", "ünï/日本.txt", "4\n"],
      ["100755", "zz/run.sh", "5\n"], ["120000", "link", "a.txt"], ["100644", "a-b", "6\n"], ["100644", "a0", "7\n"],
    ];
    let index = "";
    for (const [mode, path, content] of files) index += `${mode} ${git(["hash-object", "-w", "--stdin"], content).trim()}\t${path}\0`;
    index += "160000 95d1bdf3b8757e97f2ca33fc5de33aff343fddb1\tsub\0";
    git(["update-index", "--add", "-z", "--index-info"], index);
    const tree = git(["write-tree"]).trim();
    assert.equal(tree, "3363831b5bbbbcc81cce0361f0eee966e2590412");
    const entries = git(["ls-tree", "-r", "-t", "-z", tree]).split("\0").filter(Boolean).map((line) => {
      const tab = line.indexOf("\t");
      const [mode, type, sha] = line.slice(0, tab).split(" ");
      return { mode, type, sha, path: line.slice(tab + 1) };
    });
    assert.equal(entries.length, 14);
    const counts = await verifyRecursiveListing(entries.map(normalizeEntry), tree);
    assert.equal(counts.tree_count, 5); // 6 tree objects including the root, which is not an entry
    assert.equal(counts.submodule_count, 1);
    assert.ok(independentVerify(entries, tree).ok);
    // negative controls
    for (const mutate of [
      (es) => es.filter((e) => e.path !== "a/b/f.txt"),
      (es) => es.filter((e) => !e.path.startsWith("zz/")),
      (es) => es.map((e) => (e.path === "a/b/f.txt" ? { ...e, sha: hex40(2) } : e)),
      (es) => es.map((e) => (e.path === "zz/run.sh" ? { ...e, mode: "100644" } : e)),
      (es) => [...es, entry("extra")],
      (es) => es.map((e) => (e.path === "a/b/f.txt" ? { ...e, path: "a/b/g.txt" } : e)),
    ]) {
      await assert.rejects(verifyRecursiveListing(mutate(entries).map(normalizeEntry), tree), (e) => e.details.reason === "TREE_HASH_MISMATCH");
    }
    await assert.rejects(verifyRecursiveListing([...entries, entry("q/x")].map(normalizeEntry), tree), (e) => e.details.reason === "ORPHAN_PATH");
    await assert.rejects(verifyRecursiveListing([...entries, entries[0]].map(normalizeEntry), tree), (e) => e.details.reason === "DUPLICATE_PATH");
    await assert.rejects(verifyRecursiveListing([...entries, entry("sub/x")].map(normalizeEntry), tree), (e) => e.details.reason === "ORPHAN_PATH");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("the deadline tick is called between trees and may abort the proof", async () => {
  const tree = makeTree([{ path: "a/x", content: "1" }, { path: "b/y", content: "2" }]);
  let ticks = 0;
  await verifyRecursiveListing(tree.entries.map(normalizeEntry), tree.rootSha, () => { ticks += 1; });
  assert.equal(ticks, 3);
  await assert.rejects(verifyRecursiveListing(tree.entries.map(normalizeEntry), tree.rootSha, () => { throw new Error("deadline"); }), /deadline/);
});

test("sortedTuples orders by UTF-8 bytes", () => {
  const tuples = sortedTuples([entry("b"), entry("a"), entry("～"), entry("😀")]);
  assert.deepEqual(tuples.map((t) => t[2]), ["a", "b", "～", "😀"]);
});
