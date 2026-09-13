import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "../app/(protected)/page";
import { MonitoringCard } from "@/components/monitoring-controls";
import { apiFetch, ApiError } from "@/lib/api";
import type {
  HomeStatus,
  MonitoringProjection,
  SourceHealthResponse,
  UpdateMonitoringResponse,
} from "@/lib/api-types";

const authMocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("@/lib/api");
vi.mock("@/lib/auth-client", () => ({
  useAuth: authMocks.useAuth,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerMocks.push }),
}));

const mockedFetch = vi.mocked(apiFetch);

type Role = "ADMIN" | "OPERATOR" | "VIEWER";

function session(role: Role) {
  return {
    status: "authenticated" as const,
    session: { role },
    retry: vi.fn(),
    logout: vi.fn(),
    login: vi.fn(),
  };
}

function base(over: Partial<MonitoringProjection> = {}): MonitoringProjection {
  return {
    site_id: "s1",
    enabled: false,
    monitoring_state_updated_at: null,
    cadence: { identifier: "six-hour", hours: 6 },
    next_scheduled_for: null,
    in_flight_scheduled_run_status: null,
    ...over,
  };
}

function dialogEl() {
  return document.getElementById("monitoring-dialog") as HTMLDialogElement | null;
}

function confirmButton() {
  // jsdom's stubbed <dialog>.showModal is a no-op, so role queries inside the
  // dialog report no accessible roles (matching AddSiteDialog test convention,
  // which queries dialog buttons via the DOM directly). The confirm action is
  // the last of the two dialog-actions buttons.
  return document.querySelector(
    "#monitoring-dialog .dialog-actions button:last-child",
  ) as HTMLButtonElement;
}

function cancelButton() {
  return document.querySelector(
    "#monitoring-dialog .dialog-actions button:first-child",
  ) as HTMLButtonElement;
}

beforeEach(() => {
  mockedFetch.mockReset();
  authMocks.useAuth.mockReset();
  authMocks.useAuth.mockReturnValue(session("ADMIN"));
});

afterEach(() => {
  authMocks.useAuth.mockReset();
});

describe("MonitoringCard · state rendering (canonical)", () => {
  it("renders Monitoring active with cadence and next scheduled check", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard
        monitoring={base({
          enabled: true,
          next_scheduled_for: "2026-09-02T12:00:00Z",
        })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.getByText("Monitoring active")).toBeInTheDocument();
    expect(screen.getByText(/Every 6 hours/)).toBeInTheDocument();
    expect(document.body.textContent).toContain("Next scheduled check:");
  });

  it("renders Monitoring active without a next check when the boundary is absent", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard monitoring={base({ enabled: true, next_scheduled_for: null })} siteId="s1" onRefetch={vi.fn()} />,
    );
    expect(screen.getByText("Monitoring active")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Next scheduled check:");
  });

  it("renders Paused for OFF with no in-flight run", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard monitoring={base({ enabled: false })} siteId="s1" onRefetch={vi.fn()} />,
    );
    expect(screen.getByText("Paused")).toBeInTheDocument();
    expect(screen.getByText("No automatic checks will start.")).toBeInTheDocument();
  });

  it("renders Paused — current check finishing for OFF with an in-flight run", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false, in_flight_scheduled_run_status: "RUNNING" })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.getByText("Paused — current check finishing")).toBeInTheDocument();
    expect(screen.getByText(/a check already in progress may finish/)).toBeInTheDocument();
  });

  it("renders Monitoring state unavailable (fail-closed) for null projection", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(<MonitoringCard monitoring={null} siteId="s1" onRefetch={vi.fn()} />);
    expect(screen.getByText("Monitoring state unavailable")).toBeInTheDocument();
    expect(screen.getByText("Automatic monitoring is treated as paused.")).toBeInTheDocument();
    // No mutation is offered for an unavailable read.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders Monitoring state unavailable when the projection has an ambiguous enabled value", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false, next_scheduled_for: "2026-09-02T12:00:00Z" })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    // OFF with a fabricated boundary stays a paused read; the boundary cannot
    // resurrect automatic monitoring.
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });
});

