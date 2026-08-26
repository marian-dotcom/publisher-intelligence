import type { NextConfig } from "next";

/**
 * EP-026 local/production-like runtime: same-origin backend routing.
 *
 * The frontend intentionally calls the API with relative, same-origin paths
 * (frontend/lib/api.ts: `credentials: "same-origin"`, paths like
 * `/auth/login`). In containerized topologies the Next.js server and the
 * FastAPI service are separate processes, so the deployment injects
 * `BACKEND_INTERNAL_URL` and these rewrites forward ONLY the path prefixes
 * that belong to the FastAPI application (verified against every APIRouter
 * prefix in backend/app: /auth, /health, /investigations, /product plus the
 * root-level memory routes /timeline, /incidents, /evidence).
 *
 * No CORS is needed (browser still sees one origin), cookies keep their exact
 * semantics, and no new runtime dependency is introduced.
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

export function backendRewrites(backendInternalUrl: string): {
  source: string;
  destination: string;
}[] {
  return BACKEND_PREFIXES.map((prefix) => ({
    source: `${prefix}/:path*`,
    destination: `${backendInternalUrl}${prefix}/:path*`,
  }));
}

export function createNextConfig(
  env: Record<string, string | undefined> = process.env
): NextConfig {
  return {
    reactStrictMode: true,
    poweredByHeader: false,
    async rewrites() {
      // Evaluated at server start; `next start` loads next.config.ts at boot,
      // so the internal API target is environment-driven per deployment.
      return backendRewrites(env.BACKEND_INTERNAL_URL ?? "http://api:8000");
    },
  };
}

const nextConfig: NextConfig = createNextConfig();

export default nextConfig;
