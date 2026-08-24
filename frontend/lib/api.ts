/**
 * EP-025b M1 — typed fetch layer for the first-party cookie-session API.
 *
 * Contract (from backend/app/auth/routes.py + EP-025a routes):
 * - credentials ride the HttpOnly `pi_session` cookie (same-origin)
 * - CSRF token is server-set in the JS-readable `pi_csrf` cookie at login and
 *   must be echoed as `X-CSRF-Token` on state-changing requests
 * - 401 = unauthenticated, 403 = CSRF/authorization failure
 *
 * No JWT, no localStorage/sessionStorage auth storage.
 */

export type ApiErrorKind =
  | "unauthorized" // 401 — session missing/invalid/expired/revoked
  | "forbidden" // 403 — CSRF or authorization failure
  | "not_found" // 404 — non-disclosing resource absence
  | "server" // 5xx
  | "network"; // fetch itself failed

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;

  constructor(kind: ApiErrorKind, status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

export function errorKind(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  return "server";
}

/** Read the server-set, non-HttpOnly CSRF double-submit cookie. */
export function readCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)pi_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = {};
  let body: string | undefined;

  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  if (method !== "GET") {
    const csrf = readCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError("network", 0, "Network request failed.");
  }

  if (!response.ok) {
    throw new ApiError(errorKind(response.status), response.status, `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}
