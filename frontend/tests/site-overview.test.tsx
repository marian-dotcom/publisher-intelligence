import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "../app/(protected)/page";
import SiteOverviewPage from "../app/(protected)/sites/[site_id]/page";
import { apiFetch, ApiError } from "@/lib/api";
import type {
  HomeStatus,
  MonitoringProjection,
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
    // No mutation is offered for an unavailable read.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
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

describe("SiteOverviewPage · M2 shell boundary", () => {
  it("renders no M3/M4 panel content", async () => {
    mockedFetch.mockResolvedValueOnce(BASE_OVERVIEW);

    render(<SiteOverviewPage />);

    await screen.findByText("Climatologie Déploiement");
    expect(screen.queryByRole("heading", { level: 2, name: /diagnostic/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /scheduled/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /recent runs/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /source health/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /open incidents/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2, name: /recent activity/i })).not.toBeInTheDocument();
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