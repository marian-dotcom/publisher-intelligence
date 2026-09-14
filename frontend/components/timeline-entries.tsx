/** EP-025b / EP-031 M4 — shared canonical timeline entry renderer.
 * Used by both the /timeline page and Site Overview recent activity.
 * Semantic rendering rules are defined here once; screens must not reimplement them. */

import type { TimelineEntry } from "@/lib/api-types";
import {
  ObservedAt,
  ProvenanceBadge,
  SeverityBadge,
  StatusChip,
  TemporalUncertainty,
} from "@/components/domain";

export function TimelineEntryView({
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