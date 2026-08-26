/**
 * EP-026 M7 support: request-time same-origin backend proxy.
 *
 * Runs on the Next.js server (Node runtime) for backend-owned paths only.
 * The browser keeps ONE origin; cookies and CSRF semantics pass through
 * untouched (Set-Cookie headers are forwarded); no CORS is added.
 *
 * BACKEND_INTERNAL_URL is resolved at REQUEST time so a single immutable
 * image can target different backends per deployment (proven requirement).
 */
import { NextRequest, NextResponse } from "next/server";
import { resolveBackendInternalUrl } from "./lib/backend-routing";

export async function middleware(request: NextRequest) {
  const backend = resolveBackendInternalUrl(process.env);
  if (backend === null) {
    return new NextResponse(
      JSON.stringify({ detail: "backend routing not configured" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
  const target = new URL(backend + request.nextUrl.pathname + request.nextUrl.search);
  const headers = new Headers(request.headers);
  headers.set("host", target.host);
  const response = await fetch(target, {
    method: request.method,
    headers,
    body: request.body,
    // @ts-expect-error -- Node fetch duplex streaming option
    duplex: "half",
    redirect: "manual",
  });
  const proxied = new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
  });
  response.headers.forEach((value, key) => {
    const normalizedKey = key.toLowerCase();
    if (normalizedKey !== "content-encoding" && normalizedKey !== "set-cookie") {
      proxied.headers.set(key, value);
    }
  });
  response.headers.getSetCookie().forEach((cookie) => {
    proxied.headers.append("set-cookie", cookie);
  });
  return proxied;
}

export const config = {
  matcher: [
    "/auth/:path*",
    "/health/:path*",
    "/investigations/:path*",
    "/product/:path*",
    "/timeline/:path*",
    "/incidents/:path*",
    "/evidence/:path*",
  ],
};
