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

describe("shared prefixes: document navigation renders the page, API requests proxy", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.BACKEND_INTERNAL_URL;
  });

  function spyOnFetch() {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ entries: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("REGRESSION: browser document navigation to /timeline is NOT proxied (renders the page)", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    const req = new NextRequest("https://publisher.test/timeline", {
      method: "GET",
      headers: { accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" },
    });
    const res = await middleware(req);

    // A page navigation must never reach FastAPI; the backend call is skipped so
    // Next.js can render the /timeline page (the exact live defect).
    expect(fetchMock).not.toHaveBeenCalled();
    expect(res.status).toBe(200);
  });

  it("REGRESSION: browser document navigation to /incidents and /incidents/<id> is NOT proxied", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    await middleware(
      new NextRequest("https://publisher.test/incidents", {
        method: "GET",
        headers: { accept: "text/html" },
      }),
    );
    await middleware(
      new NextRequest("https://publisher.test/incidents/abc-123", {
        method: "GET",
        headers: { accept: "text/html" },
      }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("REGRESSION: browser document navigation to /evidence/<id> is NOT proxied", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    await middleware(
      new NextRequest("https://publisher.test/evidence/abc-123", {
        method: "GET",
        headers: { accept: "text/html" },
      }),
    );

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("API request (Accept: application/json) to /timeline is proxied to FastAPI", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    await middleware(
      new NextRequest("https://publisher.test/timeline", {
        method: "GET",
        headers: { accept: "application/json" },
      }),
    );

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [target] = fetchMock.mock.calls[0] as [string];
    expect(String(target)).toBe("http://api:8000/timeline");
  });

  it("API requests to /incidents, /incidents/<id>, /evidence/packs/<id> are proxied", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    await middleware(
      new NextRequest("https://publisher.test/incidents", {
        method: "GET",
        headers: { accept: "application/json" },
      }),
    );
    await middleware(
      new NextRequest("https://publisher.test/incidents/abc-123", {
        method: "GET",
        headers: { accept: "application/json" },
      }),
    );
    await middleware(
      new NextRequest("https://publisher.test/evidence/packs/abc-123", {
        method: "GET",
        headers: { accept: "application/json" },
      }),
    );

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const targets = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(targets).toContain("http://api:8000/incidents");
    expect(targets).toContain("http://api:8000/incidents/abc-123");
    expect(targets).toContain("http://api:8000/evidence/packs/abc-123");
  });

  it("backend-exclusive paths still proxy regardless of Accept", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const fetchMock = spyOnFetch();

    await middleware(
      new NextRequest("https://publisher.test/auth/session", {
        method: "GET",
        headers: { accept: "text/html" },
      }),
    );
    await middleware(
      new NextRequest("https://publisher.test/product/home/status", {
        method: "GET",
        headers: { accept: "text/html" },
      }),
    );
    await middleware(
      new NextRequest("https://publisher.test/investigations", {
        method: "POST",
        headers: { accept: "application/json" },
      }),
    );

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("trust boundary still strips spoofed forwarding headers on proxied requests", async () => {
    process.env.BACKEND_INTERNAL_URL = "http://api:8000";
    const sent = new Headers();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_url: string, opts: { headers: Headers }) => {
        for (const [k, v] of opts.headers.entries()) sent.set(k, v);
        return new Response(null, { status: 200 });
      }),
    );

    await middleware(
      new NextRequest("https://publisher.test/incidents", {
        method: "GET",
        headers: {
          accept: "application/json",
          "x-forwarded-for": "203.0.113.5",
          "x-real-ip": "1.2.3.4",
          "x-forwarded-host": "attacker.test",
          "x-forwarded-proto": "http",
        },
      }),
    );

    expect(sent.get("x-real-ip")).toBe("203.0.113.5");
    expect(sent.has("x-forwarded-for")).toBe(false);
    expect(sent.has("x-forwarded-host")).toBe(false);
    expect(sent.has("x-forwarded-proto")).toBe(false);
  });
});
