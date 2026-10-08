import { ControlError, ErrorClass, classifyHttpStatus } from "./errors.js";

export const GITHUB_API = "https://api.github.com";
// Keep one invocation bounded. get_commit_ci makes one commit request, up to
// three pages for each top-level source, and at most ten job collections of up
// to three pages.
export const MAX_PAGES = 3;
export const REQUEST_TIMEOUT_MS = 15_000;
export const SHA_RE = /^[0-9a-f]{40}$/;

function assertToken(env) {
  if (!env || typeof env.GITHUB_TOKEN !== "string" || !env.GITHUB_TOKEN.trim()) {
    throw new ControlError(ErrorClass.CONFIG_INVALID, "GitHub credential is not configured.");
  }
  return env.GITHUB_TOKEN;
}

function authHeaders(env) {
  return {
    Authorization: `Bearer ${assertToken(env)}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "dogbuild-control-mcp",
  };
}

function githubUrl(pathOrUrl) {
  let url;
  try {
    url = pathOrUrl.startsWith("/")
      ? new URL(pathOrUrl, GITHUB_API)
      : new URL(pathOrUrl);
  } catch {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub pagination returned an invalid URL.");
  }
  if (url.origin !== GITHUB_API) {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub pagination left the approved API origin.");
  }
  return url.toString();
}

async function rawFetch(url, init, timeoutMs = REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error && (error.name === "AbortError" || error.name === "TimeoutError")) {
      throw new ControlError(ErrorClass.TIMEOUT, "GitHub request timed out.");
    }
    throw new ControlError(ErrorClass.UPSTREAM_ERROR, "GitHub request failed.");
  } finally {
    clearTimeout(timer);
  }
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!response.ok) {
    throw new ControlError(
      classifyHttpStatus(response.status, response.headers),
      `GitHub responded ${response.status}.`,
      { status: response.status }
    );
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub returned malformed JSON.");
  }
}

function nextLink(linkHeader, expectedPathname) {
  if (!linkHeader) return null;
  for (const part of linkHeader.split(",")) {
    const match = part.match(/<([^>]+)>\s*;\s*rel="next"/);
    if (match) {
      const next = githubUrl(match[1]);
      if (new URL(next).pathname !== expectedPathname) {
        throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub pagination changed collection path.");
      }
      return next;
    }
  }
  return null;
}

export async function gh(env, path) {
  const response = await rawFetch(githubUrl(path), { headers: authHeaders(env) });
  return readJsonResponse(response);
}

/**
 * Follow GitHub's rel="next" links to completion. If GitHub advertises more
 * data than was returned, or the hard page cap is reached, `incomplete` is
 * true and callers must not report a successful aggregate.
 */
export async function ghPaginate(env, path, { itemsKey = null } = {}) {
  let url = githubUrl(path);
  const expectedPathname = new URL(url).pathname;
  let pages = 0;
  let incomplete = false;
  let advertisedTotal = null;
  const items = [];

  while (url) {
    if (pages >= MAX_PAGES) {
      incomplete = true;
      break;
    }
    const response = await rawFetch(url, { headers: authHeaders(env) });
    const body = await readJsonResponse(response);
    const page = itemsKey ? body && body[itemsKey] : body;
    if (!Array.isArray(page)) {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub response is missing the expected collection.");
    }
    if (itemsKey && Number.isInteger(body.total_count) && body.total_count >= 0) {
      advertisedTotal = advertisedTotal === null
        ? body.total_count
        : Math.max(advertisedTotal, body.total_count);
    }
    items.push(...page);
    pages += 1;
    url = nextLink(response.headers && typeof response.headers.get === "function"
      ? response.headers.get("link")
      : null, expectedPathname);
  }

  if (advertisedTotal !== null && items.length < advertisedTotal) incomplete = true;
  return { items, pages, incomplete, advertised_total: advertisedTotal };
}

export function assertExactSha(sha) {
  if (typeof sha !== "string" || !SHA_RE.test(sha)) {
    throw new ControlError(
      ErrorClass.INVALID_INPUT,
      "sha must be exactly 40 lowercase hexadecimal characters."
    );
  }
  return sha;
}

// ---------------------------------------------------------------------------
// Bounded, read-only GET helper used by get_raw_commit only. Additive: none of
// the helpers above changes behavior.
// ---------------------------------------------------------------------------
export const RAW_MAX_GETS = 3;
export const RAW_MAX_RESPONSE_BYTES = 2_097_152;
export const RAW_TOTAL_DEADLINE_MS = 45_000;
const JSON_CONTENT_TYPE_RE = /^application\/(?:[a-z0-9.+-]*\+)?json\s*(?:;|$)/i;

export function newBoundedSession() {
  return { startedAt: Date.now(), gets: 0 };
}

export function assertWithinDeadline(session) {
  if (Date.now() - session.startedAt >= RAW_TOTAL_DEADLINE_MS) {
    throw new ControlError(ErrorClass.TIMEOUT, "GitHub request timed out.", { reason: "TOTAL_DEADLINE_EXCEEDED" });
  }
}

function cancelQuietly(target) {
  try {
    const promise = target && typeof target.cancel === "function" ? target.cancel() : null;
    if (promise && typeof promise.catch === "function") promise.catch(() => {});
  } catch {
    // best effort only
  }
}

function concatChunks(chunks, total) {
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

/**
 * One GET with manual redirect handling, stream-bounded decoded bytes and a
 * shared deadline. Resolves to { json } or { incomplete: "RESPONSE_TOO_LARGE" }.
 * Non-2xx responses are classified by status without reading their body.
 */
export async function boundedGet(env, path, session) {
  const headers = authHeaders(env);
  const requestUrl = githubUrl(path);
  assertWithinDeadline(session);
  session.gets += 1;
  if (session.gets > RAW_MAX_GETS) {
    throw new ControlError(ErrorClass.UPSTREAM_ERROR, "Internal error.", { reason: "GET_BUDGET_EXCEEDED" });
  }

  const remaining = RAW_TOTAL_DEADLINE_MS - (Date.now() - session.startedAt);
  const useTotal = remaining <= REQUEST_TIMEOUT_MS;
  const limit = useTotal ? remaining : REQUEST_TIMEOUT_MS;
  const timeoutError = () => new ControlError(ErrorClass.TIMEOUT, "GitHub request timed out.", {
    reason: useTotal ? "TOTAL_DEADLINE_EXCEEDED" : "REQUEST_TIMEOUT",
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), limit);
  const aborted = new Promise((_, reject) => {
    controller.signal.addEventListener("abort", () => reject(timeoutError()), { once: true });
  });
  aborted.catch(() => {});

  let reader = null;
  let finished = false;
  let response = null;
  try {
    try {
      response = await Promise.race([
        fetch(requestUrl, { method: "GET", headers, redirect: "manual", signal: controller.signal }),
        aborted,
      ]);
    } catch (error) {
      if (error instanceof ControlError) throw error;
      if (error && (error.name === "AbortError" || error.name === "TimeoutError")) throw timeoutError();
      throw new ControlError(ErrorClass.UPSTREAM_ERROR, "GitHub request failed.");
    }

    const fail = (errorClass, message, details) => {
      cancelQuietly(response && response.body);
      finished = true;
      throw new ControlError(errorClass, message, details);
    };
    const status = response.status;
    if ((status >= 300 && status < 400) || response.type === "opaqueredirect") {
      fail(ErrorClass.UPSTREAM_MALFORMED, "GitHub redirected the request.", { reason: "REDIRECT_DENIED" });
    }
    if (!(status >= 200 && status < 300)) {
      fail(classifyHttpStatus(status, response.headers), `GitHub responded ${status}.`, { status });
    }
    const hdr = (name) => (response.headers && typeof response.headers.get === "function"
      ? response.headers.get(name)
      : null);
    if (hdr("link")) {
      fail(ErrorClass.UPSTREAM_MALFORMED, "GitHub returned unexpected pagination.", { reason: "UNEXPECTED_PAGINATION" });
    }
    if (typeof response.url === "string" && response.url) {
      let same = false;
      try {
        const got = new URL(response.url);
        const want = new URL(requestUrl);
        same = got.origin === want.origin && got.pathname === want.pathname && got.search === want.search;
      } catch {
        same = false;
      }
      if (!same) {
        fail(ErrorClass.UPSTREAM_MALFORMED, "GitHub response URL did not match the request.", { reason: "RESPONSE_URL_MISMATCH" });
      }
    }
    const contentType = hdr("content-type");
    if (typeof contentType !== "string" || !JSON_CONTENT_TYPE_RE.test(contentType)) {
      fail(ErrorClass.UPSTREAM_MALFORMED, "GitHub returned a non-JSON response.", { reason: "CONTENT_TYPE_NOT_JSON" });
    }
    const advertised = Number(hdr("content-length"));
    if (hdr("content-length") !== null && Number.isFinite(advertised) && advertised > RAW_MAX_RESPONSE_BYTES) {
      cancelQuietly(response.body);
      finished = true;
      return { incomplete: "RESPONSE_TOO_LARGE" };
    }

    const chunks = [];
    let total = 0;
    if (response.body && typeof response.body.getReader === "function") {
      reader = response.body.getReader();
      for (;;) {
        let step;
        try {
          step = await Promise.race([reader.read(), aborted]);
        } catch (error) {
          if (error instanceof ControlError) throw error;
          throw new ControlError(ErrorClass.UPSTREAM_ERROR, "GitHub request failed.");
        }
        if (step.done) break;
        const chunk = step.value;
        total += chunk.byteLength;
        if (total > RAW_MAX_RESPONSE_BYTES) {
          cancelQuietly(reader);
          finished = true;
          return { incomplete: "RESPONSE_TOO_LARGE" };
        }
        chunks.push(chunk);
      }
      finished = true;
    } else {
      finished = true;
    }

    let text;
    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(concatChunks(chunks, total));
    } catch {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub returned malformed JSON.", { reason: "MALFORMED_JSON" });
    }
    try {
      return { json: JSON.parse(text) };
    } catch {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GitHub returned malformed JSON.", { reason: "MALFORMED_JSON" });
    }
  } finally {
    if (!finished && reader) cancelQuietly(reader);
    clearTimeout(timer);
  }
}
