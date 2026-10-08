import { test, mock } from "node:test";
import assert from "node:assert/strict";
import { getRawCommit } from "../src/raw-commit.js";
import { ErrorClass } from "../src/errors.js";
import { RAW_MAX_RESPONSE_BYTES } from "../src/github.js";
import {
  ENV, GIT, OWNER, REPO, SHA, EMPTY_TREE, chunkedResponse, clone, commitBody, flowRoutes, hex40,
  installFetch, installRoutes, jsonResponse, makeTree, smallFlow, treeBody,
} from "./raw-support.mjs";

const ARGS = { owner: OWNER, repo: REPO, sha: SHA };
const run = (args = ARGS) => getRawCommit(ENV, args);
async function failure(promise) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  assert.fail("expected a rejection");
}
const reasonOf = (error) => [error.class, error.details.reason];

test("row 1: a valid flow returns exact identities, ordered parents and three GETs", async () => {
  const flow = smallFlow();
  const calls = installRoutes(flow.routes);
  const { primary, degraded } = await run();
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.complete, true);
  assert.equal(primary.sha, SHA);
  assert.equal(primary.requested_sha, SHA);
  assert.equal(primary.tree_sha, flow.tree.rootSha);
  assert.deepEqual(primary.parents, flow.parents);
  assert.equal(primary.parent_count, 2);
  assert.equal(primary.parents_duplicate_present, false);
  assert.equal(primary.commit_object_rehash, "NOT_PERFORMED");
  assert.equal("incomplete_reason" in primary, false);
  assert.equal(calls.length, 3);
  assert.deepEqual([...new Set(calls.map((c) => c.method))], ["GET"]);
  assert.ok(calls.every((c) => c.redirect === "manual"));
  assert.deepEqual(calls.map((c) => c.pathname + c.search), [
    `${GIT}/commits/${SHA}`, `${GIT}/trees/${flow.tree.rootSha}`, `${GIT}/trees/${flow.tree.rootSha}?recursive=1`,
  ]);
  const proof = primary.tree_proof;
  assert.equal(proof.root_entry_count, 3);
  assert.equal(proof.recursive_entry_count, 6);
  assert.equal(proof.tree_count, 2);
  assert.equal(proof.blob_count, 4);
  assert.equal(proof.submodule_count, 0);
  assert.equal(proof.subtree_hashes_verified, 2);
  assert.equal(degraded.incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
  assert.equal(degraded.tree_proof.entries, null);
  const serialized = JSON.stringify(primary);
  for (const secret of ["SENTINEL_COMMIT_MESSAGE", "SENTINEL_AUTHOR_NAME", "sentinel@example.invalid", ENV.GITHUB_TOKEN]) {
    assert.ok(!serialized.includes(secret), secret);
  }
});

test("row 1: entries are sorted by UTF-8 bytes and carry API-form modes", async () => {
  const flow = smallFlow({ files: [
    { path: "b", content: "1" }, { path: "a.b", content: "2" }, { path: "a/x", content: "3" },
    { path: "a-b", content: "4" }, { path: "a0", content: "5" }, { path: "ünï/日本.txt", content: "6" },
    { path: "z.sh", content: "7", mode: "100755" }, { path: "link", content: "a.b", mode: "120000" },
    { path: "sub", gitlink: hex40(99) },
  ] });
  installRoutes(flow.routes);
  const { primary } = await run();
  const paths = primary.tree_proof.entries.map((e) => e[2]);
  assert.deepEqual(paths, [...paths].sort((x, y) => Buffer.compare(Buffer.from(x), Buffer.from(y))));
  assert.deepEqual(primary.tree_proof.entries.find((e) => e[2] === "a")[0], "040000");
  assert.equal(primary.tree_proof.submodule_count, 1);
});

const parentCases = [
  ["root commit", []],
  ["single parent", [hex40(7)]],
  ["two-parent merge", [hex40(2), hex40(1)]],
  ["three-parent octopus", [hex40(3), hex40(1), hex40(2)]],
];
for (const [name, parents] of parentCases) {
  test(`row 2: ${name} keeps verbatim parent order`, async () => {
    installRoutes(smallFlow({ parents }).routes);
    const { primary } = await run();
    assert.deepEqual(primary.parents, parents);
    assert.equal(primary.parent_count, parents.length);
  });
}

