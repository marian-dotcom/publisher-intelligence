"use client";

/** EP-025b M4 — incident list, detail (hypotheses/evidence/LKG/monetization),
 * and the frozen evidence-pack view. */

import { useEffect, useState } from "react";
import Link from "next/link";

import {
  ConfidenceLabel,
  EvidenceRelationView,
  HypothesisRank,
  LastKnownGoodCard,
  MonetizationCapabilityView,
  SeverityBadge,
  StatusChip,
} from "@/components/domain";
import { EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type {
  IncidentDetailResponse,
  IncidentListResponse,
} from "@/lib/api-types";

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<IncidentListResponse["incidents"] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<IncidentListResponse>("/incidents")
      .then((data) => {
        if (!cancelled) setIncidents(data.incidents);
      })
      .catch(() => {
        if (!cancelled) setError("Could not load incidents. Try again.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <ErrorState message={error} />;
  if (incidents === null) return <LoadingState label="Loading incidents…" />;
  if (incidents.length === 0)
    return (
      <>
        <h1>Incidents</h1>
        <EmptyState message="No incidents recorded. Open Investigate to report a symptom." />
      </>
    );

  return (
    <>
      <h1>Incidents</h1>
      <ul className="incident-list">
        {incidents.map((incident) => (
          <li key={incident.incident_id}>
            <Link href={`/incidents/${incident.incident_id}`} className="card incident-card">
              <strong>{incident.title}</strong>
              <span>{incident.symptom_family}</span>
              <StatusChip status={incident.status} />
              <SeverityBadge severity={incident.severity} />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

export function IncidentDetailView({ incidentId }: { incidentId: string }) {
  const [detail, setDetail] = useState<IncidentDetailResponse | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch<IncidentDetailResponse>(`/incidents/${incidentId}`)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch((apiError: { kind: string }) => {
        if (cancelled) return;
        if (apiError.kind === "not_found") setNotFound(true);
        else setError("Could not load this incident.");
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  if (notFound)
    return <ErrorState message="This incident was not found." />;
  if (error) return <ErrorState message={error} />;
  if (detail === null) return <LoadingState label="Loading incident…" />;

  const inc = detail.incident;
  return (
    <article>
      {/* 1. Symptom summary */}
      <h1>{inc.title}</h1>
      <p className="entry-text">{inc.description}</p>
      <p>
        <StatusChip status={inc.status} />
        <SeverityBadge severity={inc.severity} />
        <span className="temporal"> · {inc.symptom_family}</span>
      </p>

      {/* 2. Temporal localization: bounded window preserved; unknown stays unknown. */}
      <section aria-label="Temporal localization">
        <h2>When</h2>
        {inc.reported_start_at ? (
          <p>
            Reported between {new Date(inc.reported_start_at).toLocaleString()}
            {inc.reported_end_at ? ` and ${new Date(inc.reported_end_at).toLocaleString()}` : " and now (end unknown)"}
          </p>
        ) : (
          <p className="temporal temporal-unknown">Reported onset not established</p>
        )}
        <p>Opened {new Date(inc.opened_at).toLocaleString()}</p>
      </section>

      {/* 3–4. Ranked hypotheses with grouped evidence relationships */}
      <section aria-label="Hypotheses">
        <h2>Hypotheses (current ranking)</h2>
        {detail.hypotheses.length === 0 ? (
          <EmptyState message="No hypotheses have been established for this incident." />
        ) : (
          detail.hypotheses.map((hypothesis) => (
            <div key={hypothesis.hypothesis_id} className={`card hypothesis hypothesis-${hypothesis.status.toLowerCase()}`}>
              <HypothesisRank status={hypothesis.status} rank={hypothesis.rank} />
              <ConfidenceLabel confidence={hypothesis.confidence} />
              <p className="entry-text">{hypothesis.statement}</p>
              <p className="lkg-reason">{hypothesis.rationale}</p>
              <ul className="evidence-list">
                {hypothesis.evidence.map((evidence) => (
                  <li key={evidence.evidence_id}>
                    <EvidenceRelationView relation={evidence.relation} sourceKind={evidence.source_kind} />
                    {evidence.reason ? <span> — {evidence.reason}</span> : null}
                  </li>
                ))}
                {hypothesis.evidence.length === 0 ? (
                  <li className="empty-state">No evidence relationships recorded.</li>
                ) : null}
              </ul>
            </div>
          ))
        )}
      </section>

      {/* 5. LKG references: frozen baselines, never current truth */}
      <section aria-label="Last known good references">
        <h2>Last known good</h2>
        {detail.last_known_good_references.length === 0 ? (
          <EmptyState message="No frozen baseline selected for this incident." />
        ) : (
          detail.last_known_good_references.map((ref) => (
            <LastKnownGoodCard key={ref.reference_id} reference={ref} />
          ))
        )}
      </section>

      {/* 6. Capability-gated monetization */}
      <section aria-label="Monetization">
        <h2>Monetization</h2>
        <MonetizationCapabilityView capability={detail.monetization.capability} />
        <ul className="metric-list">
          {detail.monetization.metrics.map((metric) => (
            <li key={`${metric.metric_code}-${metric.unit}`}>
              <strong>{metric.metric_code}</strong> ({metric.unit}, {metric.source})
              <ul>
                {metric.points.map((point) => (
                  <li key={point.period_start}>
                    {new Date(point.period_start).toLocaleDateString()}:{" "}
                    {metric.unit === "CURRENCY"
                      ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(point.value)
                      : point.value}
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {detail.monetization.metrics.length === 0 ? (
            <li className="empty-state">No monetization evidence available.</li>
          ) : null}
        </ul>
      </section>
    </article>
  );
}

/** Frozen persisted evidence-pack snapshot view. */
export function EvidencePackView({ packId }: { packId: string }) {
  interface PackResponse {
    pack: {
      pack_id: string;
      incident_id: string | null;
      window_start: string;
      window_end: string;
      engine_version: string;
      created_at: string;
    };
    content: {
      machine_observed_sections: string[] | null;
      events: { event_id: string; summary: string; detected_at: string | null }[];
      human_reported_notes: { note_id: string; text: string; occurred_at: string | null }[];
      human_reported_notes_count: number | null;
    };
  }
  const [pack, setPack] = useState<PackResponse | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PackResponse>(`/evidence/packs/${packId}`)
      .then((data) => {
        if (!cancelled) setPack(data);
      })
      .catch(() => {
        if (!cancelled) setMissing(true);
      });
    return () => {
      cancelled = true;
    };
  }, [packId]);

  if (missing) return <ErrorState message="This evidence pack was not found." />;
  if (pack === null) return <LoadingState label="Loading evidence pack…" />;

  return (
    <article>
      <h1>Evidence pack</h1>
      {/* Persisted/frozen framing is contractual. */}
      <p className="temporal">
        Snapshot for window {new Date(pack.pack.window_start).toLocaleString()} –{" "}
        {new Date(pack.pack.window_end).toLocaleString()} · engine {pack.pack.engine_version}
      </p>
      <section aria-label="Machine observed">
        <h2>Machine observed</h2>
        <ul>
          {pack.content.events.map((event) => (
            <li key={event.event_id}>
              {event.summary}
              {event.detected_at ? ` (detected ${new Date(event.detected_at).toLocaleString()})` : ""}
            </li>
          ))}
        </ul>
      </section>
      <section aria-label="Human reported">
        <h2>Human reported</h2>
        <ul>
          {pack.content.human_reported_notes.map((note) => (
            <li key={note.note_id}>{note.text}</li>
          ))}
          {pack.content.human_reported_notes.length === 0 ? (
            <li className="empty-state">No human-reported notes in this snapshot.</li>
          ) : null}
        </ul>
      </section>
    </article>
  );
}
