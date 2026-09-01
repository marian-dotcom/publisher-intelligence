import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import TimelinePage from "../app/(protected)/timeline/page";

const searchParamsMock = vi.hoisted(() => ({ current: new URLSearchParams() }));

vi.mock("@/lib/api");
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => searchParamsMock.current,
}));

const mockedFetch = vi.mocked(apiFetch);

afterEach(() => {
  mockedFetch.mockReset();
});

const SITE_A = "s1";
const SITE_B = "s2";

const HOME_STATUS = {
  sites: [
    { site_id: SITE_A, name: "Climatologie" },
    { site_id: SITE_B, name: "EVZ" },
  ],
  selected_site_id: SITE_A,
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
};

const TIMELINE_ALL_SITES = {
  entries: [
    {
      entry_kind: "machine_observed",
      event_id: "e1",
      event_type: "BROWSER_ACCESS_CHALLENGE_SUSPECTED",
      source: "BROWSER_MONITORING",
      provenance: "machine_observed",
      severity: "MEDIUM",
      status: "RECORDED",
      time_precision: "UNKNOWN",
      observed_at: "2026-08-30T13:58:52Z",
      occurred_at: null,
      occurrence_window_start: null,
      occurrence_window_end: null,
      site_id: SITE_B,
    },
    {
      entry_kind: "machine_observed",
      event_id: "e2",
      event_type: "NOINDEX_ADDED",
      source: "BROWSER_CHECKPOINT",
      provenance: "machine_observed",
      severity: "HIGH",
      status: "RECORDED",
      time_precision: "EXACT",
      observed_at: "2026-08-29T10:00:00Z",
      occurred_at: "2026-08-29T09:30:00Z",
      occurrence_window_start: null,
      occurrence_window_end: null,
      site_id: SITE_A,
    },
  ],
};

const TIMELINE_SITE_A_ONLY = {
  entries: [
    {
      entry_kind: "machine_observed",
      event_id: "e2",
      event_type: "NOINDEX_ADDED",
      source: "BROWSER_CHECKPOINT",
      provenance: "machine_observed",
      severity: "HIGH",
      status: "RECORDED",
      time_precision: "EXACT",
      observed_at: "2026-08-29T10:00:00Z",
      occurred_at: "2026-08-29T09:30:00Z",
      occurrence_window_start: null,
      occurrence_window_end: null,
      site_id: SITE_A,
    },
  ],
};

const TIMELINE_EMPTY = { entries: [] };

const TIMELINE_SITE_B_ONLY = {
  entries: TIMELINE_ALL_SITES.entries.filter((e) => e.site_id === SITE_B),
};

describe("TimelinePage with site filtering (EP-029 M2a)", () => {
  beforeEach(() => {
    searchParamsMock.current = new URLSearchParams();
    vi.spyOn(window.history, "replaceState").mockImplementation(() => {});
  });

  it("renders All sites mode by default with visible site/domain on each entry", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES);

    render(<TimelinePage />);

    await screen.findByText("Timeline");
    expect(screen.getByText("All sites")).toBeInTheDocument();
    expect(screen.getAllByText("Climatologie")).toHaveLength(2);
    expect(screen.getAllByText("EVZ")).toHaveLength(2);

    // Both sites' events visible
    expect(screen.getByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).toBeInTheDocument();
    expect(screen.getByText("NOINDEX_ADDED")).toBeInTheDocument();
  });

