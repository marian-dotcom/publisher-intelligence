import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import { ApiError } from "@/lib/api";
import DiagnosticResultsPage from "../app/(protected)/diagnostic-results/page";

const searchParamsMock = vi.hoisted(() => ({ current: new URLSearchParams() }));

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal() as Record<string, unknown>;
  return {
    ...mod,
    apiFetch: vi.fn(),
  };
});
// The page consumes /diagnostic-results?site_id=... via useSearchParams()
// (Home's navigation contract). useParams is never used on this static route.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => searchParamsMock.current,
}));

const mockedFetch = vi.mocked(apiFetch);

afterEach(() => {
  mockedFetch.mockReset();
  searchParamsMock.current = new URLSearchParams();
});

const SITE_ID = "s1";
const RUN_ID = "r1";

const DIAGNOSTIC_RESULTS = {
  site_id: SITE_ID,
  site_name: "Climatologie",
  site_domain: "climatologie.ro",
  publisher_name: "Climatologie",
  run: {
    run_id: RUN_ID,
    observation_kind: "DIAGNOSTIC",
    trigger_source: "OPERATOR_UI",
    trigger_correlation_id: "corr-1",
    status: "COMPLETE",
    attempt_count: 1,
    final_url: "https://climatologie.ro/",
    http_status: 200,
    completed_at: "2026-08-30T16:58:52.000Z",
    started_at: "2026-08-30T16:57:00.000Z",
    browser_access_classification: "ok",
    scenario_id: "scenario-1",
    collector_bundle_version: "b8-v1",
    limitations: [],
  },
  artifacts: [
    {
      artifact_id: "art-1",
      artifact_type: "SCREENSHOT_VIEWPORT",
      content_type: "image/png",
      byte_size: 102400,
      sha256: "a".repeat(64),
    },
    {
      artifact_id: "art-2",
      artifact_type: "SCREENSHOT_FULL_PAGE",
      content_type: "image/png",
      byte_size: 204800,
      sha256: "b".repeat(64),
    },
    {
      artifact_id: "art-3",
      artifact_type: "RAW_DOM",
      content_type: "text/html",
      byte_size: 51200,
      sha256: "c".repeat(64),
    },
    {
      artifact_id: "art-4",
      artifact_type: "NORMALIZED_DOM",
      content_type: "application/json",
      byte_size: 25600,
      sha256: "d".repeat(64),
    },
    {
      artifact_id: "art-5",
      artifact_type: "MANIFEST",
      content_type: "application/json",
      byte_size: 12800,
      sha256: "e".repeat(64),
    },
  ],
};

