import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { GIT, OWNER, REPO, SHA, callRaw, flowRoutes, installRoutes, smallFlow, hex40 } from "./raw-support.mjs";

const ARGS = { owner: OWNER, repo: REPO, sha: SHA };
const parse = async (r) => JSON.parse((await r.json()).result.content[0].text);

test("row 23: every INCOMPLETE reason is incomplete=false, never COMPLETE, with proof withheld", async () => {
  const flow = smallFlow();
  installRoutes(flowRoutes({ sha: SHA, treeSha: flow.tree.rootSha, parents: flow.parents, entries: flow.tree.entries, truncatedRec: true }));
  const truncated = await parse(await callRaw(worker, ARGS));
  assert.equal(truncated.status, "INCOMPLETE");
  assert.equal(truncated.complete, false);
  assert.equal(truncated.incomplete_reason, "GITHUB_TRUNCATED");
  assert.equal(truncated.tree_proof, null);
  assert.equal(Object.keys(truncated).length, 13);

  const big = [];
  for (let i = 0; i < 1001; i += 1) big.push({ path: `f${i}`, content: String(i) });
  const rootCap = smallFlow({ files: big, parents: [hex40(1)] });
  installRoutes(rootCap.routes);
  const capped = await parse(await callRaw(worker, ARGS));
  assert.equal(capped.status, "INCOMPLETE");
  assert.equal(capped.incomplete_reason, "ROOT_ENTRY_CAP_EXCEEDED");
  assert.equal(capped.tree_proof, null);
  assert.deepEqual(capped.parents, [hex40(1)]);

  installRoutes({ [`${GIT}/commits/${SHA}`]: new Response(JSON.stringify({}), { headers: { "content-type": "application/json", "content-length": "9999999" } }) });
  const large = await parse(await callRaw(worker, ARGS));
  assert.equal(large.status, "INCOMPLETE");
  assert.equal(large.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(large.complete, false);
});

test("row 23: a COMPLETE result has 12 keys and complete=true", async () => {
  installRoutes(smallFlow().routes);
  const value = await parse(await callRaw(worker, ARGS));
  assert.equal(value.status, "COMPLETE");
  assert.equal(value.complete, true);
  assert.equal(Object.keys(value).length, 12);
  assert.equal(Object.keys(value.tree_proof).length, 10);
  assert.equal(Object.keys(value.limits).length, 6);
});