test("row 2: parent order is asserted against a swapped-order negative", async () => {
  const flow = smallFlow({ parents: [hex40(1), hex40(2)] });
  installRoutes(flow.routes);
  const { primary } = await run();
  assert.notDeepEqual(primary.parents, [hex40(2), hex40(1)]);
});

test("row 2: duplicate parents are reported verbatim and flagged", async () => {
  installRoutes(smallFlow({ parents: [hex40(1), hex40(1), hex40(2)] }).routes);
  const { primary } = await run();
  assert.deepEqual(primary.parents, [hex40(1), hex40(1), hex40(2)]);
  assert.equal(primary.parents_duplicate_present, true);
});

test("row 2: no parent cap - 300 parents are returned unchanged", async () => {
  const parents = Array.from({ length: 300 }, (_, i) => hex40(i + 1));
  installRoutes(smallFlow({ parents }).routes);
  const { primary } = await run();
  assert.deepEqual(primary.parents, parents);
});

function commitRoute(mutate) {
  const flow = smallFlow();
  const body = commitBody(SHA, flow.tree.rootSha, flow.parents);
  mutate(body);
  return { [`${GIT}/commits/${SHA}`]: jsonResponse(body) };
}
const parentNegatives = [
  ["parents absent", (b) => { delete b.parents; }, "PARENTS_MISSING"],
  ["parents null", (b) => { b.parents = null; }, "PARENTS_MISSING"],
  ["parents object", (b) => { b.parents = {}; }, "PARENTS_MISSING"],
  ["element is a string", (b) => { b.parents = [hex40(1)]; }, "PARENT_SHAPE"],
  ["element null", (b) => { b.parents = [null]; }, "PARENT_SHAPE"],
  ["element lacks sha", (b) => { b.parents = [{ url: "x" }]; }, "PARENT_SHAPE"],
  ["element sha uppercase", (b) => { b.parents = [{ sha: "A".repeat(40) }]; }, "PARENT_SHAPE"],
  ["element sha 39 chars", (b) => { b.parents = [{ sha: "a".repeat(39) }]; }, "PARENT_SHAPE"],
  ["element sha 41 chars", (b) => { b.parents = [{ sha: "a".repeat(41) }]; }, "PARENT_SHAPE"],
  ["element sha non-hex", (b) => { b.parents = [{ sha: "g".repeat(40) }]; }, "PARENT_SHAPE"],
];
for (const [name, mutate, reason] of parentNegatives) {
  test(`row 2: negative - ${name}`, async () => {
    const calls = installRoutes(commitRoute((b) => {
      if (name.startsWith("element is a string")) { mutate(b); b.parents = [hex40(1)]; } else mutate(b);
    }));
    const error = await failure(run());
    assert.deepEqual(reasonOf(error), [ErrorClass.UPSTREAM_MALFORMED, reason]);
    assert.equal(calls.length, 1);
  });
}

test("row 3: malformed SHAs and extra keys fail before any GET", async () => {
  const calls = installRoutes({});
  for (const sha of ["A".repeat(40), "a".repeat(39), "a".repeat(41), "g".repeat(40), 42, null, undefined]) {
    const error = await failure(run({ owner: OWNER, repo: REPO, sha }));
    assert.equal(error.class, ErrorClass.INVALID_INPUT);
    assert.equal(error.details.reason, "INVALID_SHA");
  }
  for (const args of [{ ...ARGS, extra: 1 }, { owner: OWNER, repo: REPO }, null, [], "x"]) {
    const error = await failure(run(args));
    assert.equal(error.details.reason, "INVALID_ARGUMENTS");
  }
  assert.equal(calls.length, 0);
});

test("row 3: allowlist denial and an unset allowlist issue zero GETs", async () => {
  const calls = installRoutes({});
  const denied = await failure(getRawCommit(ENV, { owner: "someone", repo: "else", sha: SHA }));
  assert.deepEqual(reasonOf(denied), [ErrorClass.ALLOWLIST_DENIED, "REPOSITORY_NOT_ALLOWED"]);
  const unset = await failure(getRawCommit({ ...ENV, ALLOWED_REPOS: "" }, ARGS));
  assert.equal(unset.class, ErrorClass.CONFIG_INVALID);
  assert.equal(calls.length, 0);
});

test("row 4: commit and tree binding failures", async () => {
  for (const sha of [undefined, hex40(5)]) {
    const flow = smallFlow();
    const body = commitBody(SHA, flow.tree.rootSha, flow.parents);
    if (sha === undefined) delete body.sha; else body.sha = sha;
    installRoutes({ [`${GIT}/commits/${SHA}`]: jsonResponse(body) });
    assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.HEAD_MISMATCH, "COMMIT_SHA_MISMATCH"]);
  }
  for (const tree of [undefined, null, { sha: "x" }, { sha: "A".repeat(40) }]) {
    const flow = smallFlow();
    const body = commitBody(SHA, flow.tree.rootSha, flow.parents);
    if (tree === undefined) delete body.tree; else body.tree = tree;
    installRoutes({ [`${GIT}/commits/${SHA}`]: jsonResponse(body) });
    assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.UPSTREAM_MALFORMED, "COMMIT_TREE_SHAPE"]);
  }
  for (const which of ["root", "recursive"]) {
    const flow = smallFlow();
    const r = flow.routes;
    const rootKey = `${GIT}/trees/${flow.tree.rootSha}`;
    const key = which === "root" ? rootKey : `${rootKey}?recursive=1`;
    const body = JSON.parse(await r[key].text());
    body.sha = hex40(9);
    r[key] = jsonResponse(body);
    installRoutes(r);
    assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.HEAD_MISMATCH, "ROOT_TREE_SHA_MISMATCH"]);
  }
});

test("row 5: truncated true is INCOMPLETE and never complete", async () => {
  for (const [truncatedRoot, truncatedRec, calls] of [[true, false, 2], [false, true, 3]]) {
    const flow = smallFlow();
    const fetchCalls = installRoutes(flowRoutes({
      sha: SHA, treeSha: flow.tree.rootSha, parents: flow.parents, entries: flow.tree.entries, truncatedRoot, truncatedRec,
    }));
    const { primary, degraded } = await run();
    assert.equal(primary.status, "INCOMPLETE");
    assert.equal(primary.complete, false);
    assert.equal(primary.incomplete_reason, "GITHUB_TRUNCATED");
    assert.equal(primary.tree_proof, null);
    assert.deepEqual(primary.parents, flow.parents);
    assert.equal(degraded, null);
    assert.equal(fetchCalls.length, calls);
  }
});

test("row 5: truncated absent, string or null is malformed", async () => {
  for (const value of [undefined, "false", null, 0]) {
    const flow = smallFlow();
    const key = `${GIT}/trees/${flow.tree.rootSha}`;
    const body = treeBody(flow.tree.rootSha, flow.tree.entries.filter((e) => !e.path.includes("/")));
    if (value === undefined) delete body.truncated; else body.truncated = value;
    installRoutes({ ...flow.routes, [key]: jsonResponse(body) });
    assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.UPSTREAM_MALFORMED, "TRUNCATED_FLAG_MISSING"]);
  }
});

async function mutatedRecursive(mutate, { rootEntries } = {}) {
  const flow = smallFlow({ files: [
    { path: "a/b/f.txt", content: "1" }, { path: "a.txt", content: "2" }, { path: "a.b/x", content: "3" },
    { path: "ünï/日本.txt", content: "4" }, { path: "zz/run.sh", content: "5", mode: "100755" },
    { path: "link", content: "a.txt", mode: "120000" }, { path: "sub", gitlink: hex40(77) },
    { path: "empty/keep", content: "k" },
  ] });
  const entries = clone(flow.tree.entries);
  const list = mutate(entries, flow) ?? entries;
  const routes = flowRoutes({
    sha: SHA, treeSha: flow.tree.rootSha, parents: flow.parents, entries: list,
    rootEntries: rootEntries ? rootEntries(flow.tree.entries) : flow.tree.entries.filter((e) => !e.path.includes("/")),
  });
  installRoutes(routes);
  return flow;
}

test("row 6: positives - mixed modes, submodule, non-ASCII and git-ordering names verify", async () => {
  await mutatedRecursive(() => undefined);
  const { primary } = await run();
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.tree_proof.submodule_count, 1);
});

test("row 6: positive - the empty tree verifies", async () => {
  const flow = smallFlow({ files: [] });
  assert.equal(flow.tree.rootSha, EMPTY_TREE);
  installRoutes(flow.routes);
  const { primary } = await run();
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.tree_proof.recursive_entry_count, 0);
  assert.equal(primary.tree_proof.entries_encoded_bytes, 34);
});

