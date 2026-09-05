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

/**
 * Regression suite for FINDING 1 of
 * DB-164-CODEX-GITHUB-CONTROL-TOOLS-IMPLEMENTATION-REVIEW-01: workflow runs
 * and jobs were retrieved but excluded from the verdict, so a failed
 * same-SHA workflow could be returned alongside overall: "success".
 */
function mixedEvidence({ runConclusion = "success", jobConclusion = "success", checkConclusion = "success", statusState = "success" } = {}) {
  globalThis.fetch = async (url) => {
    const u = String(url);
    let body;
    if (u.includes("/check-runs")) {
      body = { check_runs: [{ id: 1, name: "ok", status: "completed", conclusion: checkConclusion, head_sha: SHA }] };
    } else if (u.includes("/actions/runs/") && u.includes("/jobs")) {
      body = { jobs: [{ id: 9, name: "job", status: "completed", conclusion: jobConclusion, steps: [{ number: 1, name: "step", conclusion: jobConclusion }] }] };
    } else if (u.includes("/actions/runs")) {
      body = { workflow_runs: [{ id: 5, name: "wf", status: "completed", conclusion: runConclusion, head_sha: SHA, run_attempt: 1 }] };
    } else {
      body = { state: statusState, sha: SHA, statuses: [{ context: "legacy", state: statusState }] };
    }
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify(body) };
  };
}

test("a failed same-SHA workflow run cannot be reported as success", async () => {
  mixedEvidence({ runConclusion: "failure", jobConclusion: "success" });
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.overall, "failure", "a failed workflow run must dominate passing check-runs and statuses");
  assert.equal(r.evidence_breakdown.workflow_runs, 1);
});

test("a failed job cannot be reported as success", async () => {
  mixedEvidence({ runConclusion: "success", jobConclusion: "failure" });
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.overall, "failure", "a failed job must dominate passing check-runs and statuses");
  assert.equal(r.evidence_breakdown.jobs, 1);
});

test("every retrieved signal is counted as evidence", async () => {
  mixedEvidence({});
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.deepEqual(r.evidence_breakdown, { check_runs: 1, commit_statuses: 1, workflow_runs: 1, jobs: 1 });
  assert.equal(r.evidence_count, 4, "retrieved-but-uncounted evidence is how a false green happens");
  assert.equal(r.overall, "success");
});

test("a pending workflow run holds the verdict at pending", async () => {
  mixedEvidence({ runConclusion: null });
  globalThis.fetch = (function (inner) {
    return async (url) => {
      const res = await inner(url);
      if (String(url).includes("/actions/runs") && !String(url).includes("/jobs")) {
        return { ...res, text: async () => JSON.stringify({ workflow_runs: [{ id: 5, name: "wf", status: "in_progress", conclusion: null, head_sha: SHA, run_attempt: 1 }] }) };
      }
      return res;
    };
  })(globalThis.fetch);
  const r = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(r.overall, "pending");
});
