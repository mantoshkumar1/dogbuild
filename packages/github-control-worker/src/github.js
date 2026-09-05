/**
 * Bounded GitHub REST/GraphQL access with complete pagination and a
 * deterministic error taxonomy. Never logs credentials, headers or bodies.
 */
import { ControlError, ErrorClass, classifyHttpStatus } from "./errors.js";

export const GITHUB_API = "https://api.github.com";
export const MAX_PAGES = 20;
export const REQUEST_TIMEOUT_MS = 15000;

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "dogbuild-github-control-worker",
  };
}

async function rawFetch(url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if (err && (err.name === "AbortError" || err.name === "TimeoutError")) {
      throw new ControlError(ErrorClass.TIMEOUT, "Upstream request timed out.");
    }
    throw new ControlError(ErrorClass.UPSTREAM_ERROR, "Upstream request failed.");
  } finally {
    clearTimeout(timer);
  }
}

export async function gh(env, path, init = {}) {
  const res = await rawFetch(`${GITHUB_API}${path}`, {
    ...init,
    headers: { ...authHeaders(env.GITHUB_TOKEN), ...(init.headers || {}) },
  }, REQUEST_TIMEOUT_MS);
  const text = await res.text();
  if (!res.ok) {
    throw new ControlError(classifyHttpStatus(res.status, res.headers), `GitHub responded ${res.status}.`, {
      status: res.status,
    });
  }
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "Upstream returned a body that is not valid JSON.");
  }
}

function nextLink(linkHeader) {
  if (!linkHeader) return null;
  for (const part of linkHeader.split(",")) {
    const m = part.match(/<([^>]+)>\s*;\s*rel="next"/);
    if (m) return m[1];
  }
  return null;
}

/**
 * Follow rel="next" to completion. Returns { items, incomplete, pages }.
 * `incomplete: true` means the caller must NOT treat the result as a
 * complete view (invariant 3) — it never silently truncates.
 */
export async function ghPaginate(env, path, { itemsKey = null } = {}) {
  let url = `${GITHUB_API}${path}`;
  const items = [];
  let pages = 0;
  let incomplete = false;

  while (url) {
    if (pages >= MAX_PAGES) {
      incomplete = true;
      break;
    }
    const res = await rawFetch(url, { headers: authHeaders(env.GITHUB_TOKEN) }, REQUEST_TIMEOUT_MS);
    const text = await res.text();
    if (!res.ok) {
      throw new ControlError(classifyHttpStatus(res.status, res.headers), `GitHub responded ${res.status}.`, {
        status: res.status,
      });
    }
    let body;
    try {
      body = JSON.parse(text || "null");
    } catch {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "Upstream returned a body that is not valid JSON.");
    }
    const page = itemsKey ? body && body[itemsKey] : body;
    if (page === undefined || page === null) {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "Upstream response is missing the expected collection.");
    }
    if (!Array.isArray(page)) {
      throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "Upstream collection is not an array.");
    }
    items.push(...page);
    pages += 1;
    url = nextLink(res.headers && typeof res.headers.get === "function" ? res.headers.get("link") : null);
  }
  return { items, incomplete, pages };
}

export async function ghGraphql(env, query, variables, tokenOverride) {
  const res = await rawFetch(`${GITHUB_API}/graphql`, {
    method: "POST",
    headers: {
      ...authHeaders(tokenOverride || env.GITHUB_TOKEN),
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  }, REQUEST_TIMEOUT_MS);
  const text = await res.text();
  if (!res.ok) {
    throw new ControlError(classifyHttpStatus(res.status, res.headers), `GitHub GraphQL responded ${res.status}.`, {
      status: res.status,
    });
  }
  let json;
  try {
    json = JSON.parse(text);
  } catch {
    throw new ControlError(ErrorClass.UPSTREAM_MALFORMED, "GraphQL response is not valid JSON.");
  }
  if (json.errors) {
    throw new ControlError(ErrorClass.UPSTREAM_ERROR, "GitHub GraphQL returned an error response.");
  }
  return json.data;
}

export const SHA_RE = /^[0-9a-f]{40}$/;

export function assertExactSha(sha) {
  if (typeof sha !== "string" || !SHA_RE.test(sha)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "sha must be exactly 40 lowercase hexadecimal characters.");
  }
  return sha;
}

export async function sha256Hex(str) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
