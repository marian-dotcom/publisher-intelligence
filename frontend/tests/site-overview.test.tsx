import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "../app/(protected)/page";
import SiteOverviewPage from "../app/(protected)/sites/[site_id]/page";
import { apiFetch, ApiError } from "@/lib/api";
import type {
  HomeStatus,
  MonitoringProjection,
  SiteOverviewRecentRun,
  SiteOverviewResponse,
  SourceHealth,
  SourceHealthResponse,
  SourceKey,
} from "@/lib/api-types";

const authMocks = vi.hoisted(() => ({
  useAuth: vi.fn(),
}));

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
}));

const paramsMock = vi.hoisted(() => ({
  current: { site_id: "s1" } as Record<string, string | undefined>,
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    apiFetch: vi.fn(),
  };
});
vi.mock("@/lib/auth-client", () => ({
  useAuth: authMocks.useAuth,
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerMocks.push }),
  useParams: () => paramsMock.current,
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

const SITE_ID = "s1";

const ALL_UNKNOWN: Record<SourceKey, SourceHealth> = {
  BROWSER_MONITORING: "UNKNOWN",
  GA4: "UNKNOWN",
  GSC: "UNKNOWN",
  GAM: "UNKNOWN",
  PUBLIC_CONFIG: "UNKNOWN",
};

function monitoring(over: Partial<MonitoringProjection> = {}): MonitoringProjection {
  return {
    site_id: SITE_ID,
    enabled: false,
    monitoring_state_updated_at: null,
    cadence: { identifier: "six-hour", hours: 6 },
    next_scheduled_for: null,
    in_flight_scheduled_run_status: null,
    ...over,
  };
}

const BASE_OVERVIEW: SiteOverviewResponse = {
  site: {
    site_id: SITE_ID,
    name: "Climatologie Déploiement",
    canonical_domain: "climatologie.ro",
    canonical_scheme: "https",
    url: "https://climatologie.ro",
    publisher_name: "Climatologie",
    status: "ACTIVE",
    timezone: "Europe/Bucharest",
    created_at: "2026-08-15T10:00:00Z",
  },
  monitoring: monitoring({ enabled: true }),
  initial_diagnostic: {
    run_id: "diag-1",
    status: "COMPLETE",
    completed_at: "2026-08-16T12:00:00Z",
    browser_access_classification: "ok",
  },
  latest_scheduled_run: {
    run_id: "run-1",
    status: "COMPLETE",
    started_at: "2026-09-14T06:00:00Z",
    completed_at: "2026-09-14T06:05:00Z",
    attempt_count: 1,
    browser_access_classification: "ok",
  },
  source_health: { ...ALL_UNKNOWN, BROWSER_MONITORING: "HEALTHY" },
  browser_monitoring_detail: null,
  open_incidents: [],
  recent_runs: [],
  recent_activity: [],
};

function overview(mon: MonitoringProjection | null): SiteOverviewResponse {
  return { ...BASE_OVERVIEW, monitoring: mon };
}

// M3 panel variants — shallow overrides on the contract-typed BASE projection.
function overviewM3(
  over: Partial<
    Pick<
      SiteOverviewResponse,
      "site" | "monitoring" | "initial_diagnostic" | "latest_scheduled_run" | "recent_runs"
    >
  > = {},
): SiteOverviewResponse {
  return { ...BASE_OVERVIEW, ...over };
}

function diagnostic(
  over: Partial<NonNullable<SiteOverviewResponse["initial_diagnostic"]>> = {},
): NonNullable<SiteOverviewResponse["initial_diagnostic"]> {
  return { ...BASE_OVERVIEW.initial_diagnostic!, ...over };
}

function scheduledRun(
  over: Partial<NonNullable<SiteOverviewResponse["latest_scheduled_run"]>> = {},
): NonNullable<SiteOverviewResponse["latest_scheduled_run"]> {
  return { ...BASE_OVERVIEW.latest_scheduled_run!, ...over };
}

function recentRun(over: Partial<SiteOverviewRecentRun> = {}): SiteOverviewRecentRun {
  return {
    run_id: "r1",
    observation_kind: "SCHEDULED",
    status: "COMPLETE",
    started_at: "2026-09-13T00:00:00Z",
    completed_at: "2026-09-13T00:05:00Z",
    limitations: [],
    ...over,
  };
}

// Scope queries to a single overview card, keyed by its h2 title.
function card(title: string) {
  const heading = screen.getByRole("heading", { level: 2, name: title });
  return within(heading.closest(".card") as HTMLElement);
}

function confirmButton() {
  // jsdom's stubbed <dialog>.showModal is a no-op, so role queries inside the
  // dialog report no accessible roles; the confirm action is the last of the
  // two dialog-actions buttons (matching monitoring-controls test convention).
  return document.querySelector(
    "#monitoring-dialog .dialog-actions button:last-child",
  ) as HTMLButtonElement;
}

function homeBody(siteId: string, name: string, enabled: boolean): HomeStatus {
  return {
    sites: [{ site_id: siteId, name }],
    selected_site_id: siteId,
    publisher_site_condition: "ACTIVE",
    source_health: { ...ALL_UNKNOWN },
    initial_diagnostic: null,
    open_incident_count: 0,
    monetization_capability: "UNKNOWN",
    monitoring: monitoring({ enabled }),
  };
}

function sourceBody(siteId: string): SourceHealthResponse {
  return { site_id: siteId, sources: { ...ALL_UNKNOWN } };
}

beforeEach(() => {
  mockedFetch.mockReset();
  authMocks.useAuth.mockReset();
  authMocks.useAuth.mockReturnValue(session("ADMIN"));
  routerMocks.push.mockReset();
  paramsMock.current = { site_id: "s1" };
});

afterEach(() => {
  authMocks.useAuth.mockReset();
});

describe("SiteOverviewPage · identity header", () => {
  it("renders site identity from the overview fixture", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByText("Climatologie Déploiement");
    expect(screen.getByText("https://climatologie.ro")).toBeInTheDocument();
    expect(screen.getByText("Climatologie")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE")).toBeInTheDocument();
    expect(screen.getByText("Europe/Bucharest")).toBeInTheDocument();
    expect(screen.getByText("Registered")).toBeInTheDocument();
  });

  it("requests the overview endpoint for the route site_id", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByText("Climatologie Déploiement");
    expect(mockedFetch).toHaveBeenCalledWith("/product/sites/s1/overview");
  });

it("encodes nontrivial site ids in the overview API path", async () => {
    const siteId = "a b+c/d";
    const encoded = encodeURIComponent(siteId);
    paramsMock.current = { site_id: siteId };
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByText("Automatic monitoring");
    expect(mockedFetch).toHaveBeenCalledWith(`/product/sites/${encoded}/overview`);
    expect(mockedFetch).not.toHaveBeenCalledWith(`/product/sites/${siteId}/overview`);
  });
});

