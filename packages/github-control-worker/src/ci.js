/**
 * get_commit_ci — one normalized, exact-SHA CI verdict (DogBuild #164
 * invariants 2, 3, 4).
 *
 * Rules that matter more than the code:
 *   - the caller supplies one exact 40-character SHA;
 *   - every returned record is verified to belong to that SHA;
 *   - pagination is complete or the result is explicitly `incomplete`;
 *   - absent, incomplete or ambiguous evidence is `unknown`, never `success`.
 */
import { ControlError, ErrorClass } from "./errors.js";
import { assertExactSha, gh, ghPaginate } from "./github.js";

export const OverallState = ["pending", "success", "failure", "neutral", "unknown"];

export function normalizeCheckRun(run) {
  const status = String(run.status || "").toLowerCase();
  if (status === "queued" || status === "in_progress" || status === "waiting" || status === "pending" || status === "requested") {
    return "pending";
  }
  if (status !== "completed") return "unknown";
  switch (String(run.conclusion || "").toLowerCase()) {
    case "success":
      return "success";
    case "failure":
    case "timed_out":
    case "action_required":
    case "startup_failure":
      return "failure";
    case "neutral":
    case "skipped":
    case "cancelled":
    case "stale":
      return "neutral";
    default:
      return "unknown";
  }
}

export function normalizeCommitStatus(state) {
  switch (String(state || "").toLowerCase()) {
    case "success":
      return "success";
    case "failure":
    case "error":
      return "failure";
    case "pending":
      return "pending";
    default:
      return "unknown";
  }
}

/**
 * Fold individual normalized states into one overall verdict.
 * Precedence: incomplete/unknown-evidence > failure > pending > success > neutral.
 * No evidence at all is `unknown` — never green by absence.
 */
export function foldOverall(states, incomplete) {
  if (incomplete) return "unknown";
  if (!states.length) return "unknown";
  if (states.includes("unknown")) return "unknown";
  if (states.includes("failure")) return "failure";
  if (states.includes("pending")) return "pending";
  if (states.includes("success")) return "success";
  return "neutral";
}

function assertBoundToSha(records, sha, label) {
  for (const r of records) {
    const recordSha = r.head_sha || r.sha;
    if (recordSha && recordSha !== sha) {
      throw new ControlError(
        ErrorClass.HEAD_MISMATCH,
        `${label} evidence is bound to a different commit than the one requested.`,
        { requested_sha: sha, found_sha: recordSha }
      );
    }
  }
}

export async function getCommitCi(env, { owner, repo, sha }) {
  assertExactSha(sha);
  const base = `/repos/${owner}/${repo}`;
  let incomplete = false;

  const checks = await ghPaginate(env, `${base}/commits/${sha}/check-runs?per_page=100`, { itemsKey: "check_runs" });
  incomplete = incomplete || checks.incomplete;
  assertBoundToSha(checks.items, sha, "check-run");

  const runs = await ghPaginate(env, `${base}/actions/runs?head_sha=${sha}&per_page=100`, { itemsKey: "workflow_runs" });
  incomplete = incomplete || runs.incomplete;
  assertBoundToSha(runs.items, sha, "workflow-run");

  const jobs = [];
  for (const run of runs.items) {
    const page = await ghPaginate(env, `${base}/actions/runs/${run.id}/jobs?per_page=100`, { itemsKey: "jobs" });
    incomplete = incomplete || page.incomplete;
    for (const j of page.items) {
      jobs.push({
        run_id: run.id,
        run_attempt: run.run_attempt,
        job_id: j.id,
        name: j.name,
        status: j.status,
        conclusion: j.conclusion,
        normalized: normalizeCheckRun(j),
        started_at: j.started_at,
        completed_at: j.completed_at,
        html_url: j.html_url,
        failed_steps: (j.steps || [])
          .filter((s) => s.conclusion && s.conclusion !== "success" && s.conclusion !== "skipped")
          .map((s) => ({ number: s.number, name: s.name, conclusion: s.conclusion })),
      });
    }
  }

  const combined = await gh(env, `${base}/commits/${sha}/status?per_page=100`);
  if (combined && combined.sha && combined.sha !== sha) {
    throw new ControlError(ErrorClass.HEAD_MISMATCH, "Combined status is bound to a different commit than requested.", {
      requested_sha: sha,
      found_sha: combined.sha,
    });
  }

  const checkStates = checks.items.map(normalizeCheckRun);
  const statusStates = (combined && Array.isArray(combined.statuses) ? combined.statuses : []).map((s) =>
    normalizeCommitStatus(s.state)
  );
  const overall = foldOverall([...checkStates, ...statusStates], incomplete);

  return {
    sha,
    overall,
    incomplete,
    evidence_count: checkStates.length + statusStates.length,
    check_runs: checks.items.map((c) => ({
      id: c.id,
      name: c.name,
      status: c.status,
      conclusion: c.conclusion,
      normalized: normalizeCheckRun(c),
      started_at: c.started_at,
      completed_at: c.completed_at,
      html_url: c.html_url,
    })),
    workflow_runs: runs.items.map((r) => ({
      id: r.id,
      name: r.name,
      event: r.event,
      status: r.status,
      conclusion: r.conclusion,
      run_attempt: r.run_attempt,
      html_url: r.html_url,
    })),
    jobs,
    combined_status: {
      state: combined ? combined.state : null,
      normalized: combined ? normalizeCommitStatus(combined.state) : "unknown",
      statuses: (combined && combined.statuses ? combined.statuses : []).map((s) => ({
        context: s.context,
        state: s.state,
        normalized: normalizeCommitStatus(s.state),
        target_url: s.target_url,
      })),
    },
  };
}
