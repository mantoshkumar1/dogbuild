/**
 * Server-enforced, request-scoped roles (DogBuild #164, founder amendment
 * 5552747159).
 *
 * The caller can neither choose nor widen its role:
 *   - a `role` argument inside a tool call is ignored, always;
 *   - the role comes from a DogBuild-signed, request-bound assertion;
 *   - an unsigned request gets read-only common capabilities and nothing else;
 *   - a reviewer assertion whose producer equals its subject is rejected, so
 *     an agent cannot review its own lineage.
 *
 * Signed assertion format (compact, HMAC-SHA256):
 *   base64url(JSON payload) + "." + base64url(signature)
 * Payload fields: role, task, repo, branch?, subject, producer?, exp (ms), nonce.
 */
import { ControlError, ErrorClass } from "./errors.js";

export const ROLES = ["read", "implementor", "reviewer"];
export const ROLE_ASSERTION_HEADER = "x-dogbuild-role-assertion";
export const MAX_ASSERTION_LIFETIME_MS = 60 * 60 * 1000;

function b64urlToString(str) {
  let s = String(str).replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return atob(s);
}
function b64urlEncodeBytes(bytes) {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function hmac(secret, data) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data));
  return b64urlEncodeBytes(new Uint8Array(sig));
}

function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Test/DogBuild helper: mint an assertion. Not exposed as an MCP tool. */
export async function signRoleAssertion(secret, payload) {
  const payloadB64 = b64urlEncodeBytes(new TextEncoder().encode(JSON.stringify(payload)));
  return `${payloadB64}.${await hmac(secret, payloadB64)}`;
}

export async function verifyRoleAssertion(env, assertion, now = Date.now()) {
  if (!env.ROLE_ASSERTION_KEY) {
    throw new ControlError(ErrorClass.CONFIG_INVALID, "ROLE_ASSERTION_KEY is not configured; roles cannot be granted.");
  }
  const parts = String(assertion || "").split(".");
  if (parts.length !== 2 || !parts[0] || !parts[1]) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion is malformed.");
  }
  const expected = await hmac(env.ROLE_ASSERTION_KEY, parts[0]);
  if (!timingSafeEqual(expected, parts[1])) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion signature is invalid.");
  }
  let payload;
  try {
    payload = JSON.parse(b64urlToString(parts[0]));
  } catch {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion payload is not valid JSON.");
  }
  if (!ROLES.includes(payload.role) || payload.role === "read") {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion names an unknown or non-grantable role.");
  }
  if (typeof payload.exp !== "number" || payload.exp <= now) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion has expired.");
  }
  if (payload.exp - now > MAX_ASSERTION_LIFETIME_MS) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion lifetime exceeds the permitted maximum.");
  }
  if (!payload.task || !payload.repo || !payload.subject || !payload.nonce) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion is missing required binding fields.");
  }
  if (payload.role === "reviewer" && payload.producer && payload.producer === payload.subject) {
    throw new ControlError(
      ErrorClass.SELF_REVIEW_DENIED,
      "A producer cannot hold independent-review authority for its own lineage."
    );
  }
  return payload;
}

/**
 * Resolve the role for one request. Never consults tool arguments.
 * No assertion => read-only. This is the fail-closed default.
 */
export async function resolveRole(env, headerValue, now = Date.now()) {
  if (!headerValue) return { role: "read", assertion: null };
  const payload = await verifyRoleAssertion(env, headerValue, now);
  return { role: payload.role, assertion: payload };
}

export function assertAssertionCoversRepo(assertion, owner, repo) {
  if (!assertion) return;
  const requested = `${owner}/${repo}`.toLowerCase();
  if (String(assertion.repo).toLowerCase() !== requested) {
    throw new ControlError(ErrorClass.ROLE_DENIED, "Role assertion does not cover the requested repository.", {
      requested,
    });
  }
}
