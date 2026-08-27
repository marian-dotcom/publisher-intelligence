/**
 * EP-025b M0 - frontend-facing API contracts derived from merged EP-025a.
 *
 * Every type mirrors the exact JSON serialized by the backend routes in
 * backend/app/api/{product,memory,investigations}.py and backend/app/auth/routes.py
 * at main commit c71c015. Nullable fields, enum values and temporal/provenance
 * semantics are contractual: the UI must not reinterpret them.
 */

// ---------- shared primitives ----------

/** ISO-8601 datetime string (backend serializes via datetime.isoformat()). */
export type Iso = string;

export type SourceKey = "BROWSER_MONITORING" | "GA4" | "GSC" | "GAM" | "PUBLIC_CONFIG";

/**
 * Source health states. UNKNOWN means lack of evidence; it is distinct from
 * DEGRADED (evidence exists but quality/state is degraded) and neither may be
 * rendered as publisher/site failure. STALE (EP-026 M3b) means the latest
 * trustworthy successful observation from this source is older than its
 * freshness window — a source-data fact, never publisher/site failure.
 */
export type SourceHealth = "HEALTHY" | "STALE" | "DEGRADED" | "UNAVAILABLE" | "ACTION_REQUIRED" | "BLOCKED" | "UNKNOWN";

export type MonetizationCapability = "ABSOLUTE" | "RELATIVE_ONLY" | "UNKNOWN";

/** EP-028 M3 — bounded initial-diagnostic status (checkpoint_runs.status CHECK). */
export type DiagnosticStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETE"
  | "PARTIAL"
  | "SITE_ERROR"
  | "BROWSER_ERROR"
  | "TIMEOUT"
  | "BLOCKED";

/** EP-028 M3 — bounded browser access classification. */
export type BrowserAccessClassification = "ok" | "degraded" | "challenge_suspected";

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

/** Incident lifecycle status (canonical check constraint). */
export type IncidentStatus = "OPEN" | "INVESTIGATING" | "RESOLVED" | "CLOSED_UNRESOLVED";

export type SymptomFamily =
  | "GAM_ADSERVING"
  | "SEARCH_DISCOVER"
  | "CONSENT_CMP"
  | "PREBID_HEADER_BIDDING"
  | "VIDEO"
  | "BROWSER_PERFORMANCE"
  | "ANALYTICS_MEASUREMENT"
  | "EXTERNAL_INFRASTRUCTURE"
  | "REPORTING_DISCREPANCY"
  | "POLICY_COMPLIANCE"
  | "PROGRAMMATIC_MARKET"
  | "OTHER";

export type HypothesisStatus = "LEADING" | "CONTENDER" | "WEAKENED" | "UNRESOLVED";
export type Confidence = "LOW" | "MEDIUM" | "HIGH";

/** Relation is canonical; source_kind OBSERVATION_GAP carries missing/unavailable semantics. */
export type EvidenceRelation = "SUPPORTS" | "CONTRADICTS" | "CONTEXT";
export type EvidenceSourceKind = "EVENT" | "MANUAL_NOTE" | "OBSERVATION_GAP";

// ---------- auth ----------

export interface LoginSuccess {
  actor_subject_id: string;
  role: string;
  /** Server-generated CSRF token; must be echoed as X-CSRF-Token on writes. */
  csrf_token: string;
}

/** GET /auth/session */
export interface SessionState {
  actor_subject_id: string;
  tenant_id: string;
  role: string;
}

/** POST /auth/logout */
export interface LogoutResult {
  revoked: boolean;
}

// ---------- home / source health ----------

export interface SiteSummary {
  site_id: string;
  name: string;
}

/** GET /product/home/status */
export interface HomeStatus {
  sites: SiteSummary[];
  selected_site_id: string | null;
  publisher_site_condition: string; // site status; independent of source_health by contract
  source_health: Record<SourceKey, SourceHealth>;
  initial_diagnostic: InitialDiagnostic | null;
  open_incident_count: number;
  monetization_capability: MonetizationCapability;
}

/** EP-028 M2 — bounded initial-diagnostic projection for operator registration. */
export interface InitialDiagnostic {
  run_id: string;
  status: string;
  completed_at: string | null;
  browser_access_classification: string | null;
}

/** GET /product/source-health?site_id={id} (required param) */
export interface SourceHealthResponse {
  site_id: string;
  sources: Record<SourceKey, SourceHealth>;
}

// ---------- timeline ----------

export type TimePrecision = "EXACT" | "WINDOW" | "UNKNOWN";

interface TimelineBase {
  severity?: Severity | null;
  site_id: string;
}

export interface MachineTimelineEntry extends TimelineBase {
  entry_kind: "machine_observed";
  event_id: string;
  event_type: string;
  source: string;
  provenance: "machine_observed";
  status: string;
  time_precision: TimePrecision;
  observed_at: Iso;
  /** Only present when time_precision === "EXACT". Never fabricate. */
  occurred_at: Iso | null;
  occurrence_window_start: Iso | null;
  occurrence_window_end: Iso | null;
}

export interface HumanTimelineEntry extends TimelineBase {
  entry_kind: "human_reported";
  note_id: string;
  note_type: string;
  provenance: "human_reported";
  source: string;
  observed_at: Iso;
  occurred_at: Iso | null;
  text: string;
}

export type TimelineEntry = MachineTimelineEntry | HumanTimelineEntry;

