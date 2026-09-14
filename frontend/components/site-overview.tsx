"use client";

/**
 * EP-031 M4 — Site Overview operational result panels.
 *
 * Read-only result presentation for a single site:
 *   M3: latest diagnostic, latest scheduled, recent runs
 *   M4: source status, browser monitoring detail, open incidents, recent activity
 *
 * Reuses existing domain badges/primitives. Absence is always neutral; SKIPPED
 * is never failure-toned; source unavailability is never rendered as publisher
 * failure. No M5+ content (configuration, cadence, connector setup) is present.
 */

import { useRouter } from "next/navigation";
import Link from "next/link";

import { Button, Card, EmptyState } from "@/components/primitives";
import {
  BrowserAccessClassificationBadge,
  DiagnosticStateBadge,
  SeverityBadge,
  SourceHealthBadge,
  StatusChip,
} from "@/components/domain";
import { TimelineEntryView } from "@/components/timeline-entries";
import type { SiteOverviewResponse } from "@/lib/api-types";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

const RUN_KIND_LABELS: Record<string, string> = {
  SCHEDULED: "Scheduled",
  DIAGNOSTIC: "Diagnostic",
  INCIDENT_DIAGNOSTIC: "Incident diagnostic",
};

const NON_TERMINAL_DIAGNOSTIC_STATUS = new Set(["PENDING", "RUNNING"]);

/* -------------------------------------------------------------------------- */
/*  M3 panels                                                                 */
/* -------------------------------------------------------------------------- */

