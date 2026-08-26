import { BACKEND_PREFIXES, backendRewrites, createNextConfig } from "../lib/backend-rewrites";
import { describe, expect, it } from "vitest";

describe("same-origin backend rewrites", () => {
  it("routes exactly the backend-owned prefixes", () => {
    expect(BACKEND_PREFIXES).toEqual([
      "/auth",
      "/health",
      "/investigations",
      "/product",
      "/timeline",
      "/incidents",
      "/evidence",
    ]);
  });

  it("forwards prefixes to the configured internal API target", () => {
    const rewrites = backendRewrites("http://api:8000");
    expect(rewrites).toHaveLength(BACKEND_PREFIXES.length);
    const login = rewrites.find((r) => r.source === "/auth/:path*");
    expect(login).toEqual({
      source: "/auth/:path*",
      destination: "http://api:8000/auth/:path*",
    });
  });

  it("defaults the internal target to the compose service name", () => {
    const config = createNextConfig({});
    expect(config.rewrites).toBeDefined();
  });

  it("does not route frontend-only paths to the backend", () => {
    const sources = backendRewrites("http://api:8000").map((r) => r.source);
    expect(sources.some((source) => source.startsWith("/login"))).toBe(false);
  });
});