const merkleNegatives = [
  ["omitted nested blob with truncated:false", (es) => es.filter((e) => e.path !== "a/b/f.txt"), "TREE_HASH_MISMATCH"],
  ["omitted subtree contents", (es) => es.filter((e) => !e.path.startsWith("zz/")), "TREE_HASH_MISMATCH"],
  ["altered nested sha", (es) => { es.find((e) => e.path === "a/b/f.txt").sha = hex40(3); }, "TREE_HASH_MISMATCH"],
  ["altered mode", (es) => { es.find((e) => e.path === "zz/run.sh").mode = "100644"; }, "TREE_HASH_MISMATCH"],
  ["injected extra entry", (es) => [...es, { path: "extra", mode: "100644", type: "blob", sha: hex40(4) }], "TREE_HASH_MISMATCH"],
  ["renamed path", (es) => { es.find((e) => e.path === "a/b/f.txt").path = "a/b/g.txt"; }, "TREE_HASH_MISMATCH"],
  ["orphan path", (es) => [...es, { path: "nowhere/x", mode: "100644", type: "blob", sha: hex40(4) }], "ORPHAN_PATH"],
  ["duplicate path", (es) => [...es, clone(es.find((e) => e.path === "a.txt"))], "DUPLICATE_PATH"],
  ["child under a submodule", (es) => [...es, { path: "sub/x", mode: "100644", type: "blob", sha: hex40(4) }], "ORPHAN_PATH"],
  ["child under a blob", (es) => [...es, { path: "a.txt/x", mode: "100644", type: "blob", sha: hex40(4) }], "ORPHAN_PATH"],
  ["unsupported mode", (es) => { es.find((e) => e.path === "a.txt").mode = "100664"; }, "UNSUPPORTED_MODE_OR_TYPE"],
  ["mode/type mismatch", (es) => { es.find((e) => e.path === "a.txt").type = "tree"; }, "UNSUPPORTED_MODE_OR_TYPE"],
  ["wrong empty-tree declaration", (es) => { es.find((e) => e.path === "empty/keep").sha = EMPTY_TREE; }, "TREE_HASH_MISMATCH"],
];
for (const [name, mutate, reason] of merkleNegatives) {
  test(`row 6: negative - ${name}`, async () => {
    await mutatedRecursive(mutate);
    const error = await failure(run());
    assert.deepEqual(reasonOf(error), [ErrorClass.UPSTREAM_MALFORMED, reason]);
    assert.ok(!JSON.stringify(error.toJSON()).includes("a/b"), "paths are never echoed");
  });
}

test("row 6: root and recursive responses must agree", async () => {
  await mutatedRecursive(() => undefined, {
    rootEntries: (es) => es.filter((e) => !e.path.includes("/")).map((e) => (e.path === "a.txt" ? { ...e, sha: hex40(8) } : e)),
  });
  assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.UPSTREAM_MALFORMED, "ROOT_RECURSIVE_DISAGREEMENT"]);
});

test("row 6: an empty-tree commit with a non-empty listing and an empty listing with a wrong tree both fail", async () => {
  const flow = smallFlow({ files: [{ path: "x", content: "1" }] });
  installRoutes(flowRoutes({ sha: SHA, treeSha: flow.tree.rootSha, parents: [], entries: [], rootEntries: [] }));
  assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.UPSTREAM_MALFORMED, "TREE_HASH_MISMATCH"]);
});

test("row 7: root entry cap at 1,000 passes and 1,001 stops before the third GET", async () => {
  for (const [count, expectComplete] of [[1000, true], [1001, false]]) {
    const flow = smallFlow({ files: Array.from({ length: count }, (_, i) => ({ path: `f${String(i).padStart(5, "0")}`, content: String(i) })) });
    const calls = installRoutes(flow.routes);
    const { primary } = await run();
    if (expectComplete) {
      assert.equal(primary.status, "COMPLETE");
      assert.equal(calls.length, 3);
    } else {
      assert.equal(primary.incomplete_reason, "ROOT_ENTRY_CAP_EXCEEDED");
      assert.equal(calls.length, 2);
    }
  }
});