export function LatestDiagnosticPanel({ overview }: { overview: SiteOverviewResponse }) {
  const router = useRouter();
  const diagnostic = overview.initial_diagnostic;
  const terminal =
    diagnostic !== null && !NON_TERMINAL_DIAGNOSTIC_STATUS.has(diagnostic.status);

  return (
    <Card title="Latest diagnostic">
      {diagnostic === null ? (
        <EmptyState message="No diagnostic yet" />
      ) : (
        <div className="overview-panel-body">
          <p className="overview-panel-line">
            <DiagnosticStateBadge diagnostic={diagnostic} />
          </p>
          {diagnostic.browser_access_classification !== null && (
            <p className="overview-panel-line">
              <BrowserAccessClassificationBadge
                classification={diagnostic.browser_access_classification}
              />
            </p>
          )}
          <p className="overview-panel-line">
            <span className="overview-panel-label">Completed</span>{" "}
            <span data-testid="latest-diagnostic-completed">
              {formatDate(diagnostic.completed_at)}
            </span>
          </p>
          {terminal && (
            <p className="overview-panel-action">
              <Button
                variant="secondary"
                onClick={() =>
                  router.push(
                    `/diagnostic-results?site_id=${encodeURIComponent(overview.site.site_id)}`,
                  )
                }
              >
                View diagnostic results →
              </Button>
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

export function LatestScheduledRunPanel({ overview }: { overview: SiteOverviewResponse }) {
  const run = overview.latest_scheduled_run;

  return (
    <Card title="Latest scheduled">
      {run === null ? (
        <EmptyState message="No scheduled results yet" />
      ) : (
        <div className="overview-panel-body">
          <p className="overview-panel-line">
            <StatusChip status={run.status} />
          </p>
          {run.browser_access_classification !== null && (
            <p className="overview-panel-line">
              <BrowserAccessClassificationBadge
                classification={run.browser_access_classification}
              />
            </p>
          )}
          <p className="overview-panel-line">
            <span className="overview-panel-label">Completed</span>{" "}
            <span data-testid="latest-scheduled-completed">
              {formatDate(run.completed_at)}
            </span>
          </p>
          <p className="overview-panel-line">
            <span className="overview-panel-label">Attempts</span> {run.attempt_count}
          </p>
        </div>
      )}
    </Card>
  );
}

function RunStatus({ run }: { run: SiteOverviewResponse["recent_runs"][number] }) {
  if (run.status === "SKIPPED") {
    return <span className="overview-run-skipped">Skipped — monitoring paused</span>;
  }
  return <StatusChip status={run.status} />;
}

export function RecentRunsPanel({ runs }: { runs: SiteOverviewResponse["recent_runs"] }) {
  return (
    <Card title="Recent runs">
      {runs.length === 0 ? (
        <EmptyState message="No runs yet" />
      ) : (
        <ul className="overview-run-list">
          {runs.map((run) => (
            <li key={run.run_id} className="overview-run-item">
              <span className="overview-run-header">
                <span className="overview-run-kind">
                  {RUN_KIND_LABELS[run.observation_kind] ?? run.observation_kind}
                </span>
                <RunStatus run={run} />
              </span>
              <span className="overview-run-time">
                {formatDate(run.completed_at ?? run.started_at)}
              </span>
              {run.limitations.length > 0 && (
                <span className="overview-run-limitation">{run.limitations.join(" · ")}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  M4 panels                                                                 */
/* -------------------------------------------------------------------------- */

/** Five source-health categories rendered independently — never aggregated
 * into a single site-health conclusion. SOURCE/OBSERVATION FAILURE is never
 * conflated with PUBLISHER FAILURE. */
export function SourceHealthPanel({
  sources,
}: { sources: SiteOverviewResponse["source_health"] }) {
  const sourceKeys = Object.keys(sources) as Array<keyof typeof sources>;
  return (
    <Card title="Source status">
      <div className="overview-source-health-grid">
        {sourceKeys.map((key) => (
          <SourceHealthBadge key={key} source={key} health={sources[key]} />
        ))}
      </div>
    </Card>
  );
}

/** Browser observation-source detail. This describes our ability to observe
 * the publisher's site via Chromium, not the publisher's own health. The
 * backend-provided boundary label is surfaced verbatim when present. */
export function BrowserConditionPanel({
  detail,
}: { detail: SiteOverviewResponse["browser_monitoring_detail"] }) {
  if (detail === null) {
    return (
      <Card title="Browser monitoring detail">
        <EmptyState message="Condition not available" />
      </Card>
    );
  }
  return (
    <Card title="Browser monitoring detail">
      <div className="overview-panel-body">
        {detail.state != null && (
          <p className="overview-panel-line">
            <StatusChip status={String(detail.state)} />
          </p>
        )}
        {detail.reason != null && (
          <p className="overview-panel-line overview-panel-label">
            {String(detail.reason)}
          </p>
        )}
        {detail.detected_at != null && (
          <p className="overview-panel-line">
            <span className="overview-panel-label">Detected</span>{" "}
            <span>{formatDate(String(detail.detected_at))}</span>
          </p>
        )}
        {detail.boundary != null && (
          <p className="overview-panel-limitation">{String(detail.boundary)}</p>
        )}
      </div>
    </Card>
  );
}

/** Open incidents rendered as compact cards linking to the existing
 * /incidents/[id] detail route. No incident mutation controls are included;
 * an empty list never implies the site is healthy. */
export function OpenIncidentsPanel({
  incidents,
}: { incidents: SiteOverviewResponse["open_incidents"] }) {
  return (
    <Card title="Open incidents">
      {incidents.length === 0 ? (
        <EmptyState message="No open incidents for this site" />
      ) : (
        <ul className="incident-list">
          {incidents.map((inc) => (
            <li key={inc.incident_id}>
              <Link
                href={`/incidents/${inc.incident_id}`}
                className="card incident-card"
              >
                <strong>{inc.title}</strong>
                <span>{inc.symptom_family}</span>
                <StatusChip status={inc.status} />
                <SeverityBadge severity={inc.severity} />
                <span className="overview-incident-opened">
                  {formatDate(inc.opened_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** Bounded recent-activity list using the shared canonical TimelineEntryView.
 * Timeline semantics (provenance, temporal uncertainty, event_kind) are
 * preserved exactly — no second timeline implementation is introduced.
 * A deep link to the site-filtered /timeline page is always provided. */
export function RecentActivityPanel({
  activity,
  siteName,
  siteId,
}: {
  activity: SiteOverviewResponse["recent_activity"];
  siteName: string;
  siteId: string;
}) {
  const router = useRouter();
  return (
    <Card title="Recent activity">
      {activity.length === 0 ? (
        <EmptyState message="No activity yet" />
      ) : (
        <ol className="timeline-list">
          {activity.map((entry) => (
            <TimelineEntryView
              key={"event_id" in entry ? entry.event_id : entry.note_id}
              entry={entry}
              siteName={siteName}
            />
          ))}
        </ol>
      )}
      <p className="overview-panel-action">
        <Button
          variant="secondary"
          onClick={() =>
            router.push(`/timeline?site_id=${encodeURIComponent(siteId)}`)
          }
        >
          View full timeline →
        </Button>
      </p>
    </Card>
  );
}

/* -------------------------------------------------------------------------- */
/*  Composition                                                               */
/* -------------------------------------------------------------------------- */

export function SiteOverviewPanels({ overview }: { overview: SiteOverviewResponse }) {
  return (
    <div className="overview-panels">
      {/* M3 — operational run results */}
      <LatestDiagnosticPanel overview={overview} />
      <LatestScheduledRunPanel overview={overview} />
      <RecentRunsPanel runs={overview.recent_runs} />
      {/* M4 — source status, browser detail, incidents, activity */}
      <SourceHealthPanel sources={overview.source_health} />
      <BrowserConditionPanel detail={overview.browser_monitoring_detail} />
      <OpenIncidentsPanel incidents={overview.open_incidents} />
      <RecentActivityPanel
        activity={overview.recent_activity}
        siteName={overview.site.name}
        siteId={overview.site.site_id}
      />
    </div>
  );
}