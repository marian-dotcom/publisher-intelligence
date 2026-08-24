"use client";

/**
 * EP-025b M1 — client auth state machine.
 *
 * unknown → checking → authenticated | unauthenticated
 *
 * Session restoration uses GET /auth/session; the CSRF token is never stored
 * by this module — it lives only in the server-set `pi_csrf` cookie and is
 * read at request time (see lib/api.ts readCsrfToken).
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiFetch, ApiError } from "./api";
import type { LoginSuccess, LogoutResult, SessionState } from "./api-types";

export type AuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated"
  | "error"; // session-check failed for a non-auth reason (network/5xx)

interface AuthState {
  status: AuthStatus;
  session: SessionState | null;
}

interface AuthContextValue extends AuthState {
  /** Re-run the session check after a transient session-check failure. */
  retry: () => Promise<void>;
  logout: () => Promise<{ ok: boolean }>;
  login: (
    input: { email: string; password: string; tenant_id: string },
  ) => Promise<{ ok: true } | { ok: false; reason: "invalid_credentials" | "server" }>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "checking", session: null });

  // Session restoration: 401 → unauthenticated; network/5xx → explicit
  // retryable error (backend unavailability never proves the session invalid).
  const restore = useCallback(async (): Promise<void> => {
    try {
      const session = await apiFetch<SessionState>("/auth/session");
      setState({ status: "authenticated", session });
    } catch (error) {
      if (error instanceof ApiError && error.kind === "unauthorized") {
        setState({ status: "unauthenticated", session: null });
      } else {
        setState({ status: "error", session: null });
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      // Apply results only after an await boundary (no sync setState-in-effect).
      await Promise.resolve();
      if (!cancelled) await restore();
    })();
    return () => {
      cancelled = true;
    };
  }, [restore]);

  const login = useCallback(
    async (input: { email: string; password: string; tenant_id: string }) => {
      try {
        await apiFetch<LoginSuccess>("/auth/login", { method: "POST", body: input });
      } catch (error) {
        if (error instanceof ApiError && error.kind === "unauthorized") {
          return { ok: false as const, reason: "invalid_credentials" as const };
        }
        return { ok: false as const, reason: "server" as const };
      }
      const session = await apiFetch<SessionState>("/auth/session");
      setState({ status: "authenticated", session });
      return { ok: true as const };
    },
    [],
  );

  const logout = useCallback(
    async (): Promise<{ ok: boolean }> => {
      try {
        const result = await apiFetch<LogoutResult>("/auth/logout", { method: "POST" });
        setState({ status: "unauthenticated", session: null });
        return { ok: Boolean(result.revoked) };
      } catch (error) {
        if (error instanceof ApiError && error.kind === "unauthorized") {
          // Session was already invalid server-side; treat as logged out.
          setState({ status: "unauthenticated", session: null });
          return { ok: true };
        }
        // CSRF/server/network failure: the session may still exist — stay
        // authenticated and surface the failure truthfully.
        setState({ status: "error", session: null });
        return { ok: false };
      }
    },
    [],
  );

  const value = useMemo(
    () => ({ ...state, retry: restore, login, logout }),
    [state, restore, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
