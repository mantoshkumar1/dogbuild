import { ControlError, ErrorClass } from "./errors.js";
import { assertExactSha, gh, ghPaginate } from "./github.js";

export const CiResult = Object.freeze({
  SUCCESS: "SUCCESS",
  FAILURE: "FAILURE",
  PENDING: "PENDING",
  NO_CHECKS: "NO_CHECKS",
  INCOMPLETE: "INCOMPLETE",
});

const Signal = Object.freeze({ PASS: "PASS", FAIL: "FAIL", PENDING: "PENDING", UNKNOWN: "UNKNOWN" });
const MAX_RETURNED_PER_TYPE = 100;
export const MAX_WORKFLOW_RUNS_WITH_JOBS = 10;

export function normalizeCheckLike(record) {
  const status = String(record && record.status || "").toLowerCase();
  if (["queued", "in_progress", "waiting", "pending", "requested"].includes(status)) {
    return Signal.PENDING;
  }
  if (status !== "completed") return Signal.UNKNOWN;

  switch (String(record && record.conclusion || "").toLowerCase()) {
    case "success":
    case "neutral":
    case "skipped":
      return Signal.PASS;
    case "failure":
    case "timed_out":
    case "action_required":
    case "startup_failure":
    case "cancelled":
    case "stale":
      return Signal.FAIL;
    default:
      return Signal.UNKNOWN;
  }
}

export function normalizeCommitStatus(record) {
  if (!record || typeof record.context !== "string" || !record.context.trim()) return Signal.UNKNOWN;
  switch (String(record && record.state || "").toLowerCase()) {
    case "success": return Signal.PASS;
    case "failure":
    case "error": return Signal.FAIL;
    case "pending": return Signal.PENDING;
    default: return Signal.UNKNOWN;
  }
}

export function foldCiResult(signals, incomplete = false) {
  if (incomplete || signals.includes(Signal.UNKNOWN)) return CiResult.INCOMPLETE;
  if (!signals.length) return CiResult.NO_CHECKS;
  if (signals.includes(Signal.FAIL)) return CiResult.FAILURE;
  if (signals.includes(Signal.PENDING)) return CiResult.PENDING;
  return CiResult.SUCCESS;
}

function assertRecordsBoundToSha(records, sha, label) {
  for (const record of records) {
    const found = record && (record.head_sha || record.sha);
    if (typeof found !== "string") {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, `${label} evidence has no commit SHA.`);
    }
    if (found !== sha) {
      throw new ControlError(ErrorClass.HEAD_MISMATCH, `${label} evidence belongs to another commit.`, {
        requested_sha: sha,
        found_sha: found,
      });
    }
  }
}

/** GitHub returns commit statuses newest first; keep only the latest per context. */
export function latestStatusesByContext(statuses) {
  const latest = new Map();
  for (const status of statuses) {
    const context = typeof status.context === "string" ? status.context.trim() : "";
    const key = context.toLowerCase();
    if (!key) {
      latest.set(`__missing_context_${latest.size}`, status);
    } else if (!latest.has(key)) {
      latest.set(key, status);
    }
  }
  return [...latest.values()];
}

function sourceSummary(page) {
  return {
    count: page.items.length,
    pages: page.pages,
    incomplete: page.incomplete,
    advertised_total: page.advertised_total,
  };
}

function limited(items, project) {
  return items.slice(0, MAX_RETURNED_PER_TYPE).map(project);
}

export async function getCommitCi(env, { owner, repo, sha }) {
  assertExactSha(sha);
  const base = `/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  const commit = await gh(env, `${base}/commits/${sha}`);
  if (!commit || typeof commit.sha !== "string") {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub commit response has no SHA.");
  }
  if (commit.sha !== sha) {
    throw new ControlError(ErrorClass.HEAD_MISMATCH, "GitHub returned a different commit than requested.", {
      requested_sha: sha,
      found_sha: commit.sha,
    });
  }

  const checks = await ghPaginate(
    env,
    `${base}/commits/${sha}/check-runs?filter=latest&per_page=100`,
    { itemsKey: "check_runs" }
  );
  assertRecordsBoundToSha(checks.items, sha, "check-run");

  const runs = await ghPaginate(
    env,
    `${base}/actions/runs?head_sha=${sha}&per_page=100`,
    { itemsKey: "workflow_runs" }
  );
  assertRecordsBoundToSha(runs.items, sha, "workflow-run");

  const jobs = [];
  let jobsPages = 0;
  let jobsIncomplete = runs.items.length > MAX_WORKFLOW_RUNS_WITH_JOBS;
  for (const run of runs.items.slice(0, MAX_WORKFLOW_RUNS_WITH_JOBS)) {
    if (!Number.isSafeInteger(run.id) || run.id < 1) {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "Workflow-run evidence has no valid numeric id.");
    }
    const page = await ghPaginate(
      env,
      `${base}/actions/runs/${encodeURIComponent(String(run.id))}/jobs?filter=all&per_page=100`,
      { itemsKey: "jobs" }
    );
    jobsPages += page.pages;
    jobsIncomplete = jobsIncomplete || page.incomplete;
    for (const job of page.items) jobs.push({ ...job, workflow_run_id: run.id });
  }

  const allStatuses = await ghPaginate(env, `${base}/commits/${sha}/statuses?per_page=100`);
  const statuses = latestStatusesByContext(allStatuses.items);

  const checkSignals = checks.items.map(normalizeCheckLike);
  const runSignals = runs.items.map(normalizeCheckLike);
  const jobSignals = jobs.map(normalizeCheckLike);
  const statusSignals = statuses.map(normalizeCommitStatus);
  const signals = [...checkSignals, ...runSignals, ...jobSignals, ...statusSignals];
  const paginationIncomplete = checks.incomplete || runs.incomplete || jobsIncomplete || allStatuses.incomplete;
  const unknownSignals = signals.filter((signal) => signal === Signal.UNKNOWN).length;
  const overall = foldCiResult(signals, paginationIncomplete);

  const evidenceTruncated = [checks.items, runs.items, jobs, statuses]
    .some((items) => items.length > MAX_RETURNED_PER_TYPE);

  return {
    repository: `${owner}/${repo}`,
    sha,
    overall,
    complete: !paginationIncomplete && unknownSignals === 0,
    evidence_count: signals.length,
    evidence_breakdown: {
      check_runs: checkSignals.length,
      workflow_runs: runSignals.length,
      jobs: jobSignals.length,
      commit_statuses: statusSignals.length,
    },
    incomplete_reasons: [
      ...(checks.incomplete ? ["check_runs_pagination"] : []),
      ...(runs.incomplete ? ["workflow_runs_pagination"] : []),
      ...(jobsIncomplete ? ["jobs_pagination"] : []),
      ...(allStatuses.incomplete ? ["commit_statuses_pagination"] : []),
      ...(unknownSignals ? ["unrecognized_evidence_state"] : []),
    ],
    evidence_truncated: evidenceTruncated,
    sources: {
      commit: { verified: true, html_url: commit.html_url || null },
      check_runs: sourceSummary(checks),
      workflow_runs: sourceSummary(runs),
      jobs: { count: jobs.length, pages: jobsPages, incomplete: jobsIncomplete },
      commit_statuses: {
        fetched_count: allStatuses.items.length,
        latest_context_count: statuses.length,
        pages: allStatuses.pages,
        incomplete: allStatuses.incomplete,
      },
    },
    check_runs: limited(checks.items, (item) => ({
      id: item.id,
      name: item.name,
      status: item.status,
      conclusion: item.conclusion,
      html_url: item.html_url || null,
    })),
    workflow_runs: limited(runs.items, (item) => ({
      id: item.id,
      name: item.name,
      event: item.event,
      status: item.status,
      conclusion: item.conclusion,
      run_attempt: item.run_attempt,
      html_url: item.html_url || null,
    })),
    jobs: limited(jobs, (item) => ({
      workflow_run_id: item.workflow_run_id,
      id: item.id,
      name: item.name,
      status: item.status,
      conclusion: item.conclusion,
      html_url: item.html_url || null,
    })),
    commit_statuses: limited(statuses, (item) => ({
      id: item.id,
      context: item.context,
      state: item.state,
      target_url: item.target_url || null,
    })),
  };
}