/** GET /timeline */
export interface TimelineResponse {
  entries: TimelineEntry[];
}

// ---------- incidents ----------

export interface IncidentListItem {
  incident_id: string;
  title: string;
  symptom_family: SymptomFamily;
  status: IncidentStatus;
  severity: Severity | null;
  reported_start_at: Iso | null;
  reported_end_at: Iso | null;
  opened_at: Iso;
  site_id: string;
}

/** GET /incidents */
export interface IncidentListResponse {
  incidents: IncidentListItem[];
}

export interface SymptomSegment {
  dimension: string;
  operator: string;
  value: string;
  source: string;
}

export interface LastKnownGoodReference {
  reference_id: string;
  checkpoint_run_id: string;
  scope_key: string;
  selection_method: string;
  selection_version: string;
  selected_at: Iso;
  reason: string;
  fingerprints: Record<string, string>;
}

export interface EvidenceRelationship {
  evidence_id: string;
  evidence_key: string;
  relation: EvidenceRelation;
  source_kind: EvidenceSourceKind;
  event_id: string | null;
  manual_note_id: string | null;
  reason: string | null;
}

export interface Hypothesis {
  hypothesis_id: string;
  hypothesis_key: string;
  family: string;
  statement: string;
  status: HypothesisStatus;
  confidence: Confidence;
  rank: number;
  supporting_count: number;
  contradicting_count: number;
  rationale: string;
  engine_version: string;
  evidence: EvidenceRelationship[];
}

export interface MetricPointView {
  period_start: Iso;
  period_end: Iso;
  value: number;
  freshness_status: string;
}

export interface MonetizationMetric {
  metric_code: string;
  unit: string; // COUNT | RATIO | NUMBER | CURRENCY (gated server-side)
  source: string;
  granularity: string;
  points: MetricPointView[];
}

export interface MonetizationSection {
  capability: MonetizationCapability;
  /** Empty under UNKNOWN; CURRENCY-unit series suppressed under RELATIVE_ONLY. */
  metrics: MonetizationMetric[];
}

export interface IncidentDetail {
  incident_id: string;
  title: string;
  symptom_family: SymptomFamily;
  description: string;
  status: IncidentStatus;
  severity: Severity | null;
  reported_start_at: Iso | null;
  reported_end_at: Iso | null;
  opened_at: Iso;
  resolved_at: Iso | null;
  resolution_summary: string | null;
  site_id: string;
}

/** GET /incidents/{incident_id} */
export interface IncidentDetailResponse {
  incident: IncidentDetail;
  symptom_segments: SymptomSegment[];
  last_known_good_references: LastKnownGoodReference[];
  hypotheses: Hypothesis[];
  monetization: MonetizationSection;
}

// ---------- evidence pack ----------

export interface EvidencePackMeta {
  pack_id: string;
  site_id: string;
  incident_id: string | null;
  window_start: Iso;
  window_end: Iso;
  fingerprints: Record<string, string>;
  content_hash: string;
  engine_version: string;
  created_at: Iso;
}

/**
 * Deterministic builder-whitelisted content sections. Sections are lists of
 * product-safe objects; the frontend renders them read-only and never treats
 * them as recomputable.
 */
export interface EvidencePackContent {
  engine_version: string | null;
  window: { start: Iso; end: Iso } | null;
  incident:
    | {
        id: string;
        title: string;
        symptom_family: string;
        description: string;
        reported_start_at: Iso | null;
        reported_end_at: Iso | null;
        status: string;
        symptom_segments: { dimension: string; operator: string; value: string; source: string }[];
      }
    | null;
  machine_observed_sections: string[] | null;
  scheduled_checkpoints: {
    run_id: string;
    scenario_id: string;
    observation_kind: string;
    status: string;
    scheduled_for: Iso | null;
    collector_bundle_version: string;
    limitations: string[];
  }[];
  public_config_states: {
    snapshot_id: string;
    config_type: string;
    parse_status: string;
    observed_at: Iso | null;
    fetch_kind: string;
    normalizer_version: string;
  }[];
  events: {
    event_id: string;
    definition_id: string;
    status: string;
    severity: string | null;
    detected_at: Iso | null;
    occurred_before_at: Iso | null;
    summary: string;
  }[];
  relations: {
    from_event_id: string;
    to_event_id: string;
    relation_type: string;
    confidence: string;
    engine_version: string;
  }[];
  human_reported_notes: {
    note_id: string;
    note_type: string;
    text: string;
    occurred_at: Iso | null;
    source: string;
    created_at: Iso | null;
    evidence_source: string;
  }[];
  human_reported_notes_count: number | null;
}

/** GET /evidence/packs/{pack_id} */
export interface EvidencePackResponse {
  pack: EvidencePackMeta;
  content: EvidencePackContent;
}

// ---------- investigate intake ----------

export interface InvestigateRequest {
  site_id: string;
  title: string;
  symptom_family?: string; // default OTHER, validated server-side
  description: string;
  /** Optional ISO bounds; end-before-start rejected server-side. */
  reported_start_at?: Iso;
  reported_end_at?: Iso;
}

/** POST /investigations success body (intentionally minimal). */
export interface InvestigateSuccess {
  incident_id: string;
  investigation_key: string;
  status: IncidentStatus;
}

/** POST /product/sites success body (EP-028 M3). */
export interface RegisterSiteSuccess {
  site_id: string;
  canonical_domain: string;
  checkpoint_run_id: string;
  diagnostic_status: string;
}
