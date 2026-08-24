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

export type AuthStatus = "checking" | "authenticated" | "unauthenticated";

interface AuthState {
  status: AuthStatus;
  session: SessionState | null;
}

interface AuthContextValue extends AuthState {
  login: (
    input: { email: string; password: string; tenant_id: string },
  ) => Promise<{ ok: true } | { ok: false; reason: "invalid_credentials" | "server" }>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "checking", session: null });

  // Session restoration runs once on mount; results are applied asynchronously
  // so no state update happens synchronously within the effect.
  useEffect(() => {
    let cancelled = false;
    async function restore() {
      try {
        const session = await apiFetch<SessionState>("/auth/session");
        if (!cancelled) setState({ status: "authenticated", session });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          setState({ status: "unauthenticated", session: null });
        } else {
          // Network/server failure surfaces as an explicit unauthenticated
          // state here; screens render their own error UI on retry.
          setState({ status: "unauthenticated", session: null });
        }
      }
    }
    void restore();
    return () => {
      cancelled = true;
    };
  }, []);

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

  const logout = useCallback(async () => {
    try {
      await apiFetch<LogoutResult>("/auth/logout", { method: "POST" });
    } catch {
      // Already-invalid sessions are safe to treat as logged out.
    }
    setState({ status: "unauthenticated", session: null });
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
