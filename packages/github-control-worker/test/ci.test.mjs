import { test } from "node:test";
import assert from "node:assert/strict";
import { foldOverall, getCommitCi, normalizeCheckRun, normalizeCommitStatus } from "../src/ci.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, OTHER_SHA, SHA, checkRun, mockFetch } from "./helpers.mjs";

const BASE = "/repos/mantoshkumar1/pingstep";

function ciRoutes({ checks = [], runs = [], jobs = [], status = { state: "success", sha: SHA, statuses: [] }, linkNext = null } = {}) {
  return {
    [`GET ${BASE}/commits/${SHA}/check-runs`]: { body: { total_count: checks.length, check_runs: checks }, headers: linkNext ? { link: `<${linkNext}>; rel="next"` } : {} },
    [`GET ${BASE}/actions/runs`]: { body: { total_count: runs.length, workflow_runs: runs } },
    [`GET ${BASE}/actions/runs/1/jobs`]: { body: { total_count: jobs.length, jobs } },
    [`GET ${BASE}/commits/${SHA}/status`]: { body: status },
  };
}

test("a non-40-character or non-hex sha is rejected before any request", async () => {
  const calls = mockFetch();
  for (const bad of ["main", "abc", SHA.toUpperCase(), "z".repeat(40), 12345]) {
    await assert.rejects(
      getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: bad }),
      (e) => e.class === ErrorClass.INVALID_INPUT
    );
  }
  assert.equal(calls.length, 0);
});

test("evidence bound to a different commit fails closed", async () => {
  mockFetch(ciRoutes({ checks: [checkRun({ head_sha: OTHER_SHA })] }));
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (e) => e.class === ErrorClass.HEAD_MISMATCH
  );
});

test("a combined status for another commit fails closed", async () => {
  mockFetch(ciRoutes({ status: { state: "success", sha: OTHER_SHA, statuses: [] } }));
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (e) => e.class === ErrorClass.HEAD_MISMATCH
  );
});

test("no evidence at all is unknown, never success", async () => {
  mockFetch(ciRoutes({ status: { state: "pending", sha: SHA, statuses: [] } }));
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.evidence_count, 0);
  assert.equal(r.overall, "unknown");
});

test("pagination is followed to completion", async () => {
  let page = 0;
  globalThis.fetch = async (url) => {
    const u = String(url);
    const isChecks = u.includes("/check-runs");
    if (isChecks) {
      page += 1;
      const first = page === 1;
      return {
        ok: true, status: 200,
        headers: { get: (h) => (h === "link" && first ? `<https://api.github.com${BASE}/commits/${SHA}/check-runs?page=2>; rel="next"` : null) },
        text: async () => JSON.stringify({ check_runs: [checkRun({ id: page, name: `check-${page}` })] }),
      };
    }
    const body = u.includes("/actions/runs") ? { workflow_runs: [] } : { state: "success", sha: SHA, statuses: [] };
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  };
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.check_runs.length, 2, "both pages must be collected");
  assert.equal(r.incomplete, false);
  assert.equal(r.overall, "success");
});

test("truncated pagination marks incomplete and refuses to be green", async () => {
  // Every page advertises another page: the cap trips and incomplete is set.
  globalThis.fetch = async (url) => {
    const u = String(url);
    if (u.includes("/check-runs")) {
      return {
        ok: true, status: 200,
        headers: { get: (h) => (h === "link" ? `<https://api.github.com${BASE}/commits/${SHA}/check-runs?page=99>; rel="next"` : null) },
        text: async () => JSON.stringify({ check_runs: [checkRun()] }),
      };
    }
    const body = u.includes("/actions/runs") ? { workflow_runs: [] } : { state: "success", sha: SHA, statuses: [] };
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  };
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.incomplete, true);
  assert.equal(r.overall, "unknown", "incomplete evidence must never be success");
});

test("check-run normalization covers the full vocabulary", () => {
  assert.equal(normalizeCheckRun({ status: "queued" }), "pending");
  assert.equal(normalizeCheckRun({ status: "in_progress" }), "pending");
  assert.equal(normalizeCheckRun({ status: "completed", conclusion: "success" }), "success");
  for (const c of ["failure", "timed_out", "action_required", "startup_failure"]) {
    assert.equal(normalizeCheckRun({ status: "completed", conclusion: c }), "failure");
  }
  for (const c of ["neutral", "skipped", "cancelled", "stale"]) {
    assert.equal(normalizeCheckRun({ status: "completed", conclusion: c }), "neutral");
  }
  assert.equal(normalizeCheckRun({ status: "completed", conclusion: "something_new" }), "unknown");
  assert.equal(normalizeCheckRun({ status: "weird" }), "unknown");
});

test("commit status normalization", () => {
  assert.equal(normalizeCommitStatus("success"), "success");
  assert.equal(normalizeCommitStatus("failure"), "failure");
  assert.equal(normalizeCommitStatus("error"), "failure");
  assert.equal(normalizeCommitStatus("pending"), "pending");
  assert.equal(normalizeCommitStatus("mystery"), "unknown");
});

test("overall precedence: unknown > failure > pending > success > neutral", () => {
  assert.equal(foldOverall([], false), "unknown");
  assert.equal(foldOverall(["success"], true), "unknown");
  assert.equal(foldOverall(["success", "unknown"], false), "unknown");
  assert.equal(foldOverall(["success", "failure", "pending"], false), "failure");
  assert.equal(foldOverall(["success", "pending"], false), "pending");
  assert.equal(foldOverall(["success", "neutral"], false), "success");
  assert.equal(foldOverall(["neutral"], false), "neutral");
});

test("a failing check makes the whole verdict failure", async () => {
  mockFetch(ciRoutes({ checks: [checkRun(), checkRun({ id: 2, conclusion: "failure" })] }));
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.overall, "failure");
});
