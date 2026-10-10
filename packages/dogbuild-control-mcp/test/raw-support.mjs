// Test support for get_raw_commit (additive; helpers.mjs is untouched).
// Provides a Response-based fetch mock, simulated GitHub tree bodies, a
// genuine-Git fixture generator and an independently written Merkle verifier.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

export const OWNER = "mantoshkumar1";
export const REPO = "dogbuild";
export const GIT = `/repos/${OWNER}/${REPO}/git`;
export const ENV = Object.freeze({
  GITHUB_TOKEN: "TEST_GITHUB_TOKEN_NOT_REAL",
  ALLOWED_REPOS: "mantoshkumar1/pingstep,mantoshkumar1/dogbuild",
  MCP_PATH_SECRET: "test-path-secret-0123456789abcdef",
  MCP_ACCESS_TOKEN: "TEST_MCP_ACCESS_TOKEN_NOT_REAL_0123456789abcdef",
});
export const SHA = "c".repeat(40);
export const TREE = "d".repeat(40);
export const EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";

export const hex40 = (n) => n.toString(16).padStart(40, "0");

export function jsonResponse(value, { status = 200, headers = {}, space = 0 } = {}) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, space || undefined);
  return new Response(text, { status, headers: { "content-type": "application/json; charset=utf-8", ...headers } });
}

/** Response whose body is delivered in explicit chunks; `onCancel` observes reader.cancel(). */
export function chunkedResponse(chunks, { status = 200, headers = {}, onCancel = () => {}, stall = false } = {}) {
  let i = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (i < chunks.length) controller.enqueue(chunks[i++]);
      else if (stall) return new Promise(() => {});
      else controller.close();
    },
    cancel() { onCancel(); },
  });
  return new Response(stream, { status, headers: { "content-type": "application/json", ...headers } });
}

/** Install a recording fetch. `handler({url, parsed, init, n})` returns a Response. */
export function installFetch(handler) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    calls.push({
      method: String(init.method || "GET").toUpperCase(),
      url: parsed.toString(),
      pathname: parsed.pathname,
      search: parsed.search,
      redirect: init.redirect,
      headers: init.headers || {},
    });
    return handler({ url: parsed.toString(), parsed, init, n: calls.length });
  };
  return calls;
}

/** Route by "<pathname><search>" with a default of throwing on unmatched requests. */
export function installRoutes(routes) {
  return installFetch(({ parsed }) => {
    const route = routes[`${parsed.pathname}${parsed.search}`];
    if (route === undefined) throw new Error(`unmatched request: ${parsed.pathname}${parsed.search}`);
    return typeof route === "function" ? route() : route.clone();
  });
}

export function commitBody(sha, treeSha, parents) {
  return {
    sha,
    node_id: "C_x",
    url: `https://api.github.com${GIT}/commits/${sha}`,
    author: { name: "SENTINEL_AUTHOR_NAME", email: "sentinel@example.invalid", date: "2026-01-01T00:00:00Z" },
    committer: { name: "SENTINEL_AUTHOR_NAME", email: "sentinel@example.invalid", date: "2026-01-01T00:00:00Z" },
    message: "SENTINEL_COMMIT_MESSAGE",
    tree: { sha: treeSha, url: `https://api.github.com${GIT}/trees/${treeSha}` },
    parents: parents.map((p) => ({ sha: p, url: `https://api.github.com${GIT}/commits/${p}`, html_url: "x" })),
    verification: { verified: false, reason: "unsigned", signature: null, payload: null },
  };
}

/** Simulated documented tree-response shape (blob `size` = content bytes). */
export function treeBody(treeSha, entries, truncated = false) {
  return {
    sha: treeSha,
    url: `https://api.github.com${GIT}/trees/${treeSha}`,
    tree: entries.map((e) => {
      const out = { path: e.path, mode: e.mode, type: e.type };
      if (e.type === "blob") out.size = e.size ?? new TextEncoder().encode(e.path).length;
      out.sha = e.sha;
      out.url = `https://api.github.com${GIT}/${e.type === "tree" ? "trees" : "blobs"}/${e.sha}`;
      return out;
    }),
    truncated,
  };
}

