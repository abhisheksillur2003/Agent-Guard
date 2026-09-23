import { cookies } from "next/headers";

import { ACCESS_COOKIE, apiBaseUrl } from "@/lib/server-auth";

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(
  request: Request,
  context: RouteContext,
): Promise<Response> {
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  if (!token) {
    return Response.json(
      { message: "Authentication required" },
      { status: 401 },
    );
  }
  const { path } = await context.params;
  const incoming = new URL(request.url);
  const target = `${apiBaseUrl()}/api/v1/${path.map(encodeURIComponent).join("/")}${incoming.search}`;
  const headers = new Headers();
  headers.set("authorization", `Bearer ${token}`);
  headers.set("accept", "application/json");
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("x-request-id", requestId);

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
    });
    const responseHeaders = new Headers();
    responseHeaders.set(
      "content-type",
      upstream.headers.get("content-type") ?? "application/json",
    );
    const upstreamRequestId = upstream.headers.get("x-request-id");
    if (upstreamRequestId)
      responseHeaders.set("x-request-id", upstreamRequestId);
    return new Response(upstream.body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch {
    return Response.json(
      { message: "AgentGuard API is unavailable" },
      { status: 503 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