describe("SiteOverviewPage · monitoring card states", () => {
  it("renders Monitoring active for an enabled projection", async () => {
    mockedFetch.mockResolvedValueOnce(overview(monitoring({ enabled: true })));

    render(<SiteOverviewPage />);

    await screen.findByText("Monitoring active");
    expect(screen.getByText(/Every 6 hours/)).toBeInTheDocument();
  });

  it("renders Paused for OFF with no in-flight run", async () => {
    mockedFetch.mockResolvedValueOnce(overview(monitoring({ enabled: false })));

    render(<SiteOverviewPage />);

    await screen.findByText("Paused");
    expect(screen.getByText("No automatic checks will start.")).toBeInTheDocument();
  });

  it("renders Paused — current check finishing for OFF with an in-flight run", async () => {
    mockedFetch.mockResolvedValueOnce(
      overview(monitoring({ enabled: false, in_flight_scheduled_run_status: "RUNNING" })),
    );

    render(<SiteOverviewPage />);

    await screen.findByText("Paused — current check finishing");
  });

  it("renders Monitoring state unavailable (fail-closed) for a null projection", async () => {
    mockedFetch.mockResolvedValueOnce(overview(null));

    render(<SiteOverviewPage />);

    await screen.findByText("Monitoring state unavailable");
    expect(screen.getByText("Automatic monitoring is treated as paused.")).toBeInTheDocument();
    // No monitoring mutation is offered for an unavailable read (the M3
    // diagnostic deep link is read-only navigation, not a mutation).
    expect(screen.queryByRole("button", { name: "Enable monitoring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause monitoring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run diagnostic now/ })).not.toBeInTheDocument();
  });
});

describe("SiteOverviewPage · ADMIN vs OPERATOR monitoring gating", () => {
  it("shows the ADMIN enable affordance for a paused site", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockResolvedValueOnce(overview(monitoring({ enabled: false })));

    render(<SiteOverviewPage />);

    await screen.findByRole("button", { name: "Enable monitoring" });
  });

  it("shows the ADMIN pause affordance for an active site", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch.mockResolvedValueOnce(overview(monitoring({ enabled: true })));

    render(<SiteOverviewPage />);

    await screen.findByRole("button", { name: "Pause monitoring" });
  });

  it("does not expose any mutation to an OPERATOR", async () => {
    authMocks.useAuth.mockReturnValue(session("OPERATOR"));
    mockedFetch.mockResolvedValueOnce(overview(monitoring({ enabled: false })));

    render(<SiteOverviewPage />);

    await screen.findByText("Paused");
    expect(screen.queryByRole("button", { name: "Enable monitoring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause monitoring" })).not.toBeInTheDocument();
  });

  it("refetches the overview after a successful ADMIN enable", async () => {
    authMocks.useAuth.mockReturnValue(session("ADMIN"));
    mockedFetch
      .mockResolvedValueOnce(overview(monitoring({ enabled: false }))) // 0: initial GET
      .mockResolvedValueOnce(monitoring({ enabled: true })) // 1: PUT response
      .mockResolvedValueOnce(overview(monitoring({ enabled: true }))); // 2: refetch GET

    render(<SiteOverviewPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Enable monitoring" }));
    await act(async () => {
      fireEvent.click(confirmButton());
    });

    expect(mockedFetch.mock.calls[1][0]).toBe("/product/sites/s1/monitoring");
    expect(mockedFetch.mock.calls[1][1]).toMatchObject({ method: "PUT", body: { enabled: true } });
    expect(mockedFetch.mock.calls[2][0]).toBe("/product/sites/s1/overview");
    await waitFor(() => expect(screen.getByText("Monitoring active")).toBeInTheDocument());
  });
});

describe("SiteOverviewPage · loading / error / stale drives", () => {
  it("shows loading state while the overview request is pending", async () => {
    mockedFetch.mockImplementation(() => new Promise(() => {}));

    render(<SiteOverviewPage />);

    expect(screen.getByText("Loading site overview…")).toBeInTheDocument();
  });

  it("shows a not-found error state for 404", async () => {
    mockedFetch.mockRejectedValue(new ApiError("not_found", 404, "Request failed: 404"));

    render(<SiteOverviewPage />);

    await screen.findByText(/Site not found/);
  });

  it("shows an authentication error state for 401", async () => {
    mockedFetch.mockRejectedValue(new ApiError("unauthorized", 401, "Request failed: 401"));

    render(<SiteOverviewPage />);

    await screen.findByText(/Authentication required/);
  });

  it("shows an access-denied error state for 403", async () => {
    mockedFetch.mockRejectedValue(new ApiError("forbidden", 403, "Request failed: 403"));

    render(<SiteOverviewPage />);

    await screen.findByText(/Access denied/);
  });

  it("shows a bounded error state for server/network failures", async () => {
    mockedFetch.mockRejectedValue(new TypeError("network"));

    render(<SiteOverviewPage />);

    await screen.findByText(/Could not load site overview\. Try again\./);
  });

  it("does not leak stale overview data when the route site_id changes", async () => {
    mockedFetch
      .mockResolvedValueOnce(overview(monitoring({ enabled: true }))) // s1
      .mockResolvedValueOnce({
        ...overview(monitoring({ enabled: true })),
        site: { ...BASE_OVERVIEW.site, site_id: "s2", name: "Other Site" },
      }); // s2

    const { rerender } = render(<SiteOverviewPage />);
    await screen.findByText("Climatologie Déploiement");

    paramsMock.current = { site_id: "s2" };
    rerender(<SiteOverviewPage />);

    await screen.findByText("Other Site");
    expect(screen.queryByText("Climatologie Déploiement")).not.toBeInTheDocument();
  });

  it("shows an explicit unavailable state when the site_id param is missing", async () => {
    paramsMock.current = {};
    render(<SiteOverviewPage />);

    await screen.findByText(/Select a site to view its overview\./);
    expect(mockedFetch).not.toHaveBeenCalled();
  });
});

describe("SiteOverviewPage · M3 panels and M4 boundary", () => {
  it("renders the three M3 result panels", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    expect(screen.getByRole("heading", { level: 2, name: "Latest scheduled" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Recent runs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /View diagnostic results/ })).toBeInTheDocument();
  });

  it("renders no M4 content in the M3 shell", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    expect(screen.queryByRole("heading", { level: 2, name: /source health/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /browser monitoring detail/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /publisher condition/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /open incidents/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /recent activity/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /deep links/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /evidence pack/i })).not.toBeInTheDocument();
  });
});

