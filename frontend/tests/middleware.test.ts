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

describe("EP-027 trust boundary: Caddy X-Forwarded-For → X-Real-IP", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.BACKEND_INTERNAL_URL;
  });

  function setupFetch() {
    const capturedHeaders = new Headers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_url: string, opts: { headers: Headers }) => {
        for (const [k, v] of opts.headers.entries()) capturedHeaders.set(k, v);
        return new Response(null, { status: 200 });
      })
    );
    return capturedHeaders;
  }

  it("A: Caddy-supplied X-Forwarded-For becomes backend X-Real-IP; spoofed X-Real-IP is stripped", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: {
        "x-forwarded-for": "203.0.113.10",
        "x-real-ip": "1.2.3.4",
      },
    });
    await middleware(req);

    expect(sent.get("x-real-ip")).toBe("203.0.113.10");
    expect(sent.has("x-forwarded-for")).toBe(false);
  });

  it("B: two Caddy-provided clients reach backend with different X-Real-IP values", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";

    // Client A
    const sentA = setupFetch();
    await middleware(
      new NextRequest("https://publisher.test/auth/login", {
        method: "POST",
        headers: { "x-forwarded-for": "203.0.113.10" },
      })
    );
    expect(sentA.get("x-real-ip")).toBe("203.0.113.10");

    // Client B
    const sentB = setupFetch();
    await middleware(
      new NextRequest("https://publisher.test/auth/login", {
        method: "POST",
        headers: { "x-forwarded-for": "203.0.113.20" },
      })
    );
    expect(sentB.get("x-real-ip")).toBe("203.0.113.20");
  });

  it("C: client-spoofed X-Forwarded-For is stripped (loopback-only Next.js)", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    // Attacker sends X-Forwarded-For directly — but Next.js is loopback-only,
    // so only Caddy traffic reaches it.  The header is still stripped.
    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: {
        "x-forwarded-for": "10.0.0.99",
        "x-real-ip": "attacker-ip",
      },
    });
    await middleware(req);

    // In this test we are simulating the middleware reading a client-sent XFF.
    // The middleware reads it BEFORE stripping.  In production, Caddy is the
    // sole ingress and would overwrite XFF.  This test documents that the
    // middleware trusts the leftmost XFF value (Caddy's).
    expect(sent.has("x-forwarded-for")).toBe(false);
    expect(sent.has("x-forwarded-host")).toBe(false);
    expect(sent.has("x-forwarded-proto")).toBe(false);
  });

  it("D: missing X-Forwarded-For → no X-Real-IP set (safe socket fallback)", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: {},
    });
    await middleware(req);

    expect(sent.has("x-real-ip")).toBe(false);
    expect(sent.has("x-forwarded-for")).toBe(false);
  });

  it("D2: malformed X-Forwarded-For → no X-Real-IP set", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: { "x-forwarded-for": "not-an-ip" },
    });
    await middleware(req);

    expect(sent.has("x-real-ip")).toBe(false);
  });

  it("E: valid IPv6 client address is extracted from X-Forwarded-For", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: { "x-forwarded-for": "::1" },
    });
    await middleware(req);

    expect(sent.get("x-real-ip")).toBe("::1");
  });

  it("E2: bracketed IPv6 is accepted", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = setupFetch();

    const req = new NextRequest("https://publisher.test/auth/login", {
      method: "POST",
      headers: { "x-forwarded-for": "[2001:db8::1]" },
    });
    await middleware(req);

    expect(sent.get("x-real-ip")).toBe("[2001:db8::1]");
  });
});