/** Routes for a complete, honest flow. */
export function flowRoutes({ sha = SHA, treeSha, parents = [], entries, rootEntries, space = 0, truncatedRoot = false, truncatedRec = false }) {
  const top = rootEntries ?? entries.filter((e) => !e.path.includes("/"));
  return {
    [`${GIT}/commits/${sha}`]: jsonResponse(commitBody(sha, treeSha, parents)),
    [`${GIT}/trees/${treeSha}`]: jsonResponse(treeBody(treeSha, top, truncatedRoot), { space }),
    [`${GIT}/trees/${treeSha}?recursive=1`]: jsonResponse(treeBody(treeSha, entries, truncatedRec), { space }),
  };
}

export const sha1hex = (buf) => createHash("sha1").update(buf).digest("hex");

/** Independently written Git tree-object verifier (does not import production code). */
export function independentVerify(entries, rootSha) {
  const kids = new Map([[""  , []]]);
  const types = new Map();
  for (const e of entries) {
    const i = e.path.lastIndexOf("/");
    const dir = i < 0 ? "" : e.path.slice(0, i);
    const name = i < 0 ? e.path : e.path.slice(i + 1);
    if (!kids.has(dir)) kids.set(dir, []);
    kids.get(dir).push({ name, mode: e.mode, type: e.type, sha: e.sha });
    if (e.type === "tree") { types.set(e.path, e.sha); if (!kids.has(e.path)) kids.set(e.path, []); }
  }
  const hashDir = (dir) => {
    const list = kids.get(dir).map((k) => ({ ...k, nb: Buffer.from(k.name, "utf8") }));
    const key = (k) => (k.type === "tree" ? Buffer.concat([k.nb, Buffer.from("/")]) : k.nb);
    list.sort((a, b) => Buffer.compare(key(a), key(b)));
    const body = Buffer.concat(list.flatMap((k) => [
      Buffer.from(`${k.type === "tree" ? "40000" : k.mode} `), k.nb, Buffer.from([0]), Buffer.from(k.sha, "hex"),
    ]));
    return sha1hex(Buffer.concat([Buffer.from(`tree ${body.length}\0`), body]));
  };
  let ok = hashDir("") === rootSha;
  let verified = 0;
  for (const [dir, sha] of types) { if (hashDir(dir) !== sha) ok = false; else verified += 1; }
  return { ok, verified };
}

// ---------------------------------------------------------------------------
// Genuine Git fixture generator (spec: R355 section 3).
// ---------------------------------------------------------------------------
export function gitAvailable() {
  const r = spawnSync("git", ["--version"], { encoding: "utf8" });
  return r.status === 0;
}

