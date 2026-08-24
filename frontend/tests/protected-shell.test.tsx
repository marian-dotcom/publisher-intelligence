import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRouter } from "next/navigation";

import { ProtectedShell } from "../components/protected-shell";
import { AuthProvider } from "../lib/auth-client";

function mockResponse(status: number, body: unknown = {}): Response {
  return { ok: status >= 200 && status < 300, status, json: () => Promise.resolve(body) } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

vi.mock("next/navigation", () => ({
  useRouter: vi.fn().mockReturnValue({ replace: vi.fn() }),
}));

describe("ProtectedShell", () => {
  it("shows a loading boundary before session state resolves", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => new Promise(() => undefined)), // never settles
    );

    render(
      <AuthProvider>
        <ProtectedShell>
          <p>protected content</p>
        </ProtectedShell>
      </AuthProvider>,
    );

    expect(screen.getByText(/checking session/i)).toBeInTheDocument();
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("renders navigation for an authenticated session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(200, { actor_subject_id: "a", tenant_id: "t", role: "OPERATOR" })));

    render(
      <AuthProvider>
        <ProtectedShell>
          <p>protected content</p>
        </ProtectedShell>
      </AuthProvider>,
    );

    await waitFor(() => expect(screen.getByText("protected content")).toBeInTheDocument());
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Timeline" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Incidents" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Log out" })).toBeEnabled();
  });

  it("redirects to /login when unauthenticated and hides protected content", async () => {
    const replace = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ replace } as unknown as ReturnType<typeof useRouter>);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(401)));

    render(
      <AuthProvider>
        <ProtectedShell>
          <p>protected content</p>
        </ProtectedShell>
      </AuthProvider>,
    );

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });
});
