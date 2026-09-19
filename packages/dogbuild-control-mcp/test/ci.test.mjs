import { test } from "node:test";
import assert from "node:assert/strict";
import {
  CiResult,
  MAX_WORKFLOW_RUNS_WITH_JOBS,
  foldCiResult,
  getCommitCi,
  latestStatusesByContext,
  normalizeCheckLike,
  normalizeCommitStatus,
} from "../src/ci.js";
import { ErrorClass } from "../src/errors.js";
import { MAX_PAGES } from "../src/github.js";
import {
  ENV,
  OTHER_SHA,
  SHA,
  checkRun,
  ciRoutes,
  commitStatus,
  job,
  mockFetch,
  workflowRun,
} from "./helpers.mjs";

const BASE = "/repos/mantoshkumar1/pingstep";

test("invalid or abbreviated SHAs are rejected before GitHub access", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const sha of ["main", "abc", SHA.toUpperCase(), "z".repeat(40), 42, null]) {
    await assert.rejects(
      getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha }),
      (error) => error.class === ErrorClass.INVALID_INPUT
    );
  }
  assert.equal(calls.length, 0);
});

test("the exact commit must exist before CI evidence is read", async () => {
  const calls = mockFetch({
    [`GET ${BASE}/commits/${SHA}`]: { status: 404, body: { message: "Not Found" } },
  });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.NOT_FOUND
  );
  assert.equal(calls.length, 1);
});

test("a mismatched commit response fails closed", async () => {
  mockFetch(ciRoutes({ commit: { sha: OTHER_SHA } }));
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.HEAD_MISMATCH
  );
});

test("no evidence is NO_CHECKS and never success", async () => {
  mockFetch(ciRoutes());
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.NO_CHECKS);
  assert.equal(value.complete, true);
  assert.equal(value.evidence_count, 0);
});

test("one successful exact-SHA check is SUCCESS", async () => {
  mockFetch(ciRoutes({ checks: [checkRun()] }));
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.SUCCESS);
  assert.equal(value.complete, true);
  assert.deepEqual(value.evidence_breakdown, {
    check_runs: 1,
    workflow_runs: 0,
    jobs: 0,
    commit_statuses: 0,
  });
});

test("failed evidence from every source can block success", async () => {
  const cases = [
    { checks: [checkRun({ conclusion: "failure" })] },
    { runs: [workflowRun({ conclusion: "failure" })], jobs: [job()] },
    { runs: [workflowRun()], jobs: [job({ conclusion: "failure" })] },
    { statuses: [commitStatus({ state: "failure" })] },
  ];
  for (const evidence of cases) {
    mockFetch(ciRoutes(evidence));
    const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
    assert.equal(value.overall, CiResult.FAILURE);
  }
});

test("pending evidence holds the aggregate at PENDING", async () => {
  mockFetch(ciRoutes({
    checks: [checkRun()],
    runs: [workflowRun({ status: "in_progress", conclusion: null })],
    jobs: [job()],
  }));
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.PENDING);
});

test("unknown conclusions are INCOMPLETE rather than green", async () => {
  mockFetch(ciRoutes({ checks: [checkRun({ conclusion: "future_value" })] }));
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.INCOMPLETE);
  assert.equal(value.complete, false);
  assert.deepEqual(value.incomplete_reasons, ["unrecognized_evidence_state"]);
});

test("check and workflow normalization enumerates terminal conclusions", () => {
  for (const status of ["queued", "in_progress", "waiting", "pending", "requested"]) {
    assert.equal(normalizeCheckLike({ status }), "PENDING");
  }
  for (const conclusion of ["success", "neutral", "skipped"]) {
    assert.equal(normalizeCheckLike({ status: "completed", conclusion }), "PASS");
  }
  for (const conclusion of ["failure", "timed_out", "action_required", "startup_failure", "cancelled", "stale"]) {
    assert.equal(normalizeCheckLike({ status: "completed", conclusion }), "FAIL");
  }
  assert.equal(normalizeCheckLike({ status: "completed", conclusion: "new_value" }), "UNKNOWN");
  assert.equal(normalizeCheckLike({ status: "mystery" }), "UNKNOWN");
});

test("commit status normalization is exhaustive and conservative", () => {
  assert.equal(normalizeCommitStatus({ context: "ci", state: "success" }), "PASS");
  assert.equal(normalizeCommitStatus({ context: "ci", state: "failure" }), "FAIL");
  assert.equal(normalizeCommitStatus({ context: "ci", state: "error" }), "FAIL");
  assert.equal(normalizeCommitStatus({ context: "ci", state: "pending" }), "PENDING");
  assert.equal(normalizeCommitStatus({ context: "ci", state: "new_value" }), "UNKNOWN");
  assert.equal(normalizeCommitStatus({ state: "success" }), "UNKNOWN");
});

