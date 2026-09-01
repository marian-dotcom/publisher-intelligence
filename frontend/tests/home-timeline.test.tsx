import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import HomePage from "../app/(protected)/page";
import TimelinePage from "../app/(protected)/timeline/page";

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
  searchParams: { current: new URLSearchParams() },
}));

vi.mock("@/lib/api");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerMocks.push }),
  useSearchParams: () => routerMocks.searchParams.current,
}));

const mockedFetch = vi.mocked(apiFetch);

afterEach(() => {
  mockedFetch.mockReset();
  routerMocks.push.mockClear();
});

const HOME_BODY = {
  sites: [{ site_id: "s1", name: "News Daily" }],
  selected_site_id: "s1",
  publisher_site_condition: "ACTIVE",
  source_health: {
    BROWSER_MONITORING: "DEGRADED",
    GA4: "HEALTHY",
    GSC: "UNKNOWN",
    GAM: "UNKNOWN",
  },
  initial_diagnostic: null,
  open_incident_count: 2,
  monetization_capability: "RELATIVE_ONLY",
};

const SOURCE_BODY = {
  site_id: "s1",
  sources: {
    BROWSER_MONITORING: "DEGRADED",
    GA4: "HEALTHY",
    GSC: "UNKNOWN",
    GAM: "UNKNOWN",
  },
};

function homeBodyWithDiagnostic(status: string) {
  return {
    ...HOME_BODY,
    initial_diagnostic: { status, browser_access_classification: null },
  };
}

describe("HomePage", () => {
  it("renders site condition and source health as independent sections", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_BODY).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    await screen.findByText("Publisher/site: ACTIVE");
    // Degraded source stays at source level; the site condition is untouched.
    expect(screen.getByText(/Browser Monitoring · DEGRADED/)).toBeInTheDocument();
    expect(screen.getByText("Publisher/site: ACTIVE")).toBeInTheDocument();
    expect(screen.getByText(/relative metrics only/i)).toBeInTheDocument();
    expect(screen.getByText(/Open incidents: 2/)).toBeInTheDocument();
  });

  it("shows an enabled View diagnostic results action for a COMPLETE diagnostic", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("COMPLETE")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    expect(button).toBeEnabled();
  });

  it("shows an enabled View diagnostic results action for a SITE_ERROR diagnostic", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("SITE_ERROR")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    expect(button).toBeEnabled();
  });

  it("shows an enabled View diagnostic results action for a PARTIAL diagnostic", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("PARTIAL")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    expect(button).toBeEnabled();
  });

  it("disables the View diagnostic results action while the diagnostic is PENDING", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("PENDING")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    expect(button).toBeDisabled();
  });

  it("disables the View diagnostic results action while the diagnostic is RUNNING", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("RUNNING")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    expect(button).toBeDisabled();
  });

  it("shows no diagnostic navigation action when no initial diagnostic exists", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_BODY).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    await screen.findByText("Publisher/site: ACTIVE");
    expect(screen.queryByRole("button", { name: "View diagnostic results" })).not.toBeInTheDocument();
  });

  it("pushes the exact encoded diagnostic-results URL on click", async () => {
    mockedFetch.mockResolvedValueOnce(homeBodyWithDiagnostic("COMPLETE")).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    const button = await screen.findByRole("button", { name: "View diagnostic results" });
    await act(async () => {
      fireEvent.click(button);
    });
    expect(routerMocks.push).toHaveBeenCalledWith(
      `/diagnostic-results?site_id=${encodeURIComponent("s1")}`,
    );
  });
});

describe("TimelinePage", () => {
  beforeEach(() => {
    // TimelinePage now fetches /product/home/status first for site list
    mockedFetch.mockResolvedValueOnce(HOME_BODY);
  });

  it("renders exact, bounded and unknown occurrence semantics distinctly", async () => {
    mockedFetch.mockResolvedValue({
      entries: [
        {
          entry_kind: "machine_observed",
          event_id: "e1",
          event_type: "NOINDEX_ADDED",
          source: "BROWSER_CHECKPOINT",
          provenance: "machine_observed",
          severity: "HIGH",
          status: "RECORD",
          time_precision: "EXACT",
          observed_at: "2026-08-20T10:00:00+00:00",
          occurred_at: "2026-08-20T09:30:00+00:00",
          occurrence_window_start: null,
          occurrence_window_end: null,
          site_id: "s1",
        },
        {
          entry_kind: "machine_observed",
          event_id: "e2",
          event_type: "CMP_BLOCKED",
          source: "BROWSER_CHECKPOINT",
          provenance: "machine_observed",
          severity: null,
          status: "RECORD",
          time_precision: "WINDOW",
          observed_at: "2026-08-20T12:00:00+00:00",
          occurred_at: null,
          occurrence_window_start: "2026-08-20T08:00:00+00:00",
          occurrence_window_end: "2026-08-20T11:00:00+00:00",
          site_id: "s1",
        },
        {
          entry_kind: "human_reported",
          note_id: "n1",
          note_type: "OPERATOR_NOTE",
          provenance: "human_reported",
          source: "OPERATOR",
          observed_at: "2026-08-21T09:00:00+00:00",
          occurred_at: null,
          text: "Revenue looked off since Monday.",
          site_id: "s1",
        },
      ],
    });

    render(<TimelinePage />);

    // EXACT renders occurred time; WINDOW renders bounded phrasing.
    await screen.findByText(/^Occurred at /);
    expect(screen.getByText(/^Occurred between/)).toBeInTheDocument();
    // Human provenance is visibly distinct from machine.
    expect(screen.getByText("Human reported")).toBeInTheDocument();
    expect(screen.getAllByText("Machine observed").length).toBe(2);
    expect(screen.getByText(/Revenue looked off since Monday\./)).toBeInTheDocument();
  });

  it("renders an empty state when no operational activity exists", async () => {
    mockedFetch.mockResolvedValue({ entries: [] });

    render(<TimelinePage />);
    await screen.findByText(/No operational activity recorded yet\./);
  });

  it("never substitutes observed_at for a missing occurred_at", async () => {
    mockedFetch.mockResolvedValue({
      entries: [
        {
          entry_kind: "machine_observed",
          event_id: "e3",
          event_type: "SOMETHING",
          source: "BROWSER_CHECKPOINT",
          provenance: "machine_observed",
          severity: null,
          status: "RECORD",
          time_precision: "UNKNOWN",
          observed_at: "2026-08-22T09:00:00+00:00",
          occurred_at: null,
          occurrence_window_start: null,
          occurrence_window_end: null,
          site_id: "s1",
        },
      ],
    });

    render(<TimelinePage />);
    await screen.findByText("Occurrence time not established");
  });
});
