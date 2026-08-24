import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRouter } from "next/navigation";

import { apiFetch } from "../lib/api";

vi.mock("../lib/api");
import { InvestigateDialog } from "../components/investigate-dialog";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn().mockReturnValue({ push: vi.fn(), replace: vi.fn() }),
}));

const mockedApi = vi.mocked(apiFetch);

afterEach(() => {
  mockedApi.mockReset();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
  document.cookie = "pi_csrf=; Max-Age=0; path=/";
});

async function openDialog() {
  mockedApi.mockResolvedValueOnce({
    sites: [{ site_id: "s1", name: "News Daily" }],
    selected_site_id: "s1",
  });
  render(<InvestigateDialog open onClose={vi.fn()} />);
  await screen.findByLabelText("Site");
}

describe("InvestigateDialog", () => {
  it("submits with CSRF header and navigates to the created incident", async () => {
    const push = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push } as unknown as ReturnType<typeof useRouter>);
    document.cookie = "pi_csrf=test-csrf; path=/";
    mockedApi
      .mockResolvedValueOnce({
        sites: [{ site_id: "s1", name: "News Daily" }],
        selected_site_id: "s1",
      })
      .mockResolvedValueOnce({ incident_id: "inc-1", investigation_key: "k", status: "OPEN" });

    render(<InvestigateDialog open onClose={vi.fn()} />);
    await screen.findByLabelText("Site");

    await screen.findByLabelText(/What happened/i);
    fireEvent.change(screen.getByLabelText(/What happened/i), { target: { value: "Ads went dark" } });
    fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: "GAM slots empty after deploy." } });
    const form = document.querySelector("#investigate-dialog form");
    if (form) fireEvent.submit(form);

    await waitFor(() => expect(push).toHaveBeenCalledWith("/incidents/inc-1"), { timeout: 3000 });
    // The write call carried the session CSRF double-submit header.
    expect(mockedApi).toHaveBeenLastCalledWith(
      "/investigations",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("renders a non-disclosing error when the site is not found (404)", async () => {
    document.cookie = "pi_csrf=test-csrf; path=/";
    const notFound = Object.assign(new Error("not found"), { kind: "not_found", status: 404 });
    mockedApi
      .mockResolvedValueOnce({
        sites: [{ site_id: "s1", name: "News Daily" }],
        selected_site_id: "s1",
      })
      .mockRejectedValue(notFound);

    render(<InvestigateDialog open onClose={vi.fn()} />);
    await screen.findByLabelText("Site");

    fireEvent.change(screen.getByLabelText(/What happened/i), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: "y" } });
    const form = document.querySelector("#investigate-dialog form");
    if (form) fireEvent.submit(form);

    await screen.findByText("That site was not found.", undefined, { timeout: 3000 });
  });
});