test("aggregate precedence is incomplete, empty, failure, pending, success", () => {
  assert.equal(foldCiResult(["FAIL"], true), CiResult.INCOMPLETE);
  assert.equal(foldCiResult(["PASS", "UNKNOWN"], false), CiResult.INCOMPLETE);
  assert.equal(foldCiResult([], false), CiResult.NO_CHECKS);
  assert.equal(foldCiResult(["PASS", "FAIL", "PENDING"], false), CiResult.FAILURE);
  assert.equal(foldCiResult(["PASS", "PENDING"], false), CiResult.PENDING);
  assert.equal(foldCiResult(["PASS", "PASS"], false), CiResult.SUCCESS);
});

test("check-run pagination includes a later-page failure", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/check-runs`]: ({ parsed }) => {
      if (parsed.searchParams.get("page") === "2") {
        return { body: { total_count: 2, check_runs: [checkRun({ id: 2, name: "security", conclusion: "failure" })] } };
      }
      return {
        body: { total_count: 2, check_runs: [checkRun()] },
        headers: { link: `<https://api.github.com${BASE}/commits/${SHA}/check-runs?page=2&per_page=100>; rel="next"` },
      };
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.FAILURE);
  assert.equal(value.sources.check_runs.pages, 2);
  assert.equal(value.evidence_breakdown.check_runs, 2);
});

test("commit statuses are fully paginated and a later distinct context can fail", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/statuses`]: ({ parsed }) => {
      if (parsed.searchParams.get("page") === "2") {
        return { body: [commitStatus({ id: 2, context: "security", state: "failure" })] };
      }
      return {
        body: [commitStatus({ id: 1, context: "build", state: "success" })],
        headers: { link: `<https://api.github.com${BASE}/commits/${SHA}/statuses?page=2&per_page=100>; rel="next"` },
      };
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.FAILURE);
  assert.equal(value.sources.commit_statuses.pages, 2);
});

test("only the newest commit status per context contributes", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/statuses`]: ({ parsed }) => {
      if (parsed.searchParams.get("page") === "2") {
        return { body: [commitStatus({ id: 1, context: "BUILD", state: "failure" })] };
      }
      return {
        body: [commitStatus({ id: 2, context: "build", state: "success" })],
        headers: { link: `<https://api.github.com${BASE}/commits/${SHA}/statuses?page=2&per_page=100>; rel="next"` },
      };
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.SUCCESS);
  assert.equal(value.sources.commit_statuses.fetched_count, 2);
  assert.equal(value.sources.commit_statuses.latest_context_count, 1);
  assert.equal(value.commit_statuses[0].id, 2);
});

test("latest-status selection preserves first occurrence and flags missing contexts", () => {
  const statuses = latestStatusesByContext([
    commitStatus({ id: 3, context: "build", state: "success" }),
    commitStatus({ id: 2, context: "BUILD", state: "failure" }),
    commitStatus({ id: 1, context: "", state: "pending" }),
  ]);
  assert.deepEqual(statuses.map((status) => status.id), [3, 1]);
});

test("advertised totals larger than collected evidence produce INCOMPLETE", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/check-runs`]: {
      body: { total_count: 2, check_runs: [checkRun()] },
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.INCOMPLETE);
  assert.equal(value.sources.check_runs.incomplete, true);
});

test("a never-ending next link reaches the cap and produces INCOMPLETE", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/check-runs`]: {
      body: { check_runs: [checkRun()] },
      headers: { link: `<https://api.github.com${BASE}/commits/${SHA}/check-runs?page=99>; rel="next"` },
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.INCOMPLETE);
  assert.equal(value.sources.check_runs.pages, MAX_PAGES);
});

test("a pagination link leaving api.github.com fails closed", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/check-runs`]: {
      body: { total_count: 2, check_runs: [checkRun()] },
      headers: { link: `<https://attacker.example/steal>; rel="next"` },
    },
  });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.UPSTREAM_MALFORMED
  );
});

test("a pagination link changing collection path fails closed", async () => {
  mockFetch({
    ...ciRoutes(),
    [`GET ${BASE}/commits/${SHA}/check-runs`]: {
      body: { total_count: 2, check_runs: [checkRun()] },
      headers: { link: `<https://api.github.com${BASE}/issues?page=2>; rel="next"` },
    },
  });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.UPSTREAM_MALFORMED
  );
});

test("check-run and workflow evidence must be bound to the requested SHA", async () => {
  for (const evidence of [
    { checks: [checkRun({ head_sha: OTHER_SHA })] },
    { runs: [workflowRun({ head_sha: OTHER_SHA })], jobs: [job()] },
    { checks: [checkRun({ head_sha: undefined })] },
  ]) {
    mockFetch(ciRoutes(evidence));
    await assert.rejects(
      getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
      (error) => [ErrorClass.HEAD_MISMATCH, ErrorClass.UPSTREAM_MALFORMED].includes(error.class)
    );
  }
});

