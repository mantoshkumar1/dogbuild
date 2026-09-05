/** Shared offline test scaffolding. No network, no credentials, no browser. */
export const ENV = {
  GITHUB_TOKEN: "TEST_TOKEN_NOT_REAL",
  ALLOWED_REPOS: "mantoshkumar1/pingstep,mantoshkumar1/dogbuild",
  ROLE_ASSERTION_KEY: "test-signing-key",
  MCP_PATH_SECRET: "test-path-secret",
};
export const SHA = "a".repeat(40);
export const OTHER_SHA = "b".repeat(40);

/**
 * Install a mock fetch. `routes` maps "METHOD /path" (or a path prefix) to
 * { status?, body?, headers?, text? }. Every request is recorded.
 */
export function mockFetch(routes = {}, { onUnmatched = "empty" } = {}) {
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    const method = (init.method || "GET").toUpperCase();
    const full = String(url);
    const path = full.replace("https://api.github.com", "");
    let body = null;
    try {
      body = init.body ? JSON.parse(init.body) : null;
    } catch {
      body = init.body;
    }
    calls.push({ method, path, url: full, body, headers: init.headers || {} });

    const key = Object.keys(routes).find((k) => {
      const [m, p] = k.split(" ");
      return m === method && (path === p || full === p || path.startsWith(p));
    });
    const route = key ? routes[key] : null;
    if (!route && onUnmatched === "throw") throw new Error(`unmatched ${method} ${path}`);
    const status = route && route.status ? route.status : 200;
    const payload = route && route.body !== undefined ? route.body : {};
    const headers = new Map(Object.entries((route && route.headers) || {}));
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: { get: (h) => headers.get(String(h).toLowerCase()) ?? null },
      text: async () => (route && typeof route.text === "string" ? route.text : JSON.stringify(payload)),
    };
  };
  return calls;
}

export function checkRun(overrides = {}) {
  return { id: 1, name: "check", status: "completed", conclusion: "success", head_sha: SHA, ...overrides };
}
