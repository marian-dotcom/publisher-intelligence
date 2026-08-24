import { render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useRouter } from "next/navigation";

import LoginPage from "../app/login/page";
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

async function fillAndSubmit(email: string) {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "some-password" } });
  fireEvent.change(screen.getByLabelText("Tenant ID"), { target: { value: "t-1" } });
  fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
}

describe("LoginPage", () => {
  it("submits credentials and navigates Home on success", async () => {
    const replace = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ replace } as unknown as ReturnType<typeof useRouter>);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(200, { actor_subject_id: "a", role: "OPERATOR", csrf_token: "c" }))
      .mockResolvedValueOnce(mockResponse(200, { actor_subject_id: "a", tenant_id: "t-1", role: "OPERATOR" }));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await fillAndSubmit("op@example.com");

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(fetchMock).toHaveBeenCalledWith(
      "/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "op@example.com", password: "some-password", tenant_id: "t-1" }),
      }),
    );
  });

  it("shows a generic failure for invalid credentials without existence hints", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockResponse(401)));

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    await fillAndSubmit("whoever@example.com");

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(/authentication failed/i),
    );
    expect(screen.queryByText(/user not found/i)).not.toBeInTheDocument();
  });

  it("disables the submit button while submitting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => new Promise(() => undefined)),
    );

    render(
      <AuthProvider>
        <LoginPage />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "slow@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.change(screen.getByLabelText("Tenant ID"), { target: { value: "t-1" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled();
  });
});