export function generateGitFixture({ L1, L2, parents = 170 }) {
  const dir = mkdtempSync(join(tmpdir(), "dogbuild-fixture-"));
  const env = {
    PATH: process.env.PATH, HOME: dir, GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: "/dev/null",
    LC_ALL: "C", TZ: "UTC",
    GIT_AUTHOR_NAME: "DogBuild Fixture", GIT_AUTHOR_EMAIL: "fixture@dogbuild.invalid", GIT_AUTHOR_DATE: "1767225600 +0000",
    GIT_COMMITTER_NAME: "DogBuild Fixture", GIT_COMMITTER_EMAIL: "fixture@dogbuild.invalid", GIT_COMMITTER_DATE: "1767225600 +0000",
  };
  const git = (args, input) => {
    const r = spawnSync("git", args, { cwd: dir, env, input, encoding: input instanceof Buffer ? "buffer" : "utf8", maxBuffer: 1 << 28 });
    if (r.status !== 0) throw new Error(`git ${args.join(" ")} failed: ${r.stderr}`);
    return typeof r.stdout === "string" ? r.stdout.trim() : r.stdout;
  };
  try {
    git(["init", "-q", "--object-format=sha1"]);
    const pad = (s, n) => s + "x".repeat(n - s.length);
    const paths = [];
    for (let d = 0; d < 1000; d += 1) {
      const dn = pad(`d${String(d).padStart(4, "0")}`, L1);
      for (const f of ["f0", "f1", "f2"]) paths.push(`${dn}/${pad(f, L2)}`);
    }
    const index = [];
    for (const p of paths) {
      const blob = git(["hash-object", "-w", "--stdin"], p);
      index.push(`100644 ${blob}\t${p}\0`);
    }
    git(["update-index", "--add", "-z", "--index-info"], index.join(""));
    const tree = git(["write-tree"]);
    const emptyTree = git(["hash-object", "-t", "tree", "-w", "--stdin"], "");
    const parentShas = [];
    for (let i = 0; i < parents; i += 1) parentShas.push(git(["commit-tree", emptyTree, "-m", `p${i}`]));
    const commit = git(["commit-tree", tree, ...parentShas.flatMap((p) => ["-p", p]), "-m", "fixture"]);
    const readTree = git(["rev-parse", `${commit}^{tree}`]);
    const revList = git(["rev-list", "--parents", "-n1", commit]);
    const listing = git(["ls-tree", "-r", "-t", "-z", commit], undefined);
    const entries = listing.split("\0").filter(Boolean).map((line) => {
      const tab = line.indexOf("\t");
      const [mode, type, sha] = line.slice(0, tab).split(" ");
      return { mode, type, sha, path: line.slice(tab + 1) };
    });
    return { tree, commit, parents: parentShas, readTree, revList, entries };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

// ---------------------------------------------------------------------------
// In-memory tree builder (real Git object hashing, no git binary needed).
// ---------------------------------------------------------------------------
export function blobSha(content) {
  const b = Buffer.isBuffer(content) ? content : Buffer.from(content, "utf8");
  return sha1hex(Buffer.concat([Buffer.from(`blob ${b.length}\0`), b]));
}

function treeObjectSha(kids) {
  const list = kids.map((k) => ({ ...k, nb: Buffer.from(k.name, "utf8") }));
  const key = (k) => (k.type === "tree" ? Buffer.concat([k.nb, Buffer.from("/")]) : k.nb);
  list.sort((a, b) => Buffer.compare(key(a), key(b)));
  const body = Buffer.concat(list.flatMap((k) => [
    Buffer.from(`${k.type === "tree" ? "40000" : k.mode} `), k.nb, Buffer.from([0]), Buffer.from(k.sha, "hex"),
  ]));
  return sha1hex(Buffer.concat([Buffer.from(`tree ${body.length}\0`), body]));
}

/** files: [{path, content?, mode?, gitlink?}] -> { entries, rootSha } with consistent Git shas. */
export function makeTree(files) {
  const entries = new Map();
  for (const f of files) {
    if (f.gitlink) entries.set(f.path, { path: f.path, mode: "160000", type: "commit", sha: f.gitlink });
    else entries.set(f.path, { path: f.path, mode: f.mode ?? "100644", type: "blob", sha: blobSha(f.content ?? f.path) });
    const parts = f.path.split("/");
    for (let i = 1; i < parts.length; i += 1) {
      const dir = parts.slice(0, i).join("/");
      if (!entries.has(dir)) entries.set(dir, { path: dir, mode: "040000", type: "tree", sha: "" });
    }
  }
  const dirs = [...entries.values()].filter((e) => e.type === "tree").map((e) => e.path);
  dirs.sort((a, b) => b.split("/").length - a.split("/").length);
  const kidsOf = (dir) => [...entries.values()].filter((e) => {
    const i = e.path.lastIndexOf("/");
    return (i < 0 ? "" : e.path.slice(0, i)) === dir;
  }).map((e) => ({ name: e.path.slice(dir === "" ? 0 : dir.length + 1), mode: e.mode, type: e.type, sha: e.sha }));
  for (const dir of dirs) entries.get(dir).sha = treeObjectSha(kidsOf(dir));
  return { entries: [...entries.values()], rootSha: treeObjectSha(kidsOf("")) };
}

export const clone = (value) => JSON.parse(JSON.stringify(value));

/** A small honest flow: returns routes, ids and the tree. */
export function smallFlow({ parents = [hex40(1), hex40(2)], files, space = 0 } = {}) {
  const tree = makeTree(files ?? [
    { path: "README.md", content: "readme\n" },
    { path: "src/a.js", content: "a\n" },
    { path: "src/lib/b.js", content: "b\n" },
    { path: "run.sh", content: "#!/bin/sh\n", mode: "100755" },
  ]);
  const sha = SHA;
  const routes = flowRoutes({ sha, treeSha: tree.rootSha, parents, entries: tree.entries, space });
  return { sha, tree, parents, routes, path: (suffix) => `${GIT}/${suffix}` };
}

/** Call the production tool through the real default export fetch. */
export async function callRaw(worker, args, { id = 1, env = ENV, omitId = false, rawBody } = {}) {
  const body = rawBody ?? JSON.stringify({
    jsonrpc: "2.0",
    ...(omitId ? {} : { id }),
    method: "tools/call",
    params: { name: "get_raw_commit", arguments: args },
  });
  return worker.fetch(new Request(`https://control.example/mcp/${env.MCP_PATH_SECRET}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.MCP_ACCESS_TOKEN}`, "Content-Type": "application/json" },
    body,
  }), env);
}
