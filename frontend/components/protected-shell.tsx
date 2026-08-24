"use client";

/** EP-025b M1 — protected application shell: guard + navigation + logout. */

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-client";
import { Button, ErrorState, LoadingState } from "@/components/primitives";
import { InvestigateDialog } from "@/components/investigate-dialog";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/timeline", label: "Timeline" },
  { href: "/incidents", label: "Incidents" },
];

export function ProtectedShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const [investigateOpen, setInvestigateOpen] = useState(false);

  const authenticated = auth.status === "authenticated";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  if (auth.status === "checking") {
    return <LoadingState label="Checking session…" />;
  }

  if (auth.status === "error") {
    // Backend unavailable: do NOT claim the session is invalid or redirect.
    return (
      <div className="card session-error">
        <ErrorState message="Could not verify your session. The service may be temporarily unavailable." />
        <Button variant="secondary" onClick={() => void auth.retry()}>
          Retry
        </Button>
      </div>
    );
  }

  if (!authenticated) {
    // Render nothing while the redirect to /login is in flight; avoids
    // flashing protected content.
    return null;
  }

  async function handleLogout() {
    const result = await auth.logout();
    if (result.ok) {
      router.replace("/login");
    }
  }

  return (
    <div className="shell">
      <header className="shell-nav">
        <span className="shell-brand">Publisher Incident Intelligence</span>
        <nav aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <a key={item.href} href={item.href}>
              {item.label}
            </a>
          ))}
        </nav>
        <div className="shell-actions">
          <Button variant="primary" onClick={() => setInvestigateOpen(true)}>
            Investigate
          </Button>
          <Button variant="secondary" onClick={() => void handleLogout()}>
            Log out
          </Button>
        </div>
      </header>
      <main className="shell-main">{children}</main>
      <InvestigateDialog open={investigateOpen} onClose={() => setInvestigateOpen(false)} />
    </div>
  );
}

export function SessionErrorFallback() {
  return <ErrorState message="Session check failed. Try reloading." />;
}
