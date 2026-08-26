// @vitest-environment node

import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { middleware } from "../middleware";

describe("backend middleware proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.BACKEND_INTERNAL_URL;
  });

  it("preserves both authentication Set-Cookie headers independently", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const upstreamHeaders = new Headers();
    upstreamHeaders.append(
      "set-cookie",
      "pi_session=session-value; Path=/; Secure; HttpOnly; SameSite=lax"
    );
    upstreamHeaders.append(
      "set-cookie",
      "pi_csrf=csrf-value; Path=/; Secure; SameSite=lax"
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { headers: upstreamHeaders }))
    );

    const response = await middleware(
      new NextRequest("https://publisher.test/auth/login", { method: "POST" })
    );
    const cookies = response.headers.getSetCookie();

    expect(cookies).toHaveLength(2);
    expect(cookies).toContain(
      "pi_session=session-value; Path=/; Secure; HttpOnly; SameSite=lax"
    );
    expect(cookies).toContain(
      "pi_csrf=csrf-value; Path=/; Secure; SameSite=lax"
    );
  });
});
