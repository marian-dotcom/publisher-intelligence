"use client";

/** EP-025b M3 / EP-029 M2a — operational timeline with site scoping.
 * Supports filtering by selected site; each item shows its site/domain.
 * Explicit "All sites" mode preserves tenant-wide view.
 */

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  ObservedAt,
  ProvenanceBadge,
  SeverityBadge,
  StatusChip,
  TemporalUncertainty,
} from "@/components/domain";
import { EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type { TimelineEntry, TimelineResponse, SiteSummary } from "@/lib/api-types";

function TimelineEntryView({
  entry,
  siteName,
}: { entry: TimelineEntry; siteName: string }) {
  if (entry.provenance === "human_reported") {
    return (
      <li className="timeline-entry timeline-human">
        <div className="entry-meta">
          <ProvenanceBadge provenance="human_reported" />
          <span className="entry-site">{siteName}</span>
        </div>
        <p className="entry-text">{entry.text}</p>
        <ObservedAt observedAt={entry.observed_at} />
      </li>
    );
  }
  return (
    <li className="timeline-entry timeline-machine">
      <div className="entry-head">
        <ProvenanceBadge provenance="machine_observed" />
        <SeverityBadge severity={entry.severity ?? null} />
        <StatusChip status={entry.status} />
        <span className="entry-site">{siteName}</span>
      </div>
      {/* Temporal semantics are preserved exactly: exact vs bounded vs unknown. */}
      <TemporalUncertainty
        precision={entry.time_precision}
        occurredAt={entry.occurred_at}
        windowStart={entry.occurrence_window_start}
        windowEnd={entry.occurrence_window_end}
      />
      <ObservedAt observedAt={entry.observed_at} />
      <p className="entry-text">{String(entry.event_type)}</p>
    </li>
  );
}

function SiteFilter({
  sites,
  selectedSiteId,
  onChange,
}: { sites: SiteSummary[]; selectedSiteId: string | null; onChange: (id: string | null) => void }) {
  return (
    <div className="timeline-filter">
      <label className="field" htmlFor="timeline-site-filter">
        Filter by site
      </label>
      <select
        id="timeline-site-filter"
        className="input"
        value={selectedSiteId ?? "all"}
        onChange={(e) => onChange(e.target.value === "all" ? null : e.target.value)}
      >
        <option value="all">All sites</option>
        {sites.map((site) => (
          <option key={site.site_id} value={site.site_id}>
            {site.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function TimelinePage() {
  const searchParams = useSearchParams();
  const initialSiteId = searchParams.get("site_id");

  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const [sites, setSites] = useState<SiteSummary[]>([]);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(initialSiteId);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        // Fetch sites for the filter dropdown
        const homeStatus = await apiFetch<{ sites: SiteSummary[] }>("/product/home/status");
        if (!cancelled) setSites(homeStatus.sites);

        // Fetch timeline with optional site filter (encoded site id)
        const url = selectedSiteId
          ? `/timeline?site_id=${encodeURIComponent(selectedSiteId)}`
          : "/timeline";
        const data = await apiFetch<TimelineResponse>(url);
        if (!cancelled) setEntries(data.entries);
      } catch {
        if (!cancelled) setError("Could not load the timeline. Try again.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedSiteId]);

  function handleSiteChange(siteId: string | null) {
    setSelectedSiteId(siteId);
    const params = new URLSearchParams(searchParams.toString());
    if (siteId) params.set("site_id", siteId);
    else params.delete("site_id");
    window.history.replaceState(null, "", `/timeline?${params.toString()}`);
  }

  if (error) return <ErrorState message={error} />;
  if (entries === null) return <LoadingState label="Loading timeline…" />;

  // Build site name lookup
  const siteNames = new Map((sites ?? []).map((s) => [s.site_id, s.name]));

  const filteredEntries = entries ?? [];
  const isFiltered = selectedSiteId !== null;

  if (filteredEntries.length === 0) {
    return (
      <>
        <h1>Timeline</h1>
        <SiteFilter sites={sites} selectedSiteId={selectedSiteId} onChange={handleSiteChange} />
        <EmptyState
          message={isFiltered
            ? "No events for this site yet."
            : "No operational activity recorded yet."}
        />
      </>
    );
  }

  return (
    <>
      <h1>Timeline</h1>
      <SiteFilter sites={sites} selectedSiteId={selectedSiteId} onChange={handleSiteChange} />
      <ol className="timeline-list">
        {filteredEntries.map((entry) => (
          <TimelineEntryView
            key={"event_id" in entry ? entry.event_id : entry.note_id}
            entry={entry}
            siteName={siteNames.get(entry.site_id) ?? entry.site_id}
          />
        ))}
      </ol>
    </>
  );
}
