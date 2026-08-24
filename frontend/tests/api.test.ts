import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, ApiError } from "../lib/api";

function mockResponse(status: number, body: unknown = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "pi_csrf=; Max-Age=0; path=/";
});

describe("apiFetch", () => {
  it("returns typed JSON on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(200, { value: 42 })));

    await expect(apiFetch<{ value: number }>("/anything")).resolves.toEqual({ value: 42 });
  });

  it("maps 401 to the unauthorized kind", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(401)));

    await expect(apiFetch("/auth/session")).rejects.toMatchObject({ kind: "unauthorized", status: 401 });
    expect.hasAssertions();
  });

  it("maps 403 to the forbidden kind", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(403)));

    const result = apiFetch("/investigations", { method: "POST" });
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ kind: "forbidden", status: 403 });
  });

  it("injects the CSRF header from the pi_csrf cookie on writes", async () => {
    document.cookie = "pi_csrf=test-csrf-value; path=/";
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(200, { revoked: true }));
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/auth/logout", { method: "POST" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/logout",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf-value" }),
      }),
    );
  });
});