test("row 7: recursive entry cap at 20,000 passes and 20,001 is INCOMPLETE", async () => {
  const dirs = 20;
  const files = [];
  for (let d = 0; d < dirs; d += 1) for (let i = 0; i < 999; i += 1) files.push({ path: `d${String(d).padStart(2, "0")}/f${String(i).padStart(4, "0")}`, content: `${d}-${i}` });
  // 20 dirs + 19,980 blobs = 20,000 entries exactly.
  const flow = smallFlow({ files });
  assert.equal(flow.tree.entries.length, 20_000);
  const minimal = (list) => JSON.stringify({ sha: flow.tree.rootSha, tree: list.map(({ path, mode, type, sha }) => ({ path, mode, type, sha })), truncated: false });
  const minimalRoutes = (list) => ({
    [`${GIT}/commits/${SHA}`]: jsonResponse(commitBody(SHA, flow.tree.rootSha, [])),
    [`${GIT}/trees/${flow.tree.rootSha}`]: jsonResponse(minimal(list.filter((e) => !e.path.includes("/")))),
    [`${GIT}/trees/${flow.tree.rootSha}?recursive=1`]: jsonResponse(minimal(list)),
  });
  installRoutes(minimalRoutes(flow.tree.entries));
  const started = Date.now();
  const { primary } = await run();
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.tree_proof.recursive_entry_count, 20_000);
  assert.ok(Date.now() - started < 60_000, "row 12: loose wall-clock regression guard");

  const over = clone(flow.tree.entries);
  over.push({ path: "zzzz", mode: "100644", type: "blob", sha: hex40(5) });
  installRoutes(minimalRoutes(over));
  const { primary: capped } = await run();
  assert.equal(capped.incomplete_reason, "RECURSIVE_ENTRY_CAP_EXCEEDED");
  assert.equal(capped.tree_proof, null);
});

function paddedTo(value, size) {
  const text = JSON.stringify(value);
  const pad = size - new TextEncoder().encode(text).length;
  assert.ok(pad >= 0);
  return text + " ".repeat(pad);
}

test("row 7: decoded response bytes at 2,097,152 pass and 2,097,153 fail closed (parsed after the bound)", async () => {
  for (const [size, expectComplete] of [[RAW_MAX_RESPONSE_BYTES, true], [RAW_MAX_RESPONSE_BYTES + 1, false]]) {
    const flow = smallFlow();
    const recKey = `${GIT}/trees/${flow.tree.rootSha}?recursive=1`;
    const body = treeBody(flow.tree.rootSha, flow.tree.entries);
    installRoutes({ ...flow.routes, [recKey]: jsonResponse(paddedTo(body, size)) });
    const { primary } = await run();
    if (expectComplete) assert.equal(primary.status, "COMPLETE");
    else {
      assert.equal(primary.incomplete_reason, "RESPONSE_TOO_LARGE");
      assert.deepEqual(primary.parents, flow.parents);
      assert.equal(primary.tree_proof, null);
    }
  }
});

test("row 7: advertised Content-Length over the cap rejects early and cancels", async () => {
  const flow = smallFlow();
  let cancelled = 0;
  const recKey = `${GIT}/trees/${flow.tree.rootSha}?recursive=1`;
  installRoutes({
    ...flow.routes,
    [recKey]: () => chunkedResponse([new TextEncoder().encode("{}")], {
      headers: { "content-length": String(RAW_MAX_RESPONSE_BYTES + 1) }, onCancel: () => { cancelled += 1; },
    }),
  });
  const { primary } = await run();
  assert.equal(primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.ok(cancelled >= 1);
});

test("row 7: a chunked stream with no length overflows mid-stream and the reader is cancelled", async () => {
  const flow = smallFlow();
  let cancelled = 0;
  const chunk = new Uint8Array(65_536).fill(0x20);
  const chunks = Array.from({ length: 40 }, () => chunk); // 2,162,688 > cap
  const recKey = `${GIT}/trees/${flow.tree.rootSha}?recursive=1`;
  installRoutes({ ...flow.routes, [recKey]: () => chunkedResponse(chunks, { onCancel: () => { cancelled += 1; } }) });
  const { primary } = await run();
  for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r));
  assert.equal(primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(cancelled, 1);
});

