/**
 * EP-026 local/production-like runtime: backend routing target helpers.
 *
 * The frontend intentionally calls the API with relative, same-origin paths
 * (frontend/lib/api.ts: `credentials: "same-origin"`). In containerized
 * topologies the Next.js server proxies ONLY the path prefixes that belong to
 * the FastAPI application (verified against every APIRouter prefix plus the
 * root-level memory routes in backend/app).
 *
 * IMPORTANT (proven experimentally, EP-026 M7 support work): Next.js freezes
 * `rewrites()` destinations into `.next/required-server-files.json` at BUILD
 * time. To keep ONE immutable image portable across deployments,
 * `middleware.ts` resolves `BACKEND_INTERNAL_URL` at REQUEST time instead.
 */

export const BACKEND_PREFIXES = [
  "/auth",
  "/health",
  "/investigations",
  "/product",
  "/timeline",
  "/incidents",
  "/evidence",
] as const;

/**
 * Prefixes that host BOTH a Next.js frontend page AND a backend API route at
 * the same path namespace (same-origin proxy). For these, the middleware must
 * distinguish an API request from a browser document navigation via content
 * negotiation; document/HTML navigation renders the frontend page, and only
 * explicit API requests (Accept: application/json) are proxied to FastAPI.
 *
 * Keep this set in sync with the frontend route map (app/(protected)/timeline,
 * app/(protected)/incidents, app/(protected)/incidents/[id], app/evidence/[id])
 * and the backend memory router (app/api/memory.py).
 */
export const SHARED_PREFIXES = ["/timeline", "/incidents", "/evidence"] as const;

export const BACKEND_INTERNAL_URL_ENV = "BACKEND_INTERNAL_URL";
export const DEFAULT_BACKEND_INTERNAL_URL = "http://api:8000";

type Env = Record<string, string | undefined>;

export function resolveBackendInternalUrl(
  env: Env = process.env
): string | null {
  const raw = env[BACKEND_INTERNAL_URL_ENV];
  if (raw === undefined || raw.trim() === "") {
    return (env.NODE_ENV ?? process.env.NODE_ENV) === "production"
      ? null // fail closed: never guess a backend target in production builds
      : DEFAULT_BACKEND_INTERNAL_URL;
  }
  try {
    new URL(raw);
    return raw.replace(/\/+$/, "");
  } catch {
    return null;
  }
}

export function isBackendPath(pathname: string): boolean {
  return BACKEND_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

/** True when the path lives on a shared prefix (frontend page + backend API). */
export function isSharedBackendPath(pathname: string): boolean {
  return SHARED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  );
}

/**
 * Content negotiation: an explicit API request carries Accept: application/json
 * (set by apiFetch). Anything else — notably the browser's default HTML Accept
 * on top-level document navigation — is a frontend page request and must NOT be
 * proxied to the backend on shared prefixes.
 */
export function requestsApiJson(acceptHeader: string | null | undefined): boolean {
  if (!acceptHeader) return false;
  return acceptHeader.includes("application/json");
}
