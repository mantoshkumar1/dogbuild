/**
 * Minimal self-issued OAuth 2.1 layer, ported unchanged in behavior from the
 * reference Worker so the existing custom connector keeps working.
 *
 * It is NOT the access control: /mcp/<MCP_PATH_SECRET> is. Strategy accepted
 * this arrangement as existing state, not as proof of strong authorization;
 * real client validation, short-lived tokens and replay protection remain
 * follow-up work tracked in the package README.
 */
function b64urlEncode(bytes) {
  let bin = "";
  const arr = bytes instanceof Uint8Array ? bytes : new TextEncoder().encode(bytes);
  for (const b of arr) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function b64urlDecodeToString(str) {
  let s = String(str).replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return atob(s);
}
async function hmacKey(secret) {
  return crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign", "verify"]);
}
async function signPayload(secret, payloadStr) {
  const sig = await crypto.subtle.sign("HMAC", await hmacKey(secret), new TextEncoder().encode(payloadStr));
  return b64urlEncode(new Uint8Array(sig));
}
async function verifyPayload(secret, payloadStr, sigB64url) {
  const sigBytes = Uint8Array.from(b64urlDecodeToString(sigB64url), (c) => c.charCodeAt(0));
  return crypto.subtle.verify("HMAC", await hmacKey(secret), sigBytes, new TextEncoder().encode(payloadStr));
}
async function sha256Base64Url(str) {
  return b64urlEncode(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str))));
}
async function makeAuthCode(env, { redirect_uri, code_challenge }) {
  const payloadB64 = b64urlEncode(JSON.stringify({ redirect_uri, code_challenge, exp: Date.now() + 10 * 60 * 1000 }));
  return `${payloadB64}.${await signPayload(env.OAUTH_CLIENT_SECRET, payloadB64)}`;
}
async function parseAuthCode(env, code) {
  const [payloadB64, sig] = String(code).split(".");
  if (!payloadB64 || !sig) throw new Error("malformed code");
  if (!(await verifyPayload(env.OAUTH_CLIENT_SECRET, payloadB64, sig))) throw new Error("bad signature");
  const payload = JSON.parse(b64urlDecodeToString(payloadB64));
  if (payload.exp < Date.now()) throw new Error("code expired");
  return payload;
}
function oauthMetadata(issuer) {
  return {
    issuer,
    authorization_endpoint: `${issuer}/authorize`,
    token_endpoint: `${issuer}/token`,
    response_types_supported: ["code"],
    grant_types_supported: ["authorization_code", "refresh_token"],
    code_challenge_methods_supported: ["S256"],
    token_endpoint_auth_methods_supported: ["client_secret_post", "client_secret_basic", "none"],
  };
}

export async function handleOAuth(request, env, url) {
  const issuer = `${url.protocol}//${url.host}`;
  if (url.pathname === "/.well-known/oauth-authorization-server") return Response.json(oauthMetadata(issuer));
  if (url.pathname === "/.well-known/oauth-protected-resource") return Response.json({ resource: issuer, authorization_servers: [issuer] });

  if (url.pathname === "/authorize") {
    const p = url.searchParams;
    if (p.get("client_id") !== env.OAUTH_CLIENT_ID) return new Response("invalid_client", { status: 400 });
    const redirect_uri = p.get("redirect_uri");
    const code_challenge = p.get("code_challenge");
    if (!redirect_uri || !code_challenge) return new Response("invalid_request", { status: 400 });
    const redirect = new URL(redirect_uri);
    redirect.searchParams.set("code", await makeAuthCode(env, { redirect_uri, code_challenge }));
    const state = p.get("state");
    if (state) redirect.searchParams.set("state", state);
    return Response.redirect(redirect.toString(), 302);
  }

  if (url.pathname === "/token" && request.method === "POST") {
    const ct = request.headers.get("content-type") || "";
    const form = ct.includes("application/json")
      ? await request.json()
      : Object.fromEntries(new URLSearchParams(await request.text()));
    let client_id = form.client_id;
    let client_secret = form.client_secret;
    const authHeader = request.headers.get("authorization") || "";
    if (authHeader.startsWith("Basic ")) {
      const decoded = atob(authHeader.slice(6));
      const idx = decoded.indexOf(":");
      client_id = decoded.slice(0, idx);
      client_secret = decoded.slice(idx + 1);
    }
    if (client_id !== env.OAUTH_CLIENT_ID) return Response.json({ error: "invalid_client" }, { status: 401 });
    if (client_secret && client_secret !== env.OAUTH_CLIENT_SECRET) return Response.json({ error: "invalid_client" }, { status: 401 });

    if (form.grant_type === "authorization_code") {
      let payload;
      try {
        payload = await parseAuthCode(env, form.code);
      } catch {
        return Response.json({ error: "invalid_grant" }, { status: 400 });
      }
      if (payload.redirect_uri !== form.redirect_uri) return Response.json({ error: "invalid_grant" }, { status: 400 });
      if (form.code_verifier && (await sha256Base64Url(form.code_verifier)) !== payload.code_challenge) {
        return Response.json({ error: "invalid_grant" }, { status: 400 });
      }
      return Response.json({ access_token: crypto.randomUUID(), token_type: "Bearer", expires_in: 2592000, refresh_token: crypto.randomUUID() });
    }
    if (form.grant_type === "refresh_token") {
      return Response.json({ access_token: crypto.randomUUID(), token_type: "Bearer", expires_in: 2592000 });
    }
    return Response.json({ error: "unsupported_grant_type" }, { status: 400 });
  }
  return null;
}
