/**
 * EP-026 M7 support: request-time same-origin backend proxy.
 *
 * Runs on the Next.js server (Node runtime) for backend-owned paths only.
 * The browser keeps ONE origin; cookies and CSRF semantics pass through
 * untouched (Set-Cookie headers are forwarded); no CORS is added.
 *
 * BACKEND_INTERNAL_URL is resolved at REQUEST time so a single immutable
 * image can target different backends per deployment (proven requirement).
 *
 * TRUST BOUNDARY (EP-027):
 * Caddy is the only public ingress and sets X-Forwarded-For.
 * Next.js is loopback-only; browser cannot reach it directly.
 * We read X-Forwarded-For from the trusted Caddy edge, validate it,
 * strip ALL forwarding headers, and emit exactly one backend-internal
 * X-Real-IP.  This assumption must be revisited if the proxy topology
 * changes (Next.js becomes public, another CDN is placed before Caddy,
 * Caddy is removed, etc.).
 */
import { NextRequest, NextResponse } from "next/server";
import { resolveBackendInternalUrl } from "./lib/backend-routing";

function isValidIpAddress(raw: string): boolean {
  const s = raw.trim();
  if (s === "") return false;
  // IPv4: digits.digits.digits.digits
  if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(s)) return true;
  // IPv6: colon-separated hex groups, optionally bracketed
  const bare = s.startsWith("[") && s.endsWith("]") ? s.slice(1, -1) : s;
  if (/^[0-9a-fA-F:]+$/.test(bare) && bare.includes(":")) return true;
  return false;
}

export async function middleware(request: NextRequest) {
  const backend = resolveBackendInternalUrl(process.env);
  if (backend === null) {
    return new NextResponse(
      JSON.stringify({ detail: "backend routing not configured" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }

  // --- Trust boundary: read Caddy's X-Forwarded-For BEFORE stripping ---
  // Caddy sets this to the canonical client address.  In multi-hop chains
  // the rightmost untrusted value would be the client, but for the current
  // single-proxy topology Caddy's value IS the client.
  const xff = request.headers.get("x-forwarded-for");
  let trustedClientIp = "";
  if (xff) {
    // Take the first (leftmost) entry — in a single-proxy chain this is
    // the original client.  Strip any surrounding whitespace.
    const candidate = xff.split(",")[0]?.trim() ?? "";
    if (isValidIpAddress(candidate)) {
      trustedClientIp = candidate;
    }
  }

  // --- Strip ALL untrusted forwarding headers ---
  const target = new URL(backend + request.nextUrl.pathname + request.nextUrl.search);
  const headers = new Headers(request.headers);
  headers.delete("x-real-ip");
  headers.delete("x-forwarded-for");
  headers.delete("x-forwarded-host");
  headers.delete("x-forwarded-proto");
  headers.set("host", target.host);

  // Set exactly one backend-facing identity header.
  if (trustedClientIp) {
    headers.set("x-real-ip", trustedClientIp);
  }
  // If no valid trusted IP was established, no X-Real-IP is set.
  // FastAPI falls back to request.client.host (loopback socket address).

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
