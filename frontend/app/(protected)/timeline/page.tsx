"use client";

/** EP-025b M3 — operational timeline: machine_observed + human_reported entries. */

import { useEffect, useState } from "react";

import {
  ObservedAt,
  ProvenanceBadge,
  SeverityBadge,
  StatusChip,
  TemporalUncertainty,
} from "@/components/domain";
import { EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type { TimelineEntry, TimelineResponse } from "@/lib/api-types";

function TimelineEntryView({ entry }: { entry: TimelineEntry }) {
  if (entry.provenance === "human_reported") {
    return (
      <li className="timeline-entry timeline-human">
        <ProvenanceBadge provenance="human_reported" />
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

export default function TimelinePage() {
  const [entries, setEntries] = useState<TimelineEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<TimelineResponse>("/timeline")
      .then((data) => {
        if (!cancelled) setEntries(data.entries);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load the timeline. Try again.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ErrorState message={error} />;
  if (entries === null) return <LoadingState label="Loading timeline…" />;
  if ((entries?.length ?? 0) === 0)
    return (
      <>
        <h1>Timeline</h1>
        <EmptyState message="No operational activity recorded yet." />
      </>
    );

  return (
    <>
      <h1>Timeline</h1>
      <ol className="timeline-list">
        {(entries ?? []).map((entry) => (
          <TimelineEntryView key={"event_id" in entry ? entry.event_id : entry.note_id} entry={entry} />
        ))}
      </ol>
    </>
  );
}
