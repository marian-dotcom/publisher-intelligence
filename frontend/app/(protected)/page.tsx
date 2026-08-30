"use client";

/** EP-028 M3 — Home: site selector, add site, site condition, initial diagnostic, source health. */

import { useCallback, useEffect, useRef, useState } from "react";

import { AddSiteDialog } from "@/components/add-site-dialog";
import {
  InitialDiagnosticBadge,
  MonetizationCapabilityView,
  SiteCondition,
  SourceHealthBadge,
} from "@/components/domain";
import { Button, EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type {
  HomeStatus,
  SourceHealth,
  SourceHealthResponse,
  SourceKey,
} from "@/lib/api-types";

const SOURCE_KEYS: SourceKey[] = [
  "BROWSER_MONITORING",
  "GA4",
  "GSC",
  "GAM",
  "PUBLIC_CONFIG",
];

const DIAGNOSTIC_POLL_INTERVAL_MS = 4000;
const MAX_POLL_ATTEMPTS = 15;

export default function HomePage() {
  const [home, setHome] = useState<HomeStatus | null>(null);
  const [detailHealth, setDetailHealth] = useState<SourceHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [siteParam, setSiteParam] = useState<string | undefined>(undefined);
  const [addSiteOpen, setAddSiteOpen] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const siteGenRef = useRef(0);

  // Initial/default load; site selection changes re-run through siteParam.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        const status = await apiFetch<HomeStatus>(
          `/product/home/status${siteParam ? `?site_id=${siteParam}` : ""}`,
        );
        if (!cancelled) {
          setHome(status);
          if (status.selected_site_id) {
            const detail = await apiFetch<SourceHealthResponse>(
              `/product/source-health?site_id=${status.selected_site_id}`,
            );
            if (!cancelled) setDetailHealth(detail);
          } else {
            if (!cancelled) setDetailHealth(null);
          }
        }
      } catch {
        if (!cancelled) setError("Could not load home status. Try again.");
      } finally {
        if (!cancelled) {
          setInitialLoading(false);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [siteParam]);

  // Bounded diagnostic refresh: recursive setTimeout with stale-response guard.
  const startDiagnosticPoll = useCallback(
    (siteId: string) => {
      // Cancel any existing poll and invalidate in-flight responses.
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      siteGenRef.current += 1;
      const gen = siteGenRef.current;
      let attempts = 0;

      function scheduleNext() {
        pollTimerRef.current = setTimeout(async () => {
          pollTimerRef.current = null;
          attempts += 1;
          if (attempts > MAX_POLL_ATTEMPTS) return;
          try {
            const status = await apiFetch<HomeStatus>(
              `/product/home/status?site_id=${siteId}`,
            );
            // Guard: generation and site must still be current.
            if (gen !== siteGenRef.current) return;
            if (siteId !== status.selected_site_id) return;
            const diag = status.initial_diagnostic;
            const isPolling = diag && (diag.status === "PENDING" || diag.status === "RUNNING");
            if (!isPolling) {
              setHome(status);
              return;
            }
            scheduleNext();
          } catch {
            // Transient failure: stop polling.
          }
        }, DIAGNOSTIC_POLL_INTERVAL_MS);
      }

      scheduleNext();
    },
    [],
  );

  // Start/stop diagnostic polling based on current diagnostic state.
  useEffect(() => {
    const diag = home?.initial_diagnostic;
    const selectedId = home?.selected_site_id;
    if (selectedId && diag && (diag.status === "PENDING" || diag.status === "RUNNING")) {
      startDiagnosticPoll(selectedId);
    }
    return () => {
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [home?.initial_diagnostic, home?.selected_site_id, startDiagnosticPoll]);

  function onSiteChange(next: string) {
    // Stop any active diagnostic poll and invalidate in-flight responses.
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    siteGenRef.current += 1;
    setSiteParam(next === "" ? undefined : next);
    setLoading(true);
    setDetailHealth(null);
  }

  function onSiteAdded(siteId: string) {
    setAddSiteOpen(false);
    setDetailHealth(null);
    // Invalidate any in-flight poll before selecting the new site.
    siteGenRef.current += 1;
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setSiteParam(siteId);
    setLoading(true);
  }

  const sources: Record<SourceKey, SourceHealth> =
    detailHealth?.sources ?? home?.source_health ?? ({} as Record<SourceKey, SourceHealth>);

  if (error) return <ErrorState message={error} />;
  if (home === null)
    return initialLoading ? (
      <LoadingState label="Loading home…" />
    ) : (
      <EmptyState message="No sites are connected yet. Connect a site to see operational status." />
    );

  return (
    <>
      <h1>Home</h1>
      <div className="home-controls">
        <label className="field" htmlFor="site-select">
          Selected site
        </label>
        <select
          id="site-select"
          className="input"
          value={home.selected_site_id ?? ""}
          onChange={(event) => onSiteChange(event.target.value)}
        >
          {(home.sites ?? []).map((site) => (
            <option key={site.site_id} value={site.site_id}>
              {site.name}
            </option>
          ))}
        </select>
        <Button variant="secondary" onClick={() => setAddSiteOpen(true)}>
          Add site
        </Button>
      </div>

      <section aria-label="Publisher and site condition">
        {/* Site condition is independent of source observation states. */}
        <SiteCondition condition={home.publisher_site_condition} />
        <InitialDiagnosticBadge diagnostic={home.initial_diagnostic} />
        <MonetizationCapabilityView capability={home.monetization_capability} />
        <p>Open incidents: {home.open_incident_count}</p>
      </section>

      <section aria-label="Source health">
        <h2>Source health</h2>
        {SOURCE_KEYS.map((key) => (
          <p key={key}>
            <SourceHealthBadge source={key} health={sources[key] ?? "UNKNOWN"} />
          </p>
        ))}
      </section>

      {loading ? <LoadingState label="Updating…" /> : null}

      <AddSiteDialog open={addSiteOpen} onClose={() => setAddSiteOpen(false)} onSuccess={onSiteAdded} />
    </>
  );
}
