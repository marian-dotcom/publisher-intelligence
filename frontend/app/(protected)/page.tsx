"use client";

/** EP-025b M2 — Home: selected site, site condition, source health, monetization. */

import { useEffect, useState } from "react";

import {
  MonetizationCapabilityView,
  SiteCondition,
  SourceHealthBadge,
} from "@/components/domain";
import { EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type { HomeStatus, SourceHealth, SourceHealthResponse, SourceKey } from "@/lib/api-types";

const SOURCE_KEYS: SourceKey[] = ["BROWSER_MONITORING", "GA4", "GSC", "GAM"];

export default function HomePage() {
  const [home, setHome] = useState<HomeStatus | null>(null);
  const [detailHealth, setDetailHealth] = useState<SourceHealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [siteParam, setSiteParam] = useState<string | undefined>(undefined);

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

  function onSiteChange(next: string) {
    // Event-handler state updates are allowed to be synchronous.
    setSiteParam(next === "" ? undefined : next);
    setLoading(true);
    setDetailHealth(null);
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
      </div>

      <section aria-label="Publisher and site condition">
        {/* Site condition is independent of source observation states. */}
        <SiteCondition condition={home.publisher_site_condition} />
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
    </>
  );
}