describe("SiteOverviewPage · latest diagnostic panel", () => {
  it("renders the diagnostic state, access classification, and completed time", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    expect(card("Latest diagnostic").getByText("Diagnostic complete")).toBeInTheDocument();
    expect(card("Latest diagnostic").getByText("Access: normal")).toBeInTheDocument();
    expect(card("Latest diagnostic").getByText("Completed")).toBeInTheDocument();
    expect(
      card("Latest diagnostic").getByTestId("latest-diagnostic-completed").textContent,
    ).toMatch(/\d{1,2}:\d{2}/);
  });

  it("shows a neutral empty state when no diagnostic exists", async () => {
    mockedFetch.mockResolvedValueOnce(overviewM3({ initial_diagnostic: null }));

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    expect(card("Latest diagnostic").getByText("No diagnostic yet")).toBeInTheDocument();
    // Absence is neutral — never rendered as unhealthy/failed.
    expect(card("Latest diagnostic").queryByText(/fail|unhealthy|down|error/i)).not.toBeInTheDocument();
    expect(card("Latest diagnostic").queryByRole("button")).not.toBeInTheDocument();
  });

  it("deep links to diagnostic results only for a terminal diagnostic", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    fireEvent.click(card("Latest diagnostic").getByRole("button", { name: /View diagnostic results/ }));
    expect(routerMocks.push).toHaveBeenCalledWith("/diagnostic-results?site_id=s1");
    expect(routerMocks.push).not.toHaveBeenCalledWith("/diagnostic-results");
  });

  it("renders no deep link or run action for a non-terminal diagnostic", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({
        initial_diagnostic: diagnostic({
          status: "RUNNING",
          completed_at: null,
          browser_access_classification: null,
        }),
      }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    expect(card("Latest diagnostic").getByText("Diagnostic running")).toBeInTheDocument();
    expect(card("Latest diagnostic").queryByText(/Access:/)).not.toBeInTheDocument();
    expect(card("Latest diagnostic").queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run diagnostic now/ })).not.toBeInTheDocument();
  });

  it("encodes the site id in the diagnostic deep link", async () => {
    const siteId = "a b+c/d";
    paramsMock.current = { site_id: siteId };
    mockedFetch.mockResolvedValueOnce(
      overviewM3({ site: { ...BASE_OVERVIEW.site, site_id: siteId } }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    fireEvent.click(card("Latest diagnostic").getByRole("button", { name: /View diagnostic results/ }));
    expect(routerMocks.push).toHaveBeenCalledWith(
      `/diagnostic-results?site_id=${encodeURIComponent(siteId)}`,
    );
  });

  it("renders a FAILED diagnostic explicitly as failed", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({ initial_diagnostic: diagnostic({ status: "SITE_ERROR" }) }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest diagnostic" });
    expect(card("Latest diagnostic").getByText("Diagnostic failed")).toBeInTheDocument();
  });
});

