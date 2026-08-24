"use client";

/** EP-025b M1 — protected application shell: guard + navigation + logout. */

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth-client";
import { Button, ErrorState, LoadingState } from "@/components/primitives";

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/timeline", label: "Timeline" },
  { href: "/incidents", label: "Incidents" },
];

export function ProtectedShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();

  const authenticated = auth.status === "authenticated";

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.replace("/login");
    }
  }, [auth.status, router]);

  if (auth.status === "checking") {
    return <LoadingState label="Checking session…" />;
  }

  if (!authenticated) {
    // Render nothing while the redirect to /login is in flight; avoids
    // flashing protected content.
    return null;
  }

  async function handleLogout() {
    await auth.logout();
    router.replace("/login");
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
          <Button variant="secondary" disabled title="Available in an upcoming milestone">
            Investigate
          </Button>
          <Button variant="secondary" onClick={() => void handleLogout()}>
            Log out
          </Button>
        </div>
      </header>
      <main className="shell-main">{children}</main>
    </div>
  );
}

export function SessionErrorFallback() {
  return <ErrorState message="Session check failed. Try reloading." />;
}
