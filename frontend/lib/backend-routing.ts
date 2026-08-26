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