describe("MonitoringCard · canonical auth is the only ADMIN source", () => {
  it("lets an ADMIN enable a paused site", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Enable monitoring" })).toBeInTheDocument();
  });

  it("lets an ADMIN pause an active site", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "Pause monitoring" })).toBeInTheDocument();
  });

  it("does not expose any mutation to a non-ADMIN operator role", () => {
    authMocks.useAuth.mockReturnValue(session("OPERATOR"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Enable monitoring" })).not.toBeInTheDocument();
  });

  it("does not expose any mutation to a VIEWER role", () => {
    authMocks.useAuth.mockReturnValue(session("VIEWER"));
    render(
      <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "Pause monitoring" })).not.toBeInTheDocument();
  });

  it("does not expose mutation while auth is loading", () => {
    authMocks.useAuth.mockReturnValue({ status: "checking", session: null });
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not expose mutation while unauthenticated", () => {
    authMocks.useAuth.mockReturnValue({ status: "unauthenticated", session: null });
    render(
      <MonitoringCard
        monitoring={base({ enabled: true })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "Pause monitoring" })).not.toBeInTheDocument();
  });

  it("does not expose mutation when the session role is absent", () => {
    authMocks.useAuth.mockReturnValue({ status: "authenticated", session: null });
    render(
      <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={vi.fn()} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not treat a missing provider as a legitimate non-ADMIN state", () => {
    // A component that relies on useAuth() must be inside AuthProvider. Without
    // a provider (or a correct mock), useAuth() throws rather than silently
    // downgrading to a non-ADMIN session.
    authMocks.useAuth.mockImplementation(() => {
      throw new Error("useAuth must be used inside AuthProvider");
    });
    expect(() =>
      render(
        <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={vi.fn()} />,
      ),
    ).toThrow(/AuthProvider/i);
  });
});

describe("MonitoringCard · enable/pause confirmation", () => {
  it("enable confirmation warns no immediate run, no backfill, and PUTs exactly one {enabled:true}", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockResolvedValueOnce(base({ enabled: true }));
    const onRefetch = vi.fn();
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={onRefetch}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    const dlg = dialogEl()!;
    expect(
      within(dlg).getByText(/will run every 6 hours/),
    ).toBeInTheDocument();
    expect(within(dlg).getByText(/no backfill/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(
      mockedFetch.mock.calls[0][0],
    ).toBe("/product/sites/s1/monitoring");
    expect(
      mockedFetch.mock.calls[0][1],
    ).toMatchObject({ method: "PUT", body: { enabled: true } });
  });

  it("pause confirmation warns no new checks and the in-progress caveat, and PUTs exactly one {enabled:false}", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockResolvedValueOnce(base({ enabled: false }));
    const onRefetch = vi.fn();
    render(
      <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={onRefetch} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Pause monitoring" }));
    const dlg = dialogEl()!;
    expect(within(dlg).getByText(/No new automatic checks will start/)).toBeInTheDocument();
    expect(within(dlg).getByText(/retained/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(
      mockedFetch.mock.calls[0][0],
    ).toBe("/product/sites/s1/monitoring");
    expect(
      mockedFetch.mock.calls[0][1],
    ).toMatchObject({ method: "PUT", body: { enabled: false } });
  });

  it("cancel issues no request and leaves the card unchanged", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    const onRefetch = vi.fn();
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={onRefetch}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(cancelButton());
    });
    expect(mockedFetch).not.toHaveBeenCalled();
    // Dialog closed; still Paused; can reopen.
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    });
    expect(dialogEl()).not.toBeNull();
  });

  it("native cancel (Escape) closes via the cancel→close sequence with no request", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    const dlg = dialogEl()!;
    expect(dlg).not.toBeNull();

    // Simulate the browser's native sequence: Escape fires a `cancel` event on
    // the <dialog>, then the browser's default action closes it (which fires
    // `close`). jsdom's stubbed close()/showModal() are no-ops and perform no
    // automatic close, so dispatch `close` explicitly to mirror the real
    // cancel→close lifecycle. The production component reacts to `close` via
    // its native onClose handler (no custom keydown listener is added for this).
    fireEvent(dlg, new Event("cancel", { bubbles: true }));
    fireEvent(dlg, new Event("close", { bubbles: true }));

    // Native cancellation must not issue any request.
    expect(mockedFetch).not.toHaveBeenCalled();
    // Parent close removes the dialog (clean reset), not merely hiding it.
    await waitFor(() => expect(dialogEl()).toBeNull());

    // Reopening starts clean and actionable — not stuck in a prior submit.
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    expect(dialogEl()).not.toBeNull();
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(mockedFetch.mock.calls[0][0]).toBe("/product/sites/s1/monitoring");
  });

  it("does not send a duplicate PUT while a request is in-flight", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    let resolveFetch: (v: MonitoringProjection) => void = () => {};
    mockedFetch.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve;
      }),
    );
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    const confirmBtn = confirmButton();
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);
    expect(confirmBtn).toBeDisabled();
    await act(async () => {
      resolveFetch(base({ enabled: true }));
    });
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("surfaces an error, keeps the state, and sends no further request on 403", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockRejectedValueOnce(Object.assign(new ApiError("forbidden", 403, "Forbidden"), { status: 403 }));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(screen.getByText(/do not have permission/i)).toBeInTheDocument();
    // Dialog stays open (state kept); card still shows the paused action.
    expect(dialogEl()).not.toBeNull();
  });

  it("surfaces a session-expired message on 401", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockRejectedValueOnce(Object.assign(new ApiError("unauthorized", 401, "Unauthorized"), { status: 401 }));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(screen.getByText(/session has expired/i)).toBeInTheDocument();
  });

  it("surfaces a not-found message on 404", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockRejectedValueOnce(Object.assign(new ApiError("not_found", 404, "Missing"), { status: 404 }));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(screen.getByText(/was not found/i)).toBeInTheDocument();
  });

  it("surfaces a bounded error on network failure", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockRejectedValueOnce(new TypeError("network"));
    render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(screen.getByText(/could not update monitoring/i)).toBeInTheDocument();
  });

  it("refetches the current site after a successful mutation", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockResolvedValueOnce(base({ enabled: false }));
    const onRefetch = vi.fn();
    render(
      <MonitoringCard monitoring={base({ enabled: true })} siteId="s1" onRefetch={onRefetch} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Pause monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(onRefetch).toHaveBeenCalledTimes(1);
  });
});

