"use client";

/**
 * EP-031 M2 — per-site overview route (read-only operational drill-down of Home,
 * ADR-002: no new primary navigation area). Renders the site identity header
 * and reuses the existing MonitoringCard; the M3/M4 panels are NOT implemented
 * here. Navigation contract (Home): `/sites/<encoded-site-id>`.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { Card, EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { StatusChip } from "@/components/domain";
import { MonitoringCard } from "@/components/monitoring-controls";
import { apiFetch, ApiError } from "@/lib/api";
import type { SiteOverviewResponse } from "@/lib/api-types";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function SiteOverviewRoute() {
  const params = useParams();
  const siteIdParam = params.site_id;
  const site_id = typeof siteIdParam === "string" ? siteIdParam : "";
  const [overview, setOverview] = useState<SiteOverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // No API request until a valid non-empty site id exists.
    if (site_id.length === 0) {
      return;
    }
    let cancelled = false;
    (async () => {
      setError(null);
      setLoading(true);
      try {
        const data = await apiFetch<SiteOverviewResponse>(
          `/product/sites/${encodeURIComponent(site_id)}/overview`,
        );
        if (!cancelled) setOverview(data);
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError) {
            if (e.status === 404) {
              setError("Site not found.");
            } else if (e.kind === "unauthorized") {
              setError("Authentication required.");
            } else if (e.kind === "forbidden") {
              setError("Access denied.");
            } else {
              setError("Could not load site overview. Try again.");
            }
          } else {
            setError("Could not load site overview. Try again.");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [site_id]);

  // Post-mutation refetch for the reused MonitoringCard. Refuses a stale
  // completion once the route's site id has moved on; a transient refetch
  // failure keeps the current (pre-mutation) projection.
  async function handleRefetch(requestSiteId: string) {
    if (requestSiteId !== site_id) return;
    try {
      const data = await apiFetch<SiteOverviewResponse>(
        `/product/sites/${encodeURIComponent(site_id)}/overview`,
      );
      setOverview(data);
    } catch {
      // Keep the current projection on a transient refetch failure.
    }
  }

  if (site_id.length === 0) {
    return (
      <>
        <h1>Site Overview</h1>
        <EmptyState message="Select a site to view its overview." />
      </>
    );
  }
  if (loading) return <LoadingState label="Loading site overview…" />;
  if (error) return <ErrorState message={error} />;
  if (!overview) return <EmptyState message="No site overview available." />;

  const { site, monitoring } = overview;

  return (
    <>
      <h1>Site Overview</h1>

      <section aria-label="Site information">
        <Card title={site.name}>
          <dl className="site-overview-identity">
            <dt>URL</dt>
            <dd>{site.url}</dd>
            {site.publisher_name && (
              <>
                <dt>Publisher</dt>
                <dd>{site.publisher_name}</dd>
              </>
            )}
            <dt>Status</dt>
            <dd><StatusChip status={site.status} /></dd>
            <dt>Timezone</dt>
            <dd>{site.timezone}</dd>
            <dt>Registered</dt>
            <dd>{formatDate(site.created_at)}</dd>
          </dl>
        </Card>
      </section>

      <section aria-label="Automatic monitoring">
        <MonitoringCard
          monitoring={monitoring}
          siteId={site.site_id}
          onRefetch={(requestSiteId) => void handleRefetch(requestSiteId)}
        />
      </section>
    </>
  );
}