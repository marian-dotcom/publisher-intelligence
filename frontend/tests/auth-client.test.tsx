import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../lib/auth-client";

function mockResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function Probe() {
  const auth = useAuth();
  return (
    <p>
      status={auth.status}
      tenant={auth.session?.tenant_id ?? "none"}
    </p>
  );
}

describe("AuthProvider", () => {
  it("starts in checking and becomes authenticated on session restore", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockResponse(200, { actor_subject_id: "a", tenant_id: "t-1", role: "OPERATOR" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    // Initial status is "checking" (session restoration in flight).
    expect(screen.getByText(/status=checking/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/status=authenticated/)).toBeInTheDocument());
    expect(screen.getByText(/tenant=t-1/)).toBeInTheDocument();
  });

  it("becomes unauthenticated when the session is expired (401)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(401)));

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByText(/status=unauthenticated/)).toBeInTheDocument());
  });
});
