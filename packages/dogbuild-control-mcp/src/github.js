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
