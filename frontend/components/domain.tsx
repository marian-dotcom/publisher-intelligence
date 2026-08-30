/** EP-025b — domain-aware semantic components.
 * Contractual rendering rules live here; screens must not reinterpret them.
 */

import type {
  BrowserAccessClassification,
  Confidence,
  DiagnosticStatus,
  EvidenceRelation,
  EvidenceSourceKind,
  HypothesisStatus,
  InitialDiagnostic,
  LastKnownGoodReference,
  MonetizationCapability,
  Severity,
  SourceHealth,
  SourceKey,
} from "@/lib/api-types";

const SOURCE_LABELS: Record<SourceKey, string> = {
  BROWSER_MONITORING: "Browser Monitoring",
  GA4: "GA4",
  GSC: "Search Console",
  GAM: "Ad Manager",
  PUBLIC_CONFIG: "Public Config",
};

const HEALTHY_STATES: SourceHealth[] = ["HEALTHY"];
const FAILURE_STATES: SourceHealth[] = ["ACTION_REQUIRED", "BLOCKED"];

export function SourceHealthBadge({ source, health }: { source: SourceKey; health: SourceHealth }) {
  // UNKNOWN is rendered as absence-of-evidence, visually distinct from failure
  // states; STALE is data freshness, also distinct from failure/degraded.
  const tone = HEALTHY_STATES.includes(health)
    ? "healthy"
    : FAILURE_STATES.includes(health)
      ? "failure"
      : health === "DEGRADED"
        ? "degraded"
        : health === "STALE"
          ? "stale"
          : "unknown";
  const meaning =
    health === "UNKNOWN"
      ? `${SOURCE_LABELS[source]}: no evidence available`
      : health === "STALE"
        ? `${SOURCE_LABELS[source]}: no trustworthy new evidence within its freshness window`
        : `${SOURCE_LABELS[source]}: ${health.toLowerCase()}`;
  return (
    <span className={`badge badge-${tone}`} title={meaning}>
      {`${SOURCE_LABELS[source]} · ${health}`}
    </span>
  );
}

export function SiteCondition({ condition }: { condition: string }) {
  // Publisher/site condition is its own fact; never derived from source health.
  return (
    <span className="condition" title="Publisher/site condition">{`Publisher/site: ${condition}`}</span>
  );
}

export function MonetizationCapabilityView({ capability }: { capability: MonetizationCapability }) {
  const label =
    capability === "RELATIVE_ONLY"
      ? "Monetization: relative metrics only"
      : capability === "ABSOLUTE"
        ? "Monetization: absolute values available"
        : "Monetization: unknown";
  return (
    <span className={`badge badge-mono-${capability.toLowerCase()}`} title={label}>
      {label}
    </span>
  );
}

export function ProvenanceBadge({ provenance }: { provenance: "machine_observed" | "human_reported" }) {
  return (
    <span className={`provenance provenance-${provenance}`}>
      {provenance === "machine_observed" ? "Machine observed" : "Human reported"}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity | string | null }) {
  if (!severity) return null;
  return <span className={`severity severity-${severity.toLowerCase()}`}>{severity}</span>;
}

export interface OccurrenceInput {
  time_precision: string | null;
  occurred_at: string | null;
  occurrence_window_start?: string | null;
  occurrence_window_end?: string | null;
}

/** Temporal uncertainty is preserved visibly: EXACT shows occurred_at; WINDOW
 * shows bounds; anything else shows explicitly unknown. observed_at is never
 * substituted for occurred_at. */
export function TemporalUncertainty({
  precision,
  occurredAt,
  windowStart = null,
  windowEnd = null,
}: {
  precision: string;
  occurredAt?: string | null;
  windowStart?: string | null;
  windowEnd?: string | null;
}) {
  if (precision === "EXACT" && occurredAt) {
    return <span className="temporal">{`Occurred at ${new Date(occurredAt).toLocaleString()}`}</span>;
  }
  if (precision === "WINDOW" && windowStart && windowEnd) {
    return (
      <span className="temporal">{`Occurred between ${new Date(windowStart).toLocaleString()} and ${new Date(windowEnd).toLocaleString()}`}</span>
    );
  }
  return <span className="temporal temporal-unknown">Occurrence time not established</span>;
}

export function ObservedAt({ observedAt }: { observedAt: string | null }) {
  if (!observedAt) return null;
  return <span className="observed">Observed {new Date(observedAt).toLocaleString()}</span>;
}