describe("SiteOverviewPage · latest scheduled panel", () => {
  it("renders the latest scheduled run status and timestamp", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest scheduled" });
    expect(card("Latest scheduled").getByText("COMPLETE")).toBeInTheDocument();
    expect(card("Latest scheduled").getByText("Access: normal")).toBeInTheDocument();
    expect(card("Latest scheduled").getByText("Attempts")).toBeInTheDocument();
    expect(
      card("Latest scheduled").getByTestId("latest-scheduled-completed").textContent,
    ).toMatch(/\d{1,2}:\d{2}/);
  });

  it("shows a neutral empty state and never substitutes a diagnostic run", async () => {
    mockedFetch.mockResolvedValueOnce(overviewM3({ latest_scheduled_run: null }));

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest scheduled" });
    const scheduled = card("Latest scheduled");
    expect(scheduled.getByText("No scheduled results yet")).toBeInTheDocument();
    expect(scheduled.queryByText(/Diagnostic|COMPLETE/)).not.toBeInTheDocument();
  });

  it("does not surface SKIPPED in the latest scheduled card", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({
        latest_scheduled_run: scheduledRun({ status: "COMPLETE" }),
        recent_runs: [
          recentRun({ run_id: "skip-1", status: "SKIPPED", limitations: ["monitoring paused"] }),
        ],
      }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Latest scheduled" });
    const scheduled = card("Latest scheduled");
    expect(scheduled.getByText("COMPLETE")).toBeInTheDocument();
    expect(scheduled.queryByText(/Skipped/)).not.toBeInTheDocument();
  });
});