test("row 7: a small advertised length cannot hide a large actual body", async () => {
  const flow = smallFlow();
  let cancelled = 0;
  const chunk = new Uint8Array(65_536).fill(0x20);
  const recKey = `${GIT}/trees/${flow.tree.rootSha}?recursive=1`;
  installRoutes({
    ...flow.routes,
    [recKey]: () => chunkedResponse(Array.from({ length: 40 }, () => chunk), {
      headers: { "content-length": "10" }, onCancel: () => { cancelled += 1; },
    }),
  });
  const { primary } = await run();
  for (let i = 0; i < 5; i += 1) await new Promise((r) => setImmediate(r));
  assert.equal(primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(cancelled, 1);
});

test("row 7: the commit response itself may be oversized and is INCOMPLETE with nothing proven", async () => {
  const chunk = new Uint8Array(65_536).fill(0x20);
  installRoutes({ [`${GIT}/commits/${SHA}`]: () => chunkedResponse(Array.from({ length: 40 }, () => chunk)) });
  const { primary } = await run();
  assert.equal(primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(primary.sha, null);
  assert.equal(primary.parents, null);
});

test("row 8: a body that stalls past 15 s per GET times out, aborts and cancels the reader", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  let cancelled = 0;
  installRoutes({
    [`${GIT}/commits/${SHA}`]: () => chunkedResponse([new TextEncoder().encode("{")], { stall: true, onCancel: () => { cancelled += 1; } }),
  });
  const pending = failure(run());
  for (let i = 0; i < 20; i += 1) await new Promise((r) => setImmediate(r));
  t.mock.timers.tick(15_000);
  const error = await pending;
  assert.deepEqual(reasonOf(error), [ErrorClass.TIMEOUT, "REQUEST_TIMEOUT"]);
  assert.equal(cancelled, 1);
});

test("row 8: the timer is not cleared when headers arrive - a stall after fetch resolves still times out", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const flow = smallFlow();
  let cancelled = 0;
  installRoutes({
    ...flow.routes,
    [`${GIT}/trees/${flow.tree.rootSha}`]: () => chunkedResponse([], { stall: true, onCancel: () => { cancelled += 1; } }),
  });
  const pending = failure(run());
  for (let i = 0; i < 40; i += 1) await new Promise((r) => setImmediate(r));
  t.mock.timers.tick(15_000);
  assert.deepEqual(reasonOf(await pending), [ErrorClass.TIMEOUT, "REQUEST_TIMEOUT"]);
  assert.equal(cancelled, 1);
});

test("row 8: accumulated time past the shared 45 s deadline is TOTAL_DEADLINE_EXCEEDED", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const flow = smallFlow();
  let cancelled = 0;
  installRoutes({
    ...flow.routes,
    [`${GIT}/commits/${SHA}`]: () => {
      t.mock.timers.setTime(Date.now() + 31_000); // earlier work consumed 31 s of the shared budget
      return jsonResponse(commitBody(SHA, flow.tree.rootSha, flow.parents));
    },
    [`${GIT}/trees/${flow.tree.rootSha}`]: () => chunkedResponse([], { stall: true, onCancel: () => { cancelled += 1; } }),
  });
  const pending = failure(run());
  for (let i = 0; i < 40; i += 1) await new Promise((r) => setImmediate(r));
  t.mock.timers.tick(14_000);
  assert.deepEqual(reasonOf(await pending), [ErrorClass.TIMEOUT, "TOTAL_DEADLINE_EXCEEDED"]);
  assert.equal(cancelled, 1);
});

test("row 8: an exhausted budget between requests stops before the next GET", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout", "Date"] });
  const flow = smallFlow();
  const calls = installRoutes({
    ...flow.routes,
    [`${GIT}/commits/${SHA}`]: () => {
      t.mock.timers.setTime(Date.now() + 50_000);
      return jsonResponse(commitBody(SHA, flow.tree.rootSha, flow.parents));
    },
  });
  assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.TIMEOUT, "TOTAL_DEADLINE_EXCEEDED"]);
  assert.equal(calls.length, 1);
});

for (const status of [301, 302, 307, 308]) {
  test(`row 9: ${status} is denied and never followed`, async () => {
    let cancelled = 0;
    const calls = installRoutes({
      [`${GIT}/commits/${SHA}`]: () => new Response(null, { status, headers: { location: "https://evil.example/x" } }),
    });
    const error = await failure(run());
    assert.deepEqual(reasonOf(error), [ErrorClass.UPSTREAM_MALFORMED, "REDIRECT_DENIED"]);
    assert.equal(calls.length, 1);
    assert.equal(cancelled, 0);
  });
}

