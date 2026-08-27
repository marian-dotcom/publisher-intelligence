import {
  BACKEND_PREFIXES,
  isBackendPath,
  isSharedBackendPath,
  requestsApiJson,
  resolveBackendInternalUrl,
} from "../lib/backend-routing";
import { describe, expect, it } from "vitest";

describe("backend routing helpers", () => {
  it("covers exactly the backend-owned prefixes", () => {
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

  it("matches backend paths including subpaths", () => {
    expect(isBackendPath("/auth/login")).toBe(true);
    expect(isBackendPath("/product/home/status")).toBe(true);
    expect(isBackendPath("/incidents")).toBe(true);
    expect(isBackendPath("/evidence/packs/x")).toBe(true);
  });

  it("does not match frontend-only paths", () => {
    expect(isBackendPath("/login")).toBe(false);
    expect(isBackendPath("/")).toBe(false);
    expect(isBackendPath("/authorize")).toBe(false);
  });

  it("identifies shared prefixes (frontend page + backend API coexisting)", () => {
    expect(isSharedBackendPath("/timeline")).toBe(true);
    expect(isSharedBackendPath("/incidents")).toBe(true);
    expect(isSharedBackendPath("/incidents/abc-123")).toBe(true);
    expect(isSharedBackendPath("/evidence/packs/abc-123")).toBe(true);
    expect(isSharedBackendPath("/evidence/abc-123")).toBe(true);
    // Backend-exclusive prefixes are NOT shared with a frontend page.
    expect(isSharedBackendPath("/auth/login")).toBe(false);
    expect(isSharedBackendPath("/product/home/status")).toBe(false);
    expect(isSharedBackendPath("/investigations")).toBe(false);
    expect(isSharedBackendPath("/health/live")).toBe(false);
  });

  it("routes by content negotiation: only explicit JSON requests are API calls", () => {
    expect(requestsApiJson("application/json")).toBe(true);
    expect(requestsApiJson("text/html,application/xhtml+xml")).toBe(false);
    expect(requestsApiJson("text/html")).toBe(false);
    expect(requestsApiJson(null)).toBe(false);
    expect(requestsApiJson(undefined)).toBe(false);
  });

  it("resolves BACKEND_INTERNAL_URL at request time from the environment", () => {
    expect(resolveBackendInternalUrl({ BACKEND_INTERNAL_URL: "http://backend-a:8000" })).toBe(
      "http://backend-a:8000"
    );
    expect(
      resolveBackendInternalUrl({ BACKEND_INTERNAL_URL: "http://backend-b:8000/" })
    ).toBe("http://backend-b:8000");
  });

  it("defaults to the compose service name outside production", () => {
    expect(resolveBackendInternalUrl({ NODE_ENV: "test" })).toBe("http://api:8000");
  });

  it("fails closed in production builds without an explicit target", () => {
    expect(resolveBackendInternalUrl({ NODE_ENV: "production" })).toBeNull();
  });
});
