import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch, ApiError } from "@/lib/api";

vi.mock("@/lib/api");

const mockedFetch = vi.mocked(apiFetch);

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  mockedFetch.mockReset();
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  document.cookie = "pi_csrf=; Max-Age=0; path=/";
});

// ---------- helpers ----------

import { AddSiteDialog } from "../components/add-site-dialog";

function renderDialog(opts?: { onSuccess?: () => void; onClose?: () => void }) {
  const onSuccess = opts?.onSuccess ?? vi.fn();
  const onClose = opts?.onClose ?? vi.fn();
  render(<AddSiteDialog open onClose={onClose} onSuccess={onSuccess} />);
  return { onSuccess, onClose };
}

// ---------- AddSiteDialog ----------

describe("AddSiteDialog", () => {
  it("renders three labeled fields with accessible names", async () => {
    renderDialog();
    await waitFor(() => {
      expect(screen.getByLabelText("Publisher name")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Site name")).toBeInTheDocument();
    expect(screen.getByLabelText("Website URL")).toBeInTheDocument();
  });

  it("dialog has an accessible name via aria-labelledby", async () => {
    renderDialog();
    await waitFor(() => {
      expect(screen.getByText("Add site", { selector: "h2" })).toBeInTheDocument();
    });
    const dialog = document.querySelector("#add-site-dialog");
    expect(dialog).not.toBeNull();
    expect(dialog).toHaveAttribute("aria-labelledby", "add-site-title");
  });

  it("submits with correct endpoint, method, and three-field body", async () => {
    const { onSuccess } = renderDialog();
    document.cookie = "pi_csrf=test-csrf; path=/";
    mockedFetch.mockResolvedValueOnce({
      site_id: "new-site-1",
      canonical_domain: "news.example",
      checkpoint_run_id: "run-1",
      diagnostic_status: "PENDING",
    });

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Example Publisher" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Example News" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://news.example/" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1));
    expect(mockedFetch).toHaveBeenCalledWith("/product/sites", {
      method: "POST",
      body: {
        publisher_name: "Example Publisher",
        site_name: "Example News",
        url: "https://news.example/",
      },
    });
    expect(onSuccess).toHaveBeenCalledWith("new-site-1");
  });

  it("trims whitespace from all fields before submission", async () => {
    const { onSuccess } = renderDialog();
    mockedFetch.mockResolvedValueOnce({
      site_id: "new-site-1",
      canonical_domain: "news.example",
      checkpoint_run_id: "run-1",
      diagnostic_status: "PENDING",
    });

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "  Example Publisher  " } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "  Example News  " } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "  https://news.example/  " } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1));
    expect(mockedFetch).toHaveBeenCalledWith("/product/sites", {
      method: "POST",
      body: {
        publisher_name: "Example Publisher",
        site_name: "Example News",
        url: "https://news.example/",
      },
    });
    expect(onSuccess).toHaveBeenCalledWith("new-site-1");
  });

  it("disables submission when any trimmed field is empty", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Example" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://example.com" } });

    const submitBtn = document.querySelector("#add-site-dialog button[type='submit']") as HTMLButtonElement;
    expect(submitBtn).toBeDisabled();
  });

  it("prevents duplicate in-flight submission", async () => {
    renderDialog();
    // Never resolve so the request stays in-flight.
    mockedFetch.mockReturnValue(new Promise(() => {}));

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);
    await waitFor(() => expect(screen.getByText("Adding…")).toBeInTheDocument());
    // Second submit should not trigger another fetch.
    fireEvent.submit(form);
    expect(mockedFetch).toHaveBeenCalledTimes(1);
  });

  it("shows sanitized error for 409 duplicate registration", async () => {
    renderDialog();
    const duplicateError = Object.assign(new ApiError("server", 409, "Conflict"), { status: 409 });
    mockedFetch.mockRejectedValue(duplicateError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://dup.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText("This website is already registered.", undefined, { timeout: 3000 });
  });

  it("shows sanitized error for 400 blocked URL", async () => {
    renderDialog();
    const blockedError = Object.assign(new ApiError("server", 400, "Bad Request"), { status: 400 });
    mockedFetch.mockRejectedValue(blockedError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "http://127.0.0.1" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText("Enter a valid public website URL.", undefined, { timeout: 3000 });
  });

  it("shows sanitized error for 401 unauthorized", async () => {
    renderDialog();
    const authError = Object.assign(new ApiError("unauthorized", 401, "Unauthorized"), { status: 401 });
    mockedFetch.mockRejectedValue(authError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText("Your session has expired. Reload and try again.", undefined, { timeout: 3000 });
  });

  it("shows sanitized error for 403 forbidden", async () => {
    renderDialog();
    const forbiddenError = Object.assign(new ApiError("forbidden", 403, "Forbidden"), { status: 403 });
    mockedFetch.mockRejectedValue(forbiddenError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText(
      "You do not have permission to add this site, or your session could not be verified.",
      undefined,
      { timeout: 3000 },
    );
  });

  it("shows generic error for network failure", async () => {
    renderDialog();
    const networkError = new ApiError("network", 0, "Network request failed.");
    mockedFetch.mockRejectedValue(networkError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText("Could not register the site. Try again.", undefined, { timeout: 3000 });
  });

  it("shows generic error for 5xx server failure", async () => {
    renderDialog();
    const serverError = new ApiError("server", 500, "Internal Server Error");
    mockedFetch.mockRejectedValue(serverError);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;
    fireEvent.submit(form);

    await screen.findByText("Could not register the site. Try again.", undefined, { timeout: 3000 });
  });

  it("resets form and calls onClose when Cancel is clicked", async () => {
    const { onClose } = renderDialog();
    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    const cancelBtn = document.querySelector("#add-site-dialog button[type='button']") as HTMLButtonElement;
    fireEvent.click(cancelBtn);
    expect(onClose).toHaveBeenCalled();
  });

  it("has maxLength attributes matching backend constraints", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    expect(screen.getByLabelText("Publisher name")).toHaveAttribute("maxLength", "200");
    expect(screen.getByLabelText("Site name")).toHaveAttribute("maxLength", "200");
    expect(screen.getByLabelText("Website URL")).toHaveAttribute("maxLength", "2048");
  });

  it("uses url input type for the website URL field", async () => {
    renderDialog();
    await waitFor(() => expect(screen.getByLabelText("Website URL")).toBeInTheDocument());
    expect(screen.getByLabelText("Website URL")).toHaveAttribute("type", "url");
  });
});

// ---------- InitialDiagnosticBadge ----------

import { InitialDiagnosticBadge } from "../components/domain";

describe("InitialDiagnosticBadge", () => {
  it("renders explicit unavailable state when null", () => {
    render(<InitialDiagnosticBadge diagnostic={null} />);
    expect(screen.getByText("Diagnostic: not available")).toBeInTheDocument();
  });

  it("renders PENDING status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: queued")).toBeInTheDocument();
  });

  it("renders RUNNING status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "RUNNING", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: running")).toBeInTheDocument();
  });

  it("renders COMPLETE status with ok classification", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "COMPLETE", completed_at: "2026-08-27T10:00:00Z", browser_access_classification: "ok" }} />);
    expect(screen.getByText("Diagnostic: complete · Access: normal")).toBeInTheDocument();
  });

  it("renders COMPLETE status with degraded classification", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "COMPLETE", completed_at: "2026-08-27T10:00:00Z", browser_access_classification: "degraded" }} />);
    expect(screen.getByText("Diagnostic: complete · Access: degraded")).toBeInTheDocument();
  });

  it("renders COMPLETE status with challenge_suspected classification", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "COMPLETE", completed_at: "2026-08-27T10:00:00Z", browser_access_classification: "challenge_suspected" }} />);
    expect(screen.getByText("Diagnostic: complete · Access: challenge suspected")).toBeInTheDocument();
  });

  it("renders PARTIAL status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "PARTIAL", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: partial")).toBeInTheDocument();
  });

  it("renders SITE_ERROR status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "SITE_ERROR", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: site error")).toBeInTheDocument();
  });

  it("renders BROWSER_ERROR status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "BROWSER_ERROR", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: browser error")).toBeInTheDocument();
  });

  it("renders TIMEOUT status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "TIMEOUT", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: timed out")).toBeInTheDocument();
  });

  it("renders BLOCKED status", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "BLOCKED", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: blocked")).toBeInTheDocument();
  });

  it("renders sanitized label for unknown status without leaking raw value", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "TOTALLY_UNKNOWN", completed_at: null, browser_access_classification: null }} />);
    expect(screen.getByText("Diagnostic: unknown")).toBeInTheDocument();
    expect(screen.queryByText("TOTALLY_UNKNOWN")).not.toBeInTheDocument();
  });

  it("omits classification for unknown classification without leaking raw value", () => {
    render(<InitialDiagnosticBadge diagnostic={{ run_id: "r1", status: "COMPLETE", completed_at: null, browser_access_classification: "weird_value" }} />);
    expect(screen.getByText("Diagnostic: complete")).toBeInTheDocument();
    expect(screen.queryByText("weird_value")).not.toBeInTheDocument();
  });
});