test("row 9: response URL, Link header, content type and malformed JSON are fail-closed", async () => {
  const flow = smallFlow();
  const base = { ...flow.routes };
  const commitKey = `${GIT}/commits/${SHA}`;
  const okBody = commitBody(SHA, flow.tree.rootSha, flow.parents);
  const withUrl = (url) => () => {
    const response = jsonResponse(okBody);
    Object.defineProperty(response, "url", { value: url });
    return response;
  };
  const cases = [
    ["RESPONSE_URL_MISMATCH", withUrl(`https://api.github.com${GIT}/commits/${hex40(1)}`)],
    ["RESPONSE_URL_MISMATCH", withUrl(`https://evil.example${GIT}/commits/${SHA}`)],
    ["RESPONSE_URL_MISMATCH", withUrl(`https://api.github.com${GIT}/commits/${SHA}?x=1`)],
    ["UNEXPECTED_PAGINATION", () => jsonResponse(okBody, { headers: { link: '<https://api.github.com/x?page=2>; rel="next"' } })],
    ["CONTENT_TYPE_NOT_JSON", () => new Response(JSON.stringify(okBody), { headers: { "content-type": "text/html" } })],
    ["CONTENT_TYPE_NOT_JSON", () => new Response(JSON.stringify(okBody))],
    ["MALFORMED_JSON", () => jsonResponse("{not json")],
  ];
  for (const [reason, route] of cases) {
    installRoutes({ ...base, [commitKey]: route });
    assert.deepEqual(reasonOf(await failure(run())), [ErrorClass.UPSTREAM_MALFORMED, reason]);
  }
  installRoutes({ ...base, [commitKey]: withUrl(`https://api.github.com${GIT}/commits/${SHA}`) });
  assert.equal((await run()).primary.status, "COMPLETE");
});

test("row 9: non-2xx statuses are classified by status; the hostile body is cancelled and never echoed", async () => {
  const expected = { 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 422: "UNPROCESSABLE", 429: "RATE_LIMIT", 500: "UPSTREAM_ERROR" };
  for (const [status, klass] of Object.entries(expected)) {
    let cancelled = 0;
    installRoutes({
      [`${GIT}/commits/${SHA}`]: () => chunkedResponse([new TextEncoder().encode(`{"message":"HOSTILE_BODY_${ENV.GITHUB_TOKEN}"}`)], { status: Number(status), onCancel: () => { cancelled += 1; } }),
    });
    const error = await failure(run());
    assert.equal(error.class, klass, status);
    assert.ok(!JSON.stringify(error.toJSON()).includes("HOSTILE_BODY"));
    assert.ok(!JSON.stringify(error.toJSON()).includes(ENV.GITHUB_TOKEN));
    assert.equal(cancelled, 1);
  }
  installRoutes({ [`${GIT}/commits/${SHA}`]: () => jsonResponse({}, { status: 403, headers: { "x-ratelimit-remaining": "0" } }) });
  assert.equal((await failure(run())).class, ErrorClass.RATE_LIMIT);
  installFetch(() => { throw new Error("network details that must not escape"); });
  const net = await failure(run());
  assert.equal(net.class, ErrorClass.UPSTREAM_ERROR);
  assert.ok(!net.message.includes("network details"));
});

test("row 9/11: a missing credential fails before any request", async () => {
  const calls = installRoutes({});
  const error = await failure(getRawCommit({ ...ENV, GITHUB_TOKEN: "" }, ARGS));
  assert.equal(error.class, ErrorClass.CONFIG_INVALID);
  assert.equal(calls.length, 0);
});

test("row 11: every recorded call is a GET; commit text and credentials never appear in any result", async () => {
  const flow = smallFlow();
  const calls = installRoutes(flow.routes);
  const { primary } = await run();
  assert.deepEqual([...new Set(calls.map((c) => c.method))], ["GET"]);
  assert.ok(calls.every((c) => /^Bearer /.test(c.headers.Authorization)));
  assert.ok(!JSON.stringify(primary).includes(ENV.GITHUB_TOKEN));
});

test("row 12: the GET helper cannot issue a fourth request", async () => {
  const { boundedGet, newBoundedSession } = await import("../src/github.js");
  installRoutes({ [`${GIT}/commits/${SHA}`]: () => jsonResponse({}) });
  const session = newBoundedSession();
  for (let i = 0; i < 3; i += 1) await boundedGet(ENV, `${GIT}/commits/${SHA}`, session);
  const error = await failure(boundedGet(ENV, `${GIT}/commits/${SHA}`, session));
  assert.equal(error.details.reason, "GET_BUDGET_EXCEEDED");
});
