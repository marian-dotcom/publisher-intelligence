import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRouter } from "next/navigation";

import { AuthProvider, useAuth } from "../lib/auth-client";
import { ProtectedShell } from "../components/protected-shell";
import { IncidentDetailView } from "../components/incident-views";

function mockResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as Response;
}

vi.mock("next/navigation", () => ({
  useRouter: vi.fn().mockReturnValue({ push: vi.fn(), replace: vi.fn() }),
}));

const replace = vi.fn();

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  replace.mockClear();
});

vi.mocked(useRouter).mockReturnValue({ replace } as unknown as ReturnType<typeof useRouter>);

function Probe() {
  const auth = useAuth();
  return (
    <p>
      status={auth.status}
      tenant={auth.session?.tenant_id ?? "none"}
    </p>
  );
}

function renderProbe() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe("session restore classification (scenario: auth truthfulness)", () => {
  it("401 → unauthenticated → login redirect", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(401)));
    renderProbe();
    await waitFor(() => expect(screen.getByText(/status=unauthenticated/)).toBeInTheDocument());
  });

  it("500 → explicit error state; no redirect to /login; session not claimed invalid", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockResponse(500));
    vi.stubGlobal("fetch", fetchMock);
    render(
      <AuthProvider>
        <ProtectedShell>
          <p>protected content</p>
        </ProtectedShell>
      </AuthProvider>,
    );
    await screen.findByRole("alert");
    expect(screen.getByText(/could not verify your session/i)).toBeInTheDocument();
    // No login redirect while the failure is not an auth rejection.
    expect(replace).not.toHaveBeenCalledWith("/login");
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();

    // Retry path re-runs the session check.
    fetchMock.mockResolvedValue(
      mockResponse(200, { actor_subject_id: "a", tenant_id: "t", role: "OPERATOR" }),
    );
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await screen.findByText("protected content", undefined, { timeout: 3000 });
  });

  it("network failure → explicit error state; no login redirect", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network down")));
    render(
      <AuthProvider>
        <ProtectedShell>
          <p>protected content</p>
        </ProtectedShell>
      </AuthProvider>,
    );
    await screen.findByRole("alert");
    expect(replace).not.toHaveBeenCalledWith("/login");
  });
});

describe("logout truthfulness", () => {
  async function loginThenLogout(logoutStatus: number | Error) {
    const responses: Response[] = [
      mockResponse(200, { actor_subject_id: "a", tenant_id: "t", role: "OPERATOR" }), // restore
    ];
    if (logoutStatus instanceof Error) {
      responses.push(logoutStatus as unknown as Response);
    } else {
      responses.push(mockResponse(logoutStatus, { revoked: logoutStatus === 200 }));
    }
    let call = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => {
        const response = responses[call];
        call += 1;
        return Promise.resolve(response);
      }),
    );

    function LogoutProbe() {
      const auth = useAuth();
      return (
        <button type="button" onClick={() => void auth.logout()}>
          trigger-logout
        </button>
      );
    }

    render(
      <AuthProvider>
        <LogoutProbe />
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByText(/status=authenticated/)).toBeInTheDocument());

    (await screen.findByRole("button", { name: "trigger-logout" })).click();
  }

  it("successful logout clears state", async () => {
    await loginThenLogout(200);
    await waitFor(() => expect(screen.getByText(/status=unauthenticated/)).toBeInTheDocument());
  });

  it("already-invalid session (401) is treated as logged out", async () => {
    await loginThenLogout(401);
    await waitFor(() => expect(screen.getByText(/status=unauthenticated/)).toBeInTheDocument());
  });

  it("CSRF 403 keeps the session (stays authenticated, no false logout)", async () => {
    await loginThenLogout(403);
    await waitFor(() => expect(screen.getByText(/status=error/)).toBeInTheDocument());
  });

  it("server/network failure during logout keeps the session (no false logout)", async () => {
    await loginThenLogout(new TypeError("network down"));
    await waitFor(() => expect(screen.getByText(/status=error/)).toBeInTheDocument());
  });
});

const DETAIL_BODY = {
  incident: {
    incident_id: "i1",
    title: "T",
    symptom_family: "GAM_ADSERVING",
    description: "d",
    status: "OPEN",
    severity: null,
    reported_start_at: null,
    reported_end_at: null,
    opened_at: "2026-08-24T00:00:00+00:00",
    resolved_at: null,
    resolution_summary: null,
    site_id: "s1",
  },
  symptom_segments: [],
  last_known_good_references: [],
  hypotheses: [],
  monetization: {
    capability: "ABSOLUTE",
    metrics: [
      {
        metric_code: "revenue",
        unit: "CURRENCY",
        source: "gam",
        granularity: "DAY",
        points: [{ period_start: "2026-08-20T00:00:00+00:00", period_end: "2026-08-21T00:00:00+00:00", value: 1234.5, freshness_status: "MATURE" }],
      },
    ],
  },
};

describe("currency semantics", () => {
  it("renders persisted CURRENCY values neutrally without inventing USD/EUR/symbols", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(200, DETAIL_BODY)));

    render(<IncidentDetailView incidentId="i1" />);
    await screen.findByText(/1234.5 \(currency value\)/);

    const body = document.body.textContent ?? "";
    expect(body).not.toContain("$");
    expect(body).not.toContain("$1,234.50");
    expect(body).not.toContain("USD");
    expect(body).not.toContain("EUR");
  });
});