describe("MonitoringCard · race safety", () => {
  it("closes the dialog when the selected site changes", () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    const { rerender } = render(
      <MonitoringCard
        monitoring={base({ enabled: false })}
        siteId="s1"
        onRefetch={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    expect(dialogEl()).not.toBeNull();
    rerender(
      <MonitoringCard
        monitoring={base({ site_id: "s2", enabled: false })}
        siteId="s2"
        onRefetch={vi.fn()}
      />,
    );
    // A stale-site dialog must not remain actionable for the new selection.
    expect(dialogEl()?.open ?? false).toBe(false);
  });
});

describe("MonitoringCard · in-flight PUT site A → site B race (HomePage)", () => {
  function projection(siteId: string, enabled: boolean): MonitoringProjection {
    return {
      site_id: siteId,
      enabled,
      monitoring_state_updated_at: null,
      cadence: { identifier: "six-hour", hours: 6 },
      next_scheduled_for: null,
      in_flight_scheduled_run_status: null,
    };
  }

  function homeBody(siteId: string, name: string, enabled: boolean): HomeStatus {
    return {
      sites: [
        { site_id: "sA", name: "Site A" },
        { site_id: "sB", name: "Site B" },
      ],
      selected_site_id: siteId,
      publisher_site_condition: "ACTIVE",
      source_health: {
        BROWSER_MONITORING: "UNKNOWN",
        GA4: "UNKNOWN",
        GSC: "UNKNOWN",
        GAM: "UNKNOWN",
        PUBLIC_CONFIG: "UNKNOWN",
      },
      initial_diagnostic: null,
      open_incident_count: 0,
      monetization_capability: "UNKNOWN",
      monitoring: projection(siteId, enabled),
    };
  }

  function sourceBody(siteId: string): SourceHealthResponse {
    return {
      site_id: siteId,
      sources: {
        BROWSER_MONITORING: "UNKNOWN",
        GA4: "UNKNOWN",
        GSC: "UNKNOWN",
        GAM: "UNKNOWN",
        PUBLIC_CONFIG: "UNKNOWN",
      },
    };
  }

  function updateResponse(siteId: string, enabled: boolean): UpdateMonitoringResponse {
    return {
      site_id: siteId,
      enabled,
      monitoring_state_updated_at: "2026-09-03T00:00:00Z",
      cadence: { identifier: "six-hour", hours: 6 },
      next_scheduled_for: enabled ? "2026-09-03T06:00:00Z" : null,
      in_flight_scheduled_run_status: null,
    };
  }

  it("a stale successful PUT for A never contaminates, closes, or refetches under B", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));

    let resolveAPut: (v: UpdateMonitoringResponse) => void = () => {};
    const aPutDeferred = new Promise<UpdateMonitoringResponse>((resolve) => {
      resolveAPut = resolve;
    });

    // HomePage request order, asserted explicitly below.
    mockedFetch
      .mockResolvedValueOnce(homeBody("sA", "Site A", false)) // 0: home A
      .mockResolvedValueOnce(sourceBody("sA")) // 1: source A
      .mockReturnValueOnce(aPutDeferred) // 2: PUT A (pending)
      .mockResolvedValueOnce(homeBody("sB", "Site B", false)) // 3: home B
      .mockResolvedValueOnce(sourceBody("sB")); // 4: source B

    render(<HomePage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Enable monitoring" })).toBeInTheDocument(),
    );
    expect(mockedFetch.mock.calls[0][0]).toBe("/product/home/status");
    expect(String(mockedFetch.mock.calls[1][0])).toContain("/product/source-health?site_id=sA");

    // Open A's dialog and confirm; exactly one PUT targets A.
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(mockedFetch.mock.calls[2][0]).toBe("/product/sites/sA/monitoring");
    expect(mockedFetch.mock.calls[2][1]).toMatchObject({ method: "PUT", body: { enabled: true } });
    expect(mockedFetch.mock.calls.filter(([p]) => p === "/product/sites/sA/monitoring")).toHaveLength(1);

    // Switch to B through the real selector while A's PUT is still pending.
    fireEvent.change(screen.getByLabelText(/Selected site/), { target: { value: "sB" } });
    await waitFor(() => expect(String(mockedFetch.mock.calls[3][0])).toContain("site_id=sB"));
    await waitFor(() => expect(String(mockedFetch.mock.calls[4][0])).toContain("/product/source-health?site_id=sB"));
    await waitFor(() => expect(document.getElementById("monitoring-dialog")).toBeNull());

    // B's dialog must be independently usable despite A's pending PUT.
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    const bDialog = dialogEl()!;
    expect(bDialog).not.toBeNull();
    expect(within(bDialog).getByText(/will run every 6 hours/)).toBeInTheDocument();
    expect(confirmButton()).not.toBeDisabled();

    // Resolve A's successful PUT and flush all resulting async work.
    await act(async () => {
      resolveAPut(updateResponse("sA", true));
    });

    // A's ON projection must never render under B; B stays paused.
    expect(screen.queryByText("Monitoring active")).not.toBeInTheDocument();
    expect(screen.getByText("Paused")).toBeInTheDocument();
    // A's completion must not close or reset B's open dialog.
    expect(document.getElementById("monitoring-dialog")).not.toBeNull();
    expect(confirmButton()).not.toBeDisabled();
    // A's completion must not trigger any stale refetch (no calls beyond the 5).
    expect(mockedFetch.mock.calls.length).toBe(5);
    // Exactly one PUT to A total — no duplicate.
    expect(mockedFetch.mock.calls.filter(([p]) => p === "/product/sites/sA/monitoring")).toHaveLength(1);
  });

  it("a stale A generation completion never closes, resets, or refetches the A→B→A view", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));

    let resolveOldAPut: (v: UpdateMonitoringResponse) => void = () => {};
    const oldAPut = new Promise<UpdateMonitoringResponse>((resolve) => {
      resolveOldAPut = resolve;
    });

    mockedFetch
      .mockResolvedValueOnce(homeBody("sA", "Site A", false)) // 0: home A (selection gen 0)
      .mockResolvedValueOnce(sourceBody("sA")) // 1: source A
      .mockReturnValueOnce(oldAPut) // 2: PUT A (old gen) — pending
      .mockResolvedValueOnce(homeBody("sB", "Site B", false)) // 3: home B
      .mockResolvedValueOnce(sourceBody("sB")) // 4: source B
      .mockResolvedValueOnce(homeBody("sA", "Site A", false)) // 5: home A again (new gen)
      .mockResolvedValueOnce(sourceBody("sA")); // 6: source A again

    render(<HomePage />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Enable monitoring" })).toBeInTheDocument(),
    );

    // Start a pending mutation for A.
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });
    expect(mockedFetch.mock.calls.filter(([p]) => p === "/product/sites/sA/monitoring")).toHaveLength(1);

    // Move to B.
    fireEvent.change(screen.getByLabelText(/Selected site/), { target: { value: "sB" } });
    await waitFor(() => expect(String(mockedFetch.mock.calls[4][0])).toContain("/product/source-health?site_id=sB"));

    // Return to A (newer generation) before the old A response resolves.
    fireEvent.change(screen.getByLabelText(/Selected site/), { target: { value: "sA" } });
    await waitFor(() => expect(String(mockedFetch.mock.calls[5][0])).toContain("site_id=sA"));
    await waitFor(() => expect(String(mockedFetch.mock.calls[6][0])).toContain("/product/source-health?site_id=sA"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Enable monitoring" })).toBeInTheDocument(),
    );

    // Open a fresh A dialog on the newer generation.
    fireEvent.click(screen.getByRole("button", { name: "Enable monitoring" }));
    expect(dialogEl()).not.toBeNull();
    expect(confirmButton()).not.toBeDisabled();

    // Resolve the OLD A mutation while the new A context is open.
    const callsBefore = mockedFetch.mock.calls.length;
    await act(async () => {
      resolveOldAPut(updateResponse("sA", true));
    });

    // The old completion must not close or reset the new A dialog…
    expect(document.getElementById("monitoring-dialog")).not.toBeNull();
    expect(confirmButton()).not.toBeDisabled();
    // …and must not trigger any refetch.
    expect(mockedFetch.mock.calls.length).toBe(callsBefore);
  });
});