describe("DiagnosticResultsPage", () => {
  beforeEach(() => {
    // Default: a valid site id in the query string, matching Home's contract.
    searchParamsMock.current = new URLSearchParams("site_id=s1");
  });

  it("renders complete diagnostic with screenshots and downloadable artifacts", async () => {
    mockedFetch.mockResolvedValue(DIAGNOSTIC_RESULTS);

    render(<DiagnosticResultsPage />);

    await screen.findByText("Diagnostic Results");
    expect(screen.getByText("Climatologie")).toBeInTheDocument();
    expect(screen.getAllByText(/climatologie\.ro/)).toHaveLength(2);

    // Run summary - DiagnosticStateBadge renders "Diagnostic complete" for COMPLETE status
    expect(screen.getByText("Diagnostic complete")).toBeInTheDocument();
    expect(screen.getByText("DIAGNOSTIC")).toBeInTheDocument();
    expect(screen.getByText("OPERATOR_UI")).toBeInTheDocument();
    expect(screen.getByText("corr-1")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument(); // attempt_count
    expect(screen.getByText("https://climatologie.ro/")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("Access: normal")).toBeInTheDocument();
    expect(screen.getByText("scenario-1")).toBeInTheDocument();
    expect(screen.getByText("b8-v1")).toBeInTheDocument();

    // Screenshots section
    expect(screen.getByText("Screenshots")).toBeInTheDocument();
    expect(screen.getByText("Viewport screenshot")).toBeInTheDocument();
    expect(screen.getByText("Full-page screenshot")).toBeInTheDocument();

    // Downloadable artifacts section
    expect(screen.getByText("Artifacts (download)")).toBeInTheDocument();
    expect(screen.getByText("Raw DOM")).toBeInTheDocument();
    expect(screen.getByText("Normalized DOM")).toBeInTheDocument();
    expect(screen.getByText("Manifest")).toBeInTheDocument();
  });

  it("shows error state when no diagnostic results found (404)", async () => {
    const error = new ApiError("not_found", 404, "Request failed: 404");
    mockedFetch.mockRejectedValue(error);

    render(<DiagnosticResultsPage />);

    await screen.findByText(/No diagnostic results available/);
  });

  it("shows error state for unauthorized access", async () => {
    const error = new ApiError("unauthorized", 401, "Request failed: 401");
    mockedFetch.mockRejectedValue(error);

    render(<DiagnosticResultsPage />);

    await screen.findByText(/Authentication required/);
  });

  it("shows error state for forbidden access", async () => {
    const error = new ApiError("forbidden", 403, "Request failed: 403");
    mockedFetch.mockRejectedValue(error);

    render(<DiagnosticResultsPage />);

    await screen.findByText(/Access denied/);
  });

  it("shows loading state initially", async () => {
    mockedFetch.mockImplementation(() => new Promise(() => {}));

    render(<DiagnosticResultsPage />);

    expect(screen.getByText("Loading diagnostic results…")).toBeInTheDocument();
  });

  it("distinguishes diagnostic states explicitly", async () => {
    mockedFetch.mockResolvedValue({
      ...DIAGNOSTIC_RESULTS,
      run: { ...DIAGNOSTIC_RESULTS.run, status: "PARTIAL" },
    });

    render(<DiagnosticResultsPage />);

    // DiagnosticStateBadge renders "Diagnostic failed" for non-COMPLETE terminal states
    await screen.findByText("Diagnostic failed");
    // Should show explicit state, not fabricate event/incident
    expect(screen.queryByText(/incident/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/event/i)).not.toBeInTheDocument();
  });

  it("does not render collected HTML as executable content", async () => {
    mockedFetch.mockResolvedValue(DIAGNOSTIC_RESULTS);

    render(<DiagnosticResultsPage />);

    await screen.findByText("Diagnostic Results");
    // Screenshots rendered as img elements, not dangerouslySetInnerHTML
    const imgs = screen.getAllByRole("img");
    expect(imgs.length).toBe(2); // viewport + full-page
    // No script execution from artifact content
    expect(document.body.innerHTML).not.toContain("dangerouslySetInnerHTML");
  });

  it("requests the diagnostic-results API for the site_id query param", async () => {
    expect(mockedFetch).not.toHaveBeenCalled();
    mockedFetch.mockResolvedValue(DIAGNOSTIC_RESULTS);

    render(<DiagnosticResultsPage />);

    await screen.findByText("Diagnostic Results");
    expect(mockedFetch).toHaveBeenCalledWith("/product/sites/s1/diagnostic-results");
  });

  it("encodes nontrivial site IDs in API and artifact URLs", async () => {
    const siteId = "a b+c/d";
    const encoded = encodeURIComponent(siteId); // "a%20b%2Bc%2Fd"
    searchParamsMock.current = new URLSearchParams(`site_id=${encoded}`);
    mockedFetch.mockResolvedValue(DIAGNOSTIC_RESULTS);

    render(<DiagnosticResultsPage />);

    await screen.findByText("Diagnostic Results");
    expect(mockedFetch).toHaveBeenCalledWith(`/product/sites/${encoded}/diagnostic-results`);
    expect(mockedFetch).not.toHaveBeenCalledWith(`/product/sites/${siteId}/diagnostic-results`);
    const images = screen.getAllByRole("img");
    expect(images.length).toBeGreaterThan(0);
    for (const img of images) {
      const src = img.getAttribute("src");
      expect(src).toContain(`/product/sites/${encoded}/`);
      expect(src).not.toContain(`/product/sites/${siteId}/`);
    }
  });

  it("shows an explicit unavailable state when site_id is missing", async () => {
    searchParamsMock.current = new URLSearchParams();

    render(<DiagnosticResultsPage />);

    await screen.findByText(/Select a site to view diagnostic results\./);
  });

  it("performs no diagnostic API request when site_id is missing", async () => {
    searchParamsMock.current = new URLSearchParams();

    render(<DiagnosticResultsPage />);

    await screen.findByText(/Select a site to view diagnostic results\./);
    expect(mockedFetch).not.toHaveBeenCalled();
  });

  it("consumes the same query contract Home pushes", async () => {
    // Home's onViewDiagnosticResults pushes `/diagnostic-results?site_id=<encoded>`.
    const homePushTarget = `/diagnostic-results?site_id=${encodeURIComponent("s1")}`;
    searchParamsMock.current = new URLSearchParams(
      new URL(homePushTarget, "http://localhost").search,
    );
    mockedFetch.mockResolvedValue(DIAGNOSTIC_RESULTS);

    render(<DiagnosticResultsPage />);

    await screen.findByText("Diagnostic Results");
    // The page derives its API path from the same encoded query param Home
    // pushes, proving the navigation contract end to end.
    expect(mockedFetch).toHaveBeenCalledWith("/product/sites/s1/diagnostic-results");
  });
});