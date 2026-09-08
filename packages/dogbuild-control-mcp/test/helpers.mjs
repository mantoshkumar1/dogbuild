export const SHA = "a".repeat(40);
export const OTHER_SHA = "b".repeat(40);
export const ENV = Object.freeze({
  GITHUB_TOKEN: "TEST_GITHUB_TOKEN_NOT_REAL",
  ALLOWED_REPOS: "mantoshkumar1/pingstep,mantoshkumar1/dogbuild",
  MCP_PATH_SECRET: "test-path-secret-0123456789abcdef",
  MCP_ACCESS_TOKEN: "TEST_MCP_ACCESS_TOKEN_NOT_REAL_0123456789abcdef",
});

const BASE = "/repos/mantoshkumar1/pingstep";

function headersObject(values = {}) {
  const normalized = new Map(
    Object.entries(values).map(([key, value]) => [key.toLowerCase(), value])
  );
  return { get: (name) => normalized.get(String(name).toLowerCase()) ?? null };
}

export function mockFetch(routes = {}, { unmatched = "throw" } = {}) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const method = String(init.method || "GET").toUpperCase();
    const key = `${method} ${parsed.pathname}`;
    calls.push({ method, url: parsed.toString(), pathname: parsed.pathname, search: parsed.search, headers: init.headers || {} });

    let route = routes[key];
    if (typeof route === "function") route = await route({ parsed, method, calls });
    if (!route && unmatched === "throw") throw new Error(`unmatched request: ${key}${parsed.search}`);
    route ||= { body: {} };

    const status = route.status || 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: headersObject(route.headers),
      text: async () => route.text !== undefined ? route.text : JSON.stringify(route.body ?? null),
    };
  };
  return calls;
}

export function ciRoutes({
  commit = { sha: SHA, html_url: `https://github.com/mantoshkumar1/pingstep/commit/${SHA}` },
  checks = [],
  runs = [],
  jobs = [],
  statuses = [],
} = {}) {
  return {
    [`GET ${BASE}/commits/${SHA}`]: { body: commit },
    [`GET ${BASE}/commits/${SHA}/check-runs`]: { body: { total_count: checks.length, check_runs: checks } },
    [`GET ${BASE}/actions/runs`]: { body: { total_count: runs.length, workflow_runs: runs } },
    [`GET ${BASE}/actions/runs/1/jobs`]: { body: { total_count: jobs.length, jobs } },
    [`GET ${BASE}/commits/${SHA}/statuses`]: { body: statuses },
  };
}

export function checkRun(overrides = {}) {
  return {
    id: 1,
    name: "test",
    status: "completed",
    conclusion: "success",
    head_sha: SHA,
    html_url: "https://github.com/example/check/1",
    ...overrides,
  };
}

export function workflowRun(overrides = {}) {
  return {
    id: 1,
    name: "ci",
    event: "pull_request",
    status: "completed",
    conclusion: "success",
    head_sha: SHA,
    run_attempt: 1,
    html_url: "https://github.com/example/run/1",
    ...overrides,
  };
}

export function job(overrides = {}) {
  return {
    id: 10,
    name: "tests",
    status: "completed",
    conclusion: "success",
    html_url: "https://github.com/example/job/10",
    ...overrides,
  };
}

export function commitStatus(overrides = {}) {
  return {
    id: 100,
    context: "ci/test",
    state: "success",
    target_url: "https://github.com/example/status/100",
    ...overrides,
  };
}

export async function rpc(method, params, { env = ENV, path = ENV.MCP_PATH_SECRET, token = ENV.MCP_ACCESS_TOKEN } = {}) {
  const { default: worker } = await import("../src/index.js");
  return worker.fetch(new Request(`https://control.example/mcp/${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  }), env);
}