/** LEADING is the current deterministic ranking — never a proven cause. */
export function HypothesisRank({ status, rank }: { status: HypothesisStatus; rank: number }) {
  const label =
    status === "LEADING"
      ? `Leading hypothesis · rank ${rank}`
      : `${status.charAt(0)}${status.slice(1).toLowerCase()} · rank ${rank}`;
  return (
    <span className={`hypothesis-rank hypothesis-${status.toLowerCase()}`} title={label}>
      {label}
    </span>
  );
}

export function ConfidenceLabel({ confidence }: { confidence: Confidence }) {
  return <span className="confidence">Confidence: {confidence}</span>;
}

const RELATION_COPY: Record<EvidenceRelation, string> = {
  SUPPORTS: "Supports",
  CONTRADICTS: "Contradicts",
  CONTEXT: "Context",
};

export function EvidenceRelationView({
  relation,
  sourceKind,
}: {
  relation: EvidenceRelation;
  sourceKind: EvidenceSourceKind;
}) {
  // Observation gaps are missing/unavailable context — never contradictions.
  const isGap = sourceKind === "OBSERVATION_GAP";
  const tone = isGap ? "gap" : relation.toLowerCase();
  const label =
    sourceKind === "OBSERVATION_GAP" ? "Evidence not observed / unavailable" : RELATION_COPY[relation];
  return (
    <span className={`evidence-relation relation-${tone}`}>
      {label}
      <span className="relation-kind"> ({sourceKind === "OBSERVATION_GAP" ? "observation gap" : sourceKind.replace("_", " ").toLowerCase()})</span>
    </span>
  );
}

/** LKG is a frozen baseline selected at a point in time — never current truth. */
export function LastKnownGoodCard({ reference: lkg }: { reference: LastKnownGoodReference }) {
  return (
    <div className="card lkg-card">
      <span className="lkg-title">Last known good (frozen baseline)</span>
      <p>
        Scope {lkg.scope_key} · selected {new Date(lkg.selected_at).toLocaleString()} via{" "}
        {lkg.selection_method} ({lkg.selection_version})
      </p>
      <p className="lkg-reason">{lkg.reason}</p>
    </div>
  );
}

export function StatusChip({ status }: { status: string }) {
  return <span className={`status-chip status-${status.toLowerCase()}`}>{status}</span>;
}

// ---------- EP-028 M3 — initial diagnostic projection ----------

const DIAGNOSTIC_STATUS_LABELS: Record<DiagnosticStatus, string> = {
  PENDING: "Diagnostic: queued",
  RUNNING: "Diagnostic: running",
  COMPLETE: "Diagnostic: complete",
  PARTIAL: "Diagnostic: partial",
  SITE_ERROR: "Diagnostic: site error",
  BROWSER_ERROR: "Diagnostic: browser error",
  TIMEOUT: "Diagnostic: timed out",
  BLOCKED: "Diagnostic: blocked",
};

const CLASSIFICATION_LABELS: Record<BrowserAccessClassification, string> = {
  ok: "Access: normal",
  degraded: "Access: degraded",
  challenge_suspected: "Access: challenge suspected",
};

function isDiagnosticStatus(value: string): value is DiagnosticStatus {
  return value in DIAGNOSTIC_STATUS_LABELS;
}

function isBrowserAccessClassification(value: string): value is BrowserAccessClassification {
  return value in CLASSIFICATION_LABELS;
}

export function InitialDiagnosticBadge({ diagnostic }: { diagnostic: InitialDiagnostic | null }) {
  if (!diagnostic) {
    return (
      <span className="badge badge-diagnostic-unknown" title="Diagnostic: not available">
        Diagnostic: not available
      </span>
    );
  }
  const statusLabel = isDiagnosticStatus(diagnostic.status)
    ? DIAGNOSTIC_STATUS_LABELS[diagnostic.status]
    : "Diagnostic: unknown";
  const classLabel =
    diagnostic.browser_access_classification !== null &&
    isBrowserAccessClassification(diagnostic.browser_access_classification)
      ? CLASSIFICATION_LABELS[diagnostic.browser_access_classification]
      : null;
  return (
    <span className="badge badge-diagnostic" title={statusLabel}>
      {statusLabel}
      {classLabel ? ` · ${classLabel}` : ""}
    </span>
  );
}