// ---------- HomePage integration ----------

import HomePage from "../app/(protected)/page";

describe("HomePage Add Site integration", () => {
  const HOME_BODY = {
    sites: [{ site_id: "s1", name: "News Daily" }],
    selected_site_id: "s1",
    publisher_site_condition: "ACTIVE",
    source_health: { BROWSER_MONITORING: "UNKNOWN", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
    initial_diagnostic: null,
    open_incident_count: 0,
    monetization_capability: "UNKNOWN",
  };

  const SOURCE_BODY = {
    site_id: "s1",
    sources: { BROWSER_MONITORING: "UNKNOWN", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
  };

  it("renders Add site button without adding a fourth nav item", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_BODY).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    await screen.findByText("Publisher/site: ACTIVE");
    expect(screen.getByRole("button", { name: "Add site" })).toBeInTheDocument();
  });

  it("shows null diagnostic as unavailable", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_BODY).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    await screen.findByText("Diagnostic: not available");
  });

  it("shows diagnostic badge when diagnostic is present", async () => {
    const homeWithDiag = {
      ...HOME_BODY,
      initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null },
    };
    mockedFetch.mockResolvedValueOnce(homeWithDiag).mockResolvedValueOnce(SOURCE_BODY);

    render(<HomePage />);

    await screen.findByText("Diagnostic: queued");
  });

  it("clears detailHealth when site changes to prevent stale source health", async () => {
    const homeBody2Sites = {
      sites: [
        { site_id: "s1", name: "News Daily" },
        { site_id: "s2", name: "Sports Weekly" },
      ],
      selected_site_id: "s1",
      publisher_site_condition: "ACTIVE",
      source_health: { BROWSER_MONITORING: "HEALTHY", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
      initial_diagnostic: null,
      open_incident_count: 0,
      monetization_capability: "UNKNOWN",
    };
    const sourceBodyS1 = {
      site_id: "s1",
      sources: { BROWSER_MONITORING: "HEALTHY", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
    };
    const homeBodyS2 = {
      ...homeBody2Sites,
      selected_site_id: "s2",
    };
    const sourceBodyS2 = {
      site_id: "s2",
      sources: { BROWSER_MONITORING: "DEGRADED", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
    };
    mockedFetch
      .mockResolvedValueOnce(homeBody2Sites)
      .mockResolvedValueOnce(sourceBodyS1)
      .mockResolvedValueOnce(homeBodyS2)
      .mockResolvedValueOnce(sourceBodyS2);

    render(<HomePage />);

    await screen.findByText("Publisher/site: ACTIVE");
    expect(screen.getByText(/Browser Monitoring · HEALTHY/)).toBeInTheDocument();

    // Change site
    fireEvent.change(screen.getByLabelText("Selected site"), { target: { value: "s2" } });

    await waitFor(() => {
      expect(screen.getByText(/Browser Monitoring · DEGRADED/)).toBeInTheDocument();
    });
  });
});

// ---------- Diagnostic polling ----------

describe("Diagnostic polling", () => {
  const HOME_BODY = {
    sites: [{ site_id: "s1", name: "News Daily" }],
    selected_site_id: "s1",
    publisher_site_condition: "ACTIVE",
    source_health: { BROWSER_MONITORING: "UNKNOWN", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
    initial_diagnostic: null,
    open_incident_count: 0,
    monetization_capability: "UNKNOWN",
  };

  const SOURCE_BODY = {
    site_id: "s1",
    sources: { BROWSER_MONITORING: "UNKNOWN", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" },
  };

  it("A: PENDING schedules poll, terminal response stops it", async () => {
    const homePending = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null } };
    const homeComplete = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "COMPLETE", completed_at: "2026-08-27T10:00:00Z", browser_access_classification: "ok" } };
    mockedFetch
      .mockResolvedValueOnce(homePending)   // 1: initial home
      .mockResolvedValueOnce(SOURCE_BODY)   // 2: initial source
      .mockResolvedValueOnce(homeComplete); // 3: poll response (terminal)

    render(<HomePage />);
    await screen.findByText("Diagnostic: queued");
    expect(mockedFetch).toHaveBeenCalledTimes(2);

    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(3));
    expect(mockedFetch).toHaveBeenLastCalledWith("/product/home/status?site_id=s1");
    await screen.findByText(/Diagnostic: complete/);

    // No further poll after terminal.
    await act(async () => { vi.advanceTimersByTime(8000); });
    expect(mockedFetch).toHaveBeenCalledTimes(3);
  });

  it("B: RUNNING continues polling until terminal", async () => {
    const homeRunning = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "RUNNING", completed_at: null, browser_access_classification: null } };
    const homeComplete = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "COMPLETE", completed_at: "2026-08-27T10:00:00Z", browser_access_classification: "degraded" } };
    mockedFetch
      .mockResolvedValueOnce(homeRunning)   // 1: initial home
      .mockResolvedValueOnce(SOURCE_BODY)   // 2: initial source
      .mockResolvedValueOnce(homeRunning)   // 3: poll still RUNNING
      .mockResolvedValueOnce(homeComplete); // 4: poll terminal

    render(<HomePage />);
    await screen.findByText("Diagnostic: running");

    await act(async () => { vi.advanceTimersByTime(4000); });
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(3));
    await screen.findByText("Diagnostic: running");

    await act(async () => { vi.advanceTimersByTime(4000); });
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(4));
    await screen.findByText(/Diagnostic: complete/);

    await act(async () => { vi.advanceTimersByTime(8000); });
    expect(mockedFetch).toHaveBeenCalledTimes(4);
  });

  it("C: terminal and unknown statuses schedule no further poll", async () => {
    for (const status of ["COMPLETE", "PARTIAL", "SITE_ERROR", "BROWSER_ERROR", "TIMEOUT", "BLOCKED", "WEIRD_STATUS"]) {
      mockedFetch.mockReset();
      const home = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status, completed_at: null, browser_access_classification: null } };
      mockedFetch.mockResolvedValueOnce(home).mockResolvedValueOnce(SOURCE_BODY);
      const { unmount } = render(<HomePage />);
      await screen.findByText(/Diagnostic/);
      const callsBefore = mockedFetch.mock.calls.length;
      await act(async () => { vi.advanceTimersByTime(12000); });
      expect(mockedFetch).toHaveBeenCalledTimes(callsBefore);
      unmount();
    }
  });

  it("C: null diagnostic schedules no poll", async () => {
    mockedFetch.mockResolvedValueOnce(HOME_BODY).mockResolvedValueOnce(SOURCE_BODY);
    render(<HomePage />);
    await screen.findByText("Diagnostic: not available");
    const callsBefore = mockedFetch.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(12000); });
    expect(mockedFetch).toHaveBeenCalledTimes(callsBefore);
  });

  it("D: stale-site race — late response for site A does not overwrite site B", async () => {
    const homeA = {
      ...HOME_BODY,
      sites: [{ site_id: "s1", name: "News Daily" }, { site_id: "s2", name: "Sports" }],
      initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null },
    };
    const homeB = {
      ...HOME_BODY,
      sites: [{ site_id: "s1", name: "News Daily" }, { site_id: "s2", name: "Sports" }],
      selected_site_id: "s2",
      publisher_site_condition: "REVIEW",
      initial_diagnostic: { run_id: "r2", status: "COMPLETE", completed_at: null, browser_access_classification: null },
    };
    const sourceB = { site_id: "s2", sources: { BROWSER_MONITORING: "HEALTHY", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" } };

    let resolvePollA: (v: unknown) => void;
    const pollAPromise = new Promise((resolve) => { resolvePollA = resolve; });

    // call 0: homeA, call 1: SOURCE_BODY, call 2: pollAPromise (pending), call 3: homeB, call 4: sourceB
    mockedFetch
      .mockResolvedValueOnce(homeA)
      .mockResolvedValueOnce(SOURCE_BODY);

    const callResults = [pollAPromise, homeB, sourceB];
    let callIndex = 0;
    mockedFetch.mockImplementation(() => {
      const result = callResults[callIndex] ?? pollAPromise;
      callIndex += 1;
      return Promise.resolve(result);
    });

    render(<HomePage />);
    await screen.findByText("Diagnostic: queued");
    expect(mockedFetch).toHaveBeenCalledTimes(2);

    // Advance to fire the poll timer.
    await vi.advanceTimersByTimeAsync(4000);
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(3));

    // Switch to B (site change invalidates A's generation).
    fireEvent.change(screen.getByLabelText("Selected site"), { target: { value: "s2" } });
    await vi.advanceTimersByTimeAsync(100);

    // Now resolve the stale poll for A — must not overwrite B.
    await act(async () => { resolvePollA!(homeA); });
    await vi.advanceTimersByTimeAsync(0);

    // Site B state must not be overwritten by stale site A response.
    expect(screen.getByText("Publisher/site: REVIEW")).toBeInTheDocument();
    expect(screen.getByText(/Browser Monitoring · HEALTHY/)).toBeInTheDocument();

    // Poll must not request source-health for stale site A.
    const pollCalls = mockedFetch.mock.calls.slice(2);
    for (const call of pollCalls) {
      if (typeof call[0] === "string") {
        expect(call[0]).not.toContain("source-health?site_id=s1");
      }
    }
  });

  it("E: non-overlap — no second poll starts while first is unresolved", async () => {
    const homePending = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null } };
    let resolvePoll: (v: unknown) => void;
    const pollPromise = new Promise((resolve) => { resolvePoll = resolve; });

    mockedFetch
      .mockResolvedValueOnce(homePending)   // 1: initial home
      .mockResolvedValueOnce(SOURCE_BODY)   // 2: initial source
      .mockReturnValueOnce(pollPromise);    // 3: first poll (deferred)

    render(<HomePage />);
    await screen.findByText("Diagnostic: queued");

    // Fire the first poll.
    await act(async () => { vi.advanceTimersByTime(4000); });
    expect(mockedFetch).toHaveBeenCalledTimes(3);

    // Advance through many intervals — second poll must not start.
    await act(async () => { vi.advanceTimersByTime(20000); });
    expect(mockedFetch).toHaveBeenCalledTimes(3);

    // Resolve the first poll, then the next can start.
    mockedFetch.mockResolvedValueOnce(homePending); // 4: second poll
    await act(async () => { resolvePoll!(homePending); });
    await act(async () => { vi.advanceTimersByTime(4000); });
    expect(mockedFetch).toHaveBeenCalledTimes(4);
  });

  it("F: site change and unmount cancel polling", async () => {
    const homePending = {
      ...HOME_BODY,
      sites: [{ site_id: "s1", name: "News Daily" }, { site_id: "s2", name: "Sports" }],
      initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null },
    };
    const homeTwoSites = {
      ...HOME_BODY,
      sites: [{ site_id: "s1", name: "News Daily" }, { site_id: "s2", name: "Sports" }],
      initial_diagnostic: null,
    };
    const sourceS2 = { site_id: "s2", sources: { BROWSER_MONITORING: "UNKNOWN", GA4: "UNKNOWN", GSC: "UNKNOWN", GAM: "UNKNOWN", PUBLIC_CONFIG: "UNKNOWN" } };

    // --- Site change stops polling ---
    mockedFetch
      .mockResolvedValueOnce(homePending)    // 1: initial home
      .mockResolvedValueOnce(SOURCE_BODY)    // 2: initial source
      .mockResolvedValueOnce(homeTwoSites)   // 3: home after site change
      .mockResolvedValueOnce(sourceS2);      // 4: source after site change

    const { unmount } = render(<HomePage />);
    await screen.findByText("Diagnostic: queued");

    // Switch to site s2.
    fireEvent.change(screen.getByLabelText("Selected site"), { target: { value: "s2" } });
    await vi.advanceTimersByTimeAsync(100);
    await waitFor(() => expect(screen.getByText("Diagnostic: not available")).toBeInTheDocument());

    // No further poll calls after site change.
    const callsAfterChange = mockedFetch.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(12000); });
    expect(mockedFetch).toHaveBeenCalledTimes(callsAfterChange);
    unmount();

    // --- Unmount stops polling ---
    mockedFetch.mockReset();
    mockedFetch
      .mockResolvedValueOnce(homePending)
      .mockResolvedValueOnce(SOURCE_BODY);
    const { unmount: unmount2 } = render(<HomePage />);
    await screen.findByText("Diagnostic: queued");
    unmount2();
    const callsAfterUnmount = mockedFetch.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(12000); });
    expect(mockedFetch).toHaveBeenCalledTimes(callsAfterUnmount);
  });

  it("F: poll failure stops further attempts", async () => {
    const homePending = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null } };
    mockedFetch
      .mockResolvedValueOnce(homePending)
      .mockResolvedValueOnce(SOURCE_BODY)
      .mockRejectedValueOnce(new Error("network"));

    render(<HomePage />);
    await screen.findByText("Diagnostic: queued");

    await act(async () => { vi.advanceTimersByTime(4000); });
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(3));

    // No further polls after failure.
    const callsAfterFail = mockedFetch.mock.calls.length;
    await act(async () => { vi.advanceTimersByTime(12000); });
    expect(mockedFetch).toHaveBeenCalledTimes(callsAfterFail);
  });

  it("G: finite bound — stops after MAX_POLL_ATTEMPTS (15)", async () => {
    const homePending = { ...HOME_BODY, initial_diagnostic: { run_id: "r1", status: "PENDING", completed_at: null, browser_access_classification: null } };
    // Always return PENDING so it keeps polling.
    mockedFetch.mockImplementation(() => Promise.resolve(homePending));

    render(<HomePage />);
    await screen.findByText("Diagnostic: queued");

    // 1 initial home + 1 source-health = 2 calls, then up to 15 polls.
    for (let i = 0; i < 15; i++) {
      await act(async () => { vi.advanceTimersByTime(4000); });
    }
    // 2 initial + 15 polls = 17 total.
    expect(mockedFetch).toHaveBeenCalledTimes(17);

    // One more interval — no additional request.
    await act(async () => { vi.advanceTimersByTime(4000); });
    expect(mockedFetch).toHaveBeenCalledTimes(17);
  });
});

// ---------- Handler-level inflight guard ----------

describe("Handler-level duplicate-submit guard", () => {
  it("H: two synchronous submits produce exactly one POST", async () => {
    renderDialog();
    let resolvePost: (v: unknown) => void;
    const postPromise = new Promise((resolve) => { resolvePost = resolve; });
    mockedFetch.mockReturnValue(postPromise);

    await waitFor(() => expect(screen.getByLabelText("Publisher name")).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("Publisher name"), { target: { value: "Ex" } });
    fireEvent.change(screen.getByLabelText("Site name"), { target: { value: "Site" } });
    fireEvent.change(screen.getByLabelText("Website URL"), { target: { value: "https://a.com" } });

    const form = document.querySelector("#add-site-dialog form")!;

    // Dispatch two submit events in the same synchronous task.
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });

    // Only one POST issued, even before React re-renders the disabled state.
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Adding…")).toBeInTheDocument();

    // Clean up: resolve the deferred promise.
    await act(async () => {
      resolvePost!({ site_id: "new-1", canonical_domain: "a.com", checkpoint_run_id: "run-1", diagnostic_status: "PENDING" });
    });
  });
});
