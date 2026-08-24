"use client";

/** EP-025b M1 — login page. Generic failure only; no account-existence hints. */

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-client";
import { Button, ErrorState, Field, Input } from "@/components/primitives";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const auth = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<"invalid_credentials" | "server" | null>(null);

  // Already authenticated → Home.
  useEffect(() => {
    if (auth.status === "authenticated") {
      router.replace("/");
    }
  }, [auth.status, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFailure(null);
    try {
      const result = await auth.login({ email, password, tenant_id: tenantId });
      if (result.ok) {
        router.replace("/");
        return;
      }
      setFailure(result.reason === "server" ? "server" : "invalid_credentials");
    } catch (error) {
      setFailure(error instanceof ApiError && error.kind === "network" ? "server" : "invalid_credentials");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-main">
      <form className="card login-card" onSubmit={handleSubmit}>
        <p className="eyebrow">Publisher Incident Intelligence</p>
        <h1>Log in</h1>
        {auth.status === "checking" ? null : null}
        <Field label="Email" htmlFor="login-email">
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </Field>
        <Field label="Password" htmlFor="login-password">
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </Field>
        <Field label="Tenant ID" htmlFor="login-tenant">
          <Input
            id="login-tenant"
            required
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          />
        </Field>
        {failure === "invalid_credentials" ? <ErrorState message="Authentication failed." /> : null}
        {failure === "server" ? <ErrorState message="Something went wrong. Try again." /> : null}
        <Button type="submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </main>
  );
}