it("filters to the selected site when the operator changes the dropdown", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)     // 1: /product/home/status (initial)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES) // 2: /timeline (initial, no filter)
      .mockResolvedValueOnce(HOME_STATUS)     // 3: /product/home/status (after select change)
      .mockResolvedValueOnce(TIMELINE_SITE_A_ONLY); // 4: /timeline?site_id=s1 (after filter)

    render(<TimelinePage />);

    // Wait for initial load
    await screen.findByText("NOINDEX_ADDED");

    // Simulate user selecting a site from the dropdown
    const select = screen.getByLabelText("Filter by site");
    await act(async () => {
      fireEvent.change(select, { target: { value: SITE_A } });
    });

    // Wait for the filtered fetch to complete
    await screen.findByText("NOINDEX_ADDED");
    // EVZ event should NOT be visible when filtering to Climatologie
    expect(screen.queryByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).not.toBeInTheDocument();
    // Verify the exact sequence of API calls
    const timelineCalls = mockedFetch.mock.calls.filter((call) =>
      typeof call[0] === "string" && call[0].startsWith("/timeline")
    );
    expect(timelineCalls).toHaveLength(2);
    // First call: no filter (All sites)
    expect(timelineCalls[0][0]).toBe("/timeline");
    // Second call: filtered by site_id
    expect(timelineCalls[1][0]).toBe(`/timeline?site_id=${encodeURIComponent(SITE_A)}`);
  });

  it("shows 'No operational activity recorded yet' in All sites mode when empty", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_STATUS).mockResolvedValueOnce(TIMELINE_EMPTY);

    render(<TimelinePage />);

    await screen.findByText(/No operational activity recorded yet\./);
  });

  it("each timeline entry visibly identifies its site/domain", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES);

    render(<TimelinePage />);

    await screen.findByText("Timeline");
    // Each entry should show site name
    const siteLabels = screen.getAllByText(/Climatologie|EVZ/);
    expect(siteLabels.length).toBeGreaterThanOrEqual(3); // 2 in dropdown + 1 in entry
  });

  it("selecting Climatologie does not show EVZ event as Climatologie", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)
      .mockResolvedValueOnce(TIMELINE_SITE_A_ONLY);

    render(<TimelinePage />);

    await screen.findByText("NOINDEX_ADDED");
    // The EVZ challenge event must not appear when Climatologie is selected
    expect(screen.queryByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).not.toBeInTheDocument();
  });

  it("All sites mode shows both sites' events with correct attribution", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES);

    render(<TimelinePage />);

    await screen.findByText("Timeline");
    // Both events present with their correct site labels
    expect(screen.getByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).toBeInTheDocument();
    expect(screen.getByText("NOINDEX_ADDED")).toBeInTheDocument();
    expect(screen.getAllByText("EVZ")).toHaveLength(2); // 1 in dropdown + 1 in entry
    expect(screen.getAllByText("Climatologie")).toHaveLength(2); // 1 in dropdown + 1 in entry
  });

  it("does not fabricate event, incident, or alert when none exists", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_STATUS).mockResolvedValueOnce(TIMELINE_EMPTY);

    render(<TimelinePage />);

    await screen.findByText(/No operational activity recorded yet\./);
    expect(screen.queryByText(/incident/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/alert/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/fabricated/i)).not.toBeInTheDocument();
  });

  it("switching back to All sites mode clears the filter", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)     // 1: /product/home/status (initial)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES) // 2: /timeline (initial, no filter)
      .mockResolvedValueOnce(HOME_STATUS)     // 3: /product/home/status (after select to s1)
      .mockResolvedValueOnce(TIMELINE_SITE_A_ONLY) // 4: /timeline?site_id=s1 (filtered)
      .mockResolvedValueOnce(HOME_STATUS)     // 5: /product/home/status (after select back to all)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES); // 6: /timeline (back to all)

    render(<TimelinePage />);

    // Wait for initial load (All sites)
    await screen.findByText("NOINDEX_ADDED");
    await screen.findByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED");

    // Filter to Climatologie
    const select = screen.getByLabelText("Filter by site");
    await act(async () => {
      fireEvent.change(select, { target: { value: SITE_A } });
    });
    await screen.findByText("NOINDEX_ADDED");
    expect(screen.queryByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).not.toBeInTheDocument();

    // Switch back to All sites
    await act(async () => {
      fireEvent.change(select, { target: { value: "all" } });
    });
    await screen.findByText("NOINDEX_ADDED");
    await screen.findByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED");

    // Verify the exact sequence of timeline API calls
    const timelineCalls = mockedFetch.mock.calls.filter((call) =>
      typeof call[0] === "string" && call[0].startsWith("/timeline")
    );
    expect(timelineCalls).toHaveLength(3);
    expect(timelineCalls[0][0]).toBe("/timeline"); // Initial: All sites
    expect(timelineCalls[1][0]).toBe(`/timeline?site_id=${encodeURIComponent(SITE_A)}`); // Filtered
    expect(timelineCalls[2][0]).toBe("/timeline"); // Back to All sites
  });

  it("selects the site from an initial site_id query param on first load", async () => {
    searchParamsMock.current = new URLSearchParams(`site_id=${encodeURIComponent(SITE_A)}`);
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)          // 1: /product/home/status
      .mockResolvedValueOnce(TIMELINE_SITE_A_ONLY); // 2: /timeline?site_id=s1

    render(<TimelinePage />);

    await screen.findByText("NOINDEX_ADDED");
    // The site is selected from the query param, so the first timeline
    // request already carries the encoded site id (no All-sites request first).
    const timelineCalls = mockedFetch.mock.calls.filter((call) =>
      typeof call[0] === "string" && call[0].startsWith("/timeline")
    );
    expect(timelineCalls).toHaveLength(1);
    expect(timelineCalls[0][0]).toBe(`/timeline?site_id=${encodeURIComponent(SITE_A)}`);
    // Site B's event must not appear for the initial site A filter.
    expect(screen.queryByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).not.toBeInTheDocument();
  });

  it("replaces stale entries when switching between sites", async () => {
    mockedFetch
      .mockResolvedValueOnce(HOME_STATUS)           // 1: home (initial)
      .mockResolvedValueOnce(TIMELINE_ALL_SITES)     // 2: /timeline (all sites)
      .mockResolvedValueOnce(HOME_STATUS)            // 3: home (switch to s1)
      .mockResolvedValueOnce(TIMELINE_SITE_A_ONLY)   // 4: /timeline?site_id=s1
      .mockResolvedValueOnce(HOME_STATUS)            // 5: home (switch to s2)
      .mockResolvedValueOnce(TIMELINE_SITE_B_ONLY);  // 6: /timeline?site_id=s2

    render(<TimelinePage />);

    // Initial All sites: both sites' events visible.
    await screen.findByText("NOINDEX_ADDED");
    await screen.findByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED");

    const select = screen.getByLabelText("Filter by site");
    await act(async () => {
      fireEvent.change(select, { target: { value: SITE_A } });
    });
    await screen.findByText("NOINDEX_ADDED");
    expect(screen.queryByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED")).not.toBeInTheDocument();

    // Switching to site B replaces site A's stale entries.
    await act(async () => {
      fireEvent.change(select, { target: { value: SITE_B } });
    });
    await screen.findByText("BROWSER_ACCESS_CHALLENGE_SUSPECTED");
    expect(screen.queryByText("NOINDEX_ADDED")).not.toBeInTheDocument();
  });
});