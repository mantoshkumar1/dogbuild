/**
 * DogBuild GitHub control Worker — MCP transport.
 *
 * Remote-only by design: it runs on Cloudflare, spawns no local process, and
 * has no browser, DOM or GUI code path anywhere. A scheduled agent reaches it
 * over HTTP, so closing the session leaves nothing behind to reap.
 */
import { ControlError, ErrorClass } from "./errors.js";
import { handleOAuth } from "./oauth.js";
import { resolveRole, ROLE_ASSERTION_HEADER } from "./roles.js";
import { TOOLS, toolsForRole } from "./tools.js";
import { callTool } from "./handlers.js";

export const SERVER_NAME = "dogbuild-github-control-worker";
export const SERVER_VERSION = "1.0.0";

function jsonRpcResult(id, result) {
  return { jsonrpc: "2.0", id, result };
}
function jsonRpcError(id, code, message, data) {
  return { jsonrpc: "2.0", id, error: { code, message, ...(data ? { data } : {}) } };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    const oauthResponse = await handleOAuth(request, env, url);
    if (oauthResponse) return oauthResponse;

    if (!env.MCP_PATH_SECRET || !url.pathname.startsWith(`/mcp/${env.MCP_PATH_SECRET}`)) {
      return new Response("Not found", { status: 404 });
    }
    if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });

    let rpc;
    try {
      rpc = await request.json();
    } catch {
      return Response.json(jsonRpcError(null, -32700, "Parse error"), { status: 400 });
    }
    const { id, method, params } = rpc;

    // The role is resolved from the signed request header only. Tool
    // arguments are never consulted, so a caller cannot name its own role.
    let ctx;
    try {
      ctx = await resolveRole(env, request.headers.get(ROLE_ASSERTION_HEADER));
    } catch (err) {
      const e = err instanceof ControlError ? err : new ControlError(ErrorClass.ROLE_DENIED, "Role could not be resolved.");
      return Response.json(jsonRpcError(id, -32001, e.message, e.toJSON()));
    }

    try {
      if (method === "initialize") {
        return Response.json(jsonRpcResult(id, {
          protocolVersion: "2024-11-05",
          capabilities: { tools: {} },
          serverInfo: { name: SERVER_NAME, version: SERVER_VERSION },
        }));
      }
      if (method === "notifications/initialized") return new Response(null, { status: 202 });
      if (method === "tools/list") return Response.json(jsonRpcResult(id, { tools: toolsForRole(ctx.role) }));
      if (method === "tools/call") {
        const { name, arguments: args } = params || {};
        const result = await callTool(env, name, args || {}, ctx);
        return Response.json(jsonRpcResult(id, { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] }));
      }
      return Response.json(jsonRpcError(id, -32601, `Method not found: ${method}`));
    } catch (err) {
      if (err instanceof ControlError) {
        return Response.json(jsonRpcError(id, -32000, err.message, err.toJSON()));
      }
      return Response.json(jsonRpcError(id, -32000, "Internal error"));
    }
  },
};

export { TOOLS, toolsForRole, callTool };
