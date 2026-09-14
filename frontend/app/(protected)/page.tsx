"use client";

/** EP-028 M3 — Home: site selector, add site, site condition, initial diagnostic, source health.
 * EP-029 M2a — adds View diagnostic results action for DIAGNOSTIC/OPERATOR_UI runs. */

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { AddSiteDialog } from "@/components/add-site-dialog";
import {
  InitialDiagnosticBadge,
  MonetizationCapabilityView,
  SiteCondition,
  SourceHealthBadge,
} from "@/components/domain";
import { MonitoringCard } from "@/components/monitoring-controls";
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
  const router = useRouter();
  const [home, setHome] = useState<HomeStatus | null>(null);
  const [detailHealth, setDetailHealth] = useState<SourceHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [siteParam, setSiteParam] = useState<string | undefined>(undefined);
  const [addSiteOpen, setAddSiteOpen] = useState(false);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const siteGenRef = useRef(0);
  // Render-visible mirror of the monitoring selection generation (bumped at
  // site change/add and refresh; deliberately separate from siteGenRef's
  // poll-invalidation bump). Needed for the MonitoringCard key/guard without
  // reading a ref during render (react-hooks/refs).
  const [monitoringGen, setMonitoringGen] = useState(0);
  const monitoringGenRef = useRef(0);

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
    monitoringGenRef.current += 1;
    setMonitoringGen((g) => g + 1);
    setSiteParam(next === "" ? undefined : next);
    setLoading(true);
    setDetailHealth(null);
  }

  function onSiteAdded(siteId: string) {
    setAddSiteOpen(false);
    setDetailHealth(null);
    // Invalidate any in-flight poll before selecting the new site.
    siteGenRef.current += 1;
    monitoringGenRef.current += 1;
    setMonitoringGen((g) => g + 1);
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    setSiteParam(siteId);
    setLoading(true);
  }

  function onViewDiagnosticResults(siteId: string) {
    router.push(`/diagnostic-results?site_id=${encodeURIComponent(siteId)}`);
  }

  // Refetch the currently-selected site's home status after a monitoring
  // mutation. Generation-guarded so a response for an older selection can never
  // overwrite the current site's data.
  const refreshHome = useCallback(async () => {
    siteGenRef.current += 1;
    monitoringGenRef.current += 1;
    setMonitoringGen((g) => g + 1);
    const gen = siteGenRef.current;
    if (pollTimerRef.current !== null) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    try {
      const status = await apiFetch<HomeStatus>(
        `/product/home/status${siteParam ? `?site_id=${siteParam}` : ""}`,
      );
      if (gen !== siteGenRef.current) return;
      setHome(status);
      if (status.selected_site_id) {
        const detail = await apiFetch<SourceHealthResponse>(
          `/product/source-health?site_id=${status.selected_site_id}`,
        );
        if (gen !== siteGenRef.current) return;
        setDetailHealth(detail);
      } else {
        if (gen !== siteGenRef.current) return;
        setDetailHealth(null);
      }
    } catch {
      // The dialog already surfaces mutation failures; a refetch that fails
      // transiently simply keeps the current (pre-mutation) projection.
    }
  }, [siteParam]);

  const sources: Record<SourceKey, SourceHealth> =
    detailHealth?.sources ?? home?.source_health ?? ({} as Record<SourceKey, SourceHealth>);

  if (error) return <ErrorState message={error} />;
  if (home === null)
    return initialLoading ? (
      <LoadingState label="Loading home…" />
    ) : (
      <EmptyState message="No sites are connected yet. Connect a site to see operational status." />
    );

  const selectedSite = home.sites?.find((s) => s.site_id === home.selected_site_id);
  const hasDiagnostic = home.initial_diagnostic !== null;
  const diagnosticStatus = hasDiagnostic ? home.initial_diagnostic!.status : null;
  const isTerminal = diagnosticStatus !== null && diagnosticStatus !== "PENDING" && diagnosticStatus !== "RUNNING";

  // Capture the selection generation for this render (via the render-visible
  // monitoringGen mirror, kept in lockstep with siteGenRef). MonitoringCard is
  // keyed by selection+generation and handed a generation-guarded refetch so a
  // mutation that started for an older selection can never close/reset this
  // card's dialog or refetch once the selection/generation has moved on. The
  // server mutation remains valid for its original site, but its stale
  // completion produces no current-page UI effect.
  const selectedSiteId = home.selected_site_id;
  const monitoringOnRefetch = (requestSiteId: string) => {
    if (
      monitoringGenRef.current !== monitoringGen ||
      selectedSiteId !== requestSiteId
    ) {
      return;
    }
    return refreshHome();
  };

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
        {selectedSite && (
          <Button
            variant="secondary"
            onClick={() => router.push(`/sites/${encodeURIComponent(selectedSite.site_id)}`)}
          >
            Overview
          </Button>
        )}
        {selectedSite && hasDiagnostic && (
          <Button
            variant={isTerminal ? "primary" : "secondary"}
            onClick={() => onViewDiagnosticResults(selectedSite.site_id)}
            disabled={!isTerminal}
            title={isTerminal ? "View full diagnostic results" : "Diagnostic not yet complete"}
          >
            View diagnostic results
          </Button>
        )}
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

      <section aria-label="Automatic monitoring">
        {/* Monitoring authorization is a separate fact from source health,
            diagnostic status, and site lifecycle. */}
        <MonitoringCard
          key={`${selectedSiteId ?? "none"}:${monitoringGen}`}
          monitoring={home.monitoring}
          siteId={selectedSiteId}
          onRefetch={monitoringOnRefetch}
        />
      </section>

      {loading ? <LoadingState label="Updating…" /> : null}

      <AddSiteDialog open={addSiteOpen} onClose={() => setAddSiteOpen(false)} onSuccess={onSiteAdded} />
    </>
  );
}
