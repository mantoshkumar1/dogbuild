import { ControlError, ErrorClass } from "./errors.js";
import { callTool } from "./handlers.js";
import { TOOLS } from "./tools.js";

export const SERVER_NAME = "dogbuild-control-mcp";
export const SERVER_VERSION = "0.1.0";
export const MAX_REQUEST_BYTES = 32_768;
const PATH_SECRET_RE = /^[A-Za-z0-9._~-]{32,256}$/;
const ACCESS_TOKEN_RE = /^[A-Za-z0-9._~-]{32,512}$/;

function result(id, value) {
  return { jsonrpc: "2.0", id, result: value };
}

function rpcError(id, code, message, data) {
  return { jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } };
}

async function sameSecret(actual, expected) {
  if (typeof actual !== "string" || typeof expected !== "string" || !actual || !expected) return false;
  const encode = (value) => new TextEncoder().encode(value);
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", encode(actual)),
    crypto.subtle.digest("SHA-256", encode(expected)),
  ]);
  const left = new Uint8Array(a);
  const right = new Uint8Array(b);
  let difference = left.length ^ right.length;
  for (let i = 0; i < Math.min(left.length, right.length); i += 1) difference |= left[i] ^ right[i];
  return difference === 0;
}

async function readRpc(request) {
  const advertised = Number(request.headers.get("content-length"));
  if (Number.isFinite(advertised) && advertised > MAX_REQUEST_BYTES) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "MCP request body is too large.");
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_REQUEST_BYTES) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "MCP request body is too large.");
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new ControlError(ErrorClass.INVALID_INPUT, "MCP request is not valid JSON.");
  }
}

async function handle(request, env) {
  const url = new URL(request.url);
  const expectedPath = env && PATH_SECRET_RE.test(env.MCP_PATH_SECRET || "")
    ? `/mcp/${env.MCP_PATH_SECRET}`
    : null;
  if (!expectedPath || url.pathname !== expectedPath) return new Response("Not found", { status: 404 });

  if (!ACCESS_TOKEN_RE.test(env.MCP_ACCESS_TOKEN || "") || !env.GITHUB_TOKEN || !env.ALLOWED_REPOS) {
    return new Response("Server unavailable", { status: 503 });
  }

  const authorization = request.headers.get("authorization") || "";
  const suppliedToken = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  if (!(await sameSecret(suppliedToken, env.MCP_ACCESS_TOKEN))) {
    return new Response("Unauthorized", {
      status: 401,
      headers: { "WWW-Authenticate": "Bearer" },
    });
  }

  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

  let rpc;
  try {
    rpc = await readRpc(request);
  } catch (error) {
    const controlled = error instanceof ControlError
      ? error
      : new ControlError(ErrorClass.INVALID_INPUT, "MCP request could not be read.");
    return Response.json(rpcError(null, -32700, controlled.message, controlled.toJSON()), { status: 400 });
  }

  const { id = null, method, params } = rpc || {};
  try {
    if (method === "initialize") {
      return Response.json(result(id, {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
      }));
    }
    if (method === "notifications/initialized") return new Response(null, { status: 202 });
    if (method === "tools/list") return Response.json(result(id, { tools: TOOLS }));
    if (method === "tools/call") {
      const name = params && params.name;
      const args = params && params.arguments !== undefined ? params.arguments : {};
      const value = await callTool(env, name, args);
      return Response.json(result(id, {
        content: [{ type: "text", text: JSON.stringify(value, null, 2) }],
      }));
    }
    return Response.json(rpcError(id, -32601, `Method not found: ${String(method)}`));
  } catch (error) {
    const controlled = error instanceof ControlError
      ? error
      : new ControlError(ErrorClass.UPSTREAM_ERROR, "Internal error.");
    return Response.json(rpcError(id, -32000, controlled.message, controlled.toJSON()));
  }
}

export default { fetch: handle };
export { callTool, TOOLS };