test("job pagination contributes later-page failures", async () => {
  mockFetch({
    ...ciRoutes({ runs: [workflowRun()] }),
    [`GET ${BASE}/actions/runs/1/jobs`]: ({ parsed }) => {
      if (parsed.searchParams.get("page") === "2") {
        return { body: { total_count: 2, jobs: [job({ id: 11, name: "security", conclusion: "failure" })] } };
      }
      return {
        body: { total_count: 2, jobs: [job()] },
        headers: { link: `<https://api.github.com${BASE}/actions/runs/1/jobs?page=2&per_page=100>; rel="next"` },
      };
    },
  });
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.FAILURE);
  assert.equal(value.sources.jobs.pages, 2);
});

test("job enumeration is bounded and reports INCOMPLETE instead of truncating silently", async () => {
  const runs = Array.from(
    { length: MAX_WORKFLOW_RUNS_WITH_JOBS + 1 },
    (_, index) => workflowRun({ id: index + 1, name: `workflow-${index + 1}` })
  );
  const routes = ciRoutes({ runs });
  for (let id = 1; id <= MAX_WORKFLOW_RUNS_WITH_JOBS; id += 1) {
    routes[`GET ${BASE}/actions/runs/${id}/jobs`] = { body: { total_count: 0, jobs: [] } };
  }
  const calls = mockFetch(routes);
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.INCOMPLETE);
  assert.equal(value.sources.jobs.incomplete, true);
  assert.equal(calls.filter((call) => call.pathname.endsWith("/jobs")).length, MAX_WORKFLOW_RUNS_WITH_JOBS);
});

test("a workflow run without a usable id fails closed before a job request", async () => {
  const calls = mockFetch(ciRoutes({ runs: [workflowRun({ id: null })] }));
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.UPSTREAM_MALFORMED
  );
  assert.equal(calls.filter((call) => call.pathname.endsWith("/jobs")).length, 0);
});

test("returned evidence is bounded without weakening the complete aggregate", async () => {
  const checks = Array.from({ length: 101 }, (_, index) => checkRun({ id: index + 1, name: `check-${index + 1}` }));
  mockFetch(ciRoutes({ checks }));
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.equal(value.overall, CiResult.SUCCESS);
  assert.equal(value.evidence_count, 101);
  assert.equal(value.check_runs.length, 100);
  assert.equal(value.evidence_truncated, true);
});

test("results and errors do not expose credential material", async () => {
  mockFetch(ciRoutes({ checks: [checkRun()] }));
  const value = await getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.doesNotMatch(JSON.stringify(value), /TEST_GITHUB_TOKEN_NOT_REAL/);

  mockFetch({ [`GET ${BASE}/commits/${SHA}`]: { status: 500, body: { token: ENV.GITHUB_TOKEN } } });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => {
      assert.doesNotMatch(JSON.stringify(error.toJSON()), /TEST_GITHUB_TOKEN_NOT_REAL/);
      return error.class === ErrorClass.UPSTREAM_ERROR;
    }
  );
});

test("GitHub HTTP failures have deterministic error classes", async () => {
  const cases = [
    { status: 401, expected: ErrorClass.UNAUTHORIZED },
    { status: 403, expected: ErrorClass.FORBIDDEN },
    { status: 404, expected: ErrorClass.NOT_FOUND },
    { status: 409, expected: ErrorClass.CONFLICT },
    { status: 422, expected: ErrorClass.UNPROCESSABLE },
    { status: 429, expected: ErrorClass.RATE_LIMIT },
    { status: 500, expected: ErrorClass.UPSTREAM_ERROR },
  ];
  for (const { status, expected } of cases) {
    mockFetch({ [`GET ${BASE}/commits/${SHA}`]: { status, body: { message: "bounded" } } });
    await assert.rejects(
      getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
      (error) => error.class === expected,
      String(status)
    );
  }

  mockFetch({
    [`GET ${BASE}/commits/${SHA}`]: {
      status: 403,
      headers: { "x-ratelimit-remaining": "0" },
      body: { message: "rate limited" },
    },
  });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.RATE_LIMIT
  );
});

test("malformed JSON and network failures have deterministic classes", async () => {
  mockFetch({ [`GET ${BASE}/commits/${SHA}`]: { text: "not-json" } });
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.UPSTREAM_MALFORMED
  );

  globalThis.fetch = async () => {
    const error = new Error("network details that must not escape");
    error.name = "NetworkError";
    throw error;
  };
  await assert.rejects(
    getCommitCi(ENV, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.UPSTREAM_ERROR && !error.message.includes("network details")
  );
});

test("missing GitHub credentials fail before a network request", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  await assert.rejects(
    getCommitCi({ ...ENV, GITHUB_TOKEN: "" }, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
    (error) => error.class === ErrorClass.CONFIG_INVALID
  );
  assert.equal(calls.length, 0);
});