describe("SiteOverviewPage · recent runs panel", () => {
  it("renders mixed run kinds with distinct kind labels and statuses", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({
        recent_runs: [
          recentRun({ run_id: "sched-1", observation_kind: "SCHEDULED", status: "COMPLETE" }),
          recentRun({ run_id: "diag-1", observation_kind: "DIAGNOSTIC", status: "PARTIAL" }),
          recentRun({ run_id: "inc-1", observation_kind: "INCIDENT_DIAGNOSTIC", status: "COMPLETE" }),
        ],
      }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    const runs = card("Recent runs");
    expect(runs.getByText("Scheduled")).toBeInTheDocument();
    expect(runs.getByText("Diagnostic")).toBeInTheDocument();
    expect(runs.getByText("Incident diagnostic")).toBeInTheDocument();
    expect(runs.getAllByText("COMPLETE")).toHaveLength(2);
    expect(runs.getByText("PARTIAL")).toBeInTheDocument();
    expect(runs.getAllByText(/\d{1,2}:\d{2}/).length).toBeGreaterThan(0);
  });

  it("keeps diagnostic and scheduled cohorts distinct", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({ recent_runs: [recentRun({ run_id: "diag-1", observation_kind: "DIAGNOSTIC" })] }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    const runs = card("Recent runs");
    expect(runs.getByText("Diagnostic")).toBeInTheDocument();
    expect(runs.queryByText("Scheduled")).not.toBeInTheDocument();
  });

  it("renders SKIPPED neutrally with limitation text and no failure tone", async () => {
    mockedFetch.mockResolvedValueOnce(
      overviewM3({
        recent_runs: [
          recentRun({
            run_id: "skip-1",
            status: "SKIPPED",
            limitations: ["monitoring paused for scheduled checks"],
          }),
        ],
      }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    const runs = card("Recent runs");
    expect(runs.getByText("Skipped — monitoring paused")).toBeInTheDocument();
    expect(runs.getByText("monitoring paused for scheduled checks")).toBeInTheDocument();
    expect(runs.queryByText("SKIPPED")).not.toBeInTheDocument();
    expect(runs.queryByText(/fail|unhealthy|down|error/i)).not.toBeInTheDocument();
  });

  it("renders an empty recent runs state", async () => {
    mockedFetch.mockResolvedValueOnce(overviewM3({ recent_runs: [] }));

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    expect(card("Recent runs").getByText("No runs yet")).toBeInTheDocument();
  });
});

describe("SiteOverviewPage · M3 panel data freshness", () => {
  it("does not leak stale panel data when the route site_id changes", async () => {
    mockedFetch
      .mockResolvedValueOnce(BASE_OVERVIEW) // s1
      .mockResolvedValueOnce(
        overviewM3({
          site: { ...BASE_OVERVIEW.site, site_id: "s2", name: "Other Site" },
          initial_diagnostic: diagnostic({
            run_id: "diag-2",
            status: "SITE_ERROR",
            browser_access_classification: "degraded",
          }),
          recent_runs: [
            recentRun({ run_id: "run-2", observation_kind: "DIAGNOSTIC", status: "COMPLETE" }),
          ],
        }),
      ); // s2

    const { rerender } = render(<SiteOverviewPage />);
    await screen.findByText("Diagnostic complete");

    paramsMock.current = { site_id: "s2" };
    rerender(<SiteOverviewPage />);

    await screen.findByText("Diagnostic failed");
    const diagnosticCard = card("Latest diagnostic");
    expect(diagnosticCard.queryByText("Diagnostic complete")).not.toBeInTheDocument();
    expect(diagnosticCard.queryByText("Access: normal")).not.toBeInTheDocument();
    expect(diagnosticCard.getByText("Access: degraded")).toBeInTheDocument();
    expect(card("Recent runs").getByText("Diagnostic")).toBeInTheDocument();
  });
});

describe("SiteOverviewPage · OPERATOR/ADMIN result parity", () => {
  it("shows the same read-only M3 result panels to an OPERATOR", async () => {
    authMocks.useAuth.mockReturnValue(session("OPERATOR"));
    mockedFetch.mockResolvedValueOnce(
      overviewM3({
        monitoring: monitoring({ enabled: false }),
        recent_runs: [
          recentRun({ run_id: "sched-1", observation_kind: "SCHEDULED", status: "COMPLETE" }),
          recentRun({ run_id: "skip-1", observation_kind: "SCHEDULED", status: "SKIPPED" }),
        ],
      }),
    );

    render(<SiteOverviewPage />);

    await screen.findByRole("heading", { level: 2, name: "Recent runs" });
    expect(card("Latest diagnostic").getByText("Diagnostic complete")).toBeInTheDocument();
    expect(card("Latest scheduled").getByText("COMPLETE")).toBeInTheDocument();
    expect(card("Recent runs").getAllByText("Scheduled")).toHaveLength(2);
    expect(card("Recent runs").getByText("Skipped — monitoring paused")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enable monitoring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pause monitoring" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Run diagnostic now/ })).not.toBeInTheDocument();
  });
});

describe("Home · Overview entry point", () => {
  it("renders an Overview button for the selected site and deep links to /sites/<id>", async () => {
    mockedFetch
      .mockResolvedValueOnce(homeBody("s1", "Climatologie Déploiement", false))
      .mockResolvedValueOnce(sourceBody("s1"));

    render(<HomePage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(routerMocks.push).toHaveBeenCalledWith("/sites/s1");
  });

  it("encodes the selected site id in the Overview deep link", async () => {
    const siteId = "a b+c/d";
    mockedFetch
      .mockResolvedValueOnce(homeBody(siteId, "Site A", false))
      .mockResolvedValueOnce(sourceBody(siteId));

    render(<HomePage />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(routerMocks.push).toHaveBeenCalledWith(`/sites/${encodeURIComponent(siteId)}`);
  });

  it("renders no Overview button when no site is selected", async () => {
    mockedFetch
      .mockResolvedValueOnce({ ...homeBody("s1", "Site A", false), selected_site_id: null, monitoring: null });

    render(<HomePage />);

    await screen.findByLabelText(/Selected site/);
    expect(screen.queryByRole("button", { name: "Overview" })).not.toBeInTheDocument();
  });
});