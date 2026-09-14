"use client";

/**
 * EP-031 M3 — Site Overview operational result panels.
 *
 * Read-only result presentation for a single site:
 *   - Latest diagnostic (overview.initial_diagnostic)
 *   - Latest scheduled (overview.latest_scheduled_run, backend-filtered to
 *     SCHEDULED with SKIPPED excluded)
 *   - Recent runs (overview.recent_runs, bounded list)
 *
 * Reuses existing domain badges/primitives. Absence is always neutral; SKIPPED
 * is never failure-toned. M4 content (source health, browser monitoring detail,
 * open incidents, recent activity, deep links) is NOT implemented here.
 */

import { useRouter } from "next/navigation";

import { Button, Card, EmptyState } from "@/components/primitives";
import { BrowserAccessClassificationBadge, DiagnosticStateBadge, StatusChip } from "@/components/domain";
import type { SiteOverviewRecentRun, SiteOverviewResponse } from "@/lib/api-types";

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

function RunStatus({ run }: { run: SiteOverviewRecentRun }) {
  if (run.status === "SKIPPED") {
    return <span className="overview-run-skipped">Skipped — monitoring paused</span>;
  }
  return <StatusChip status={run.status} />;
}

export function RecentRunsPanel({ runs }: { runs: SiteOverviewRecentRun[] }) {
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

export function SiteOverviewPanels({ overview }: { overview: SiteOverviewResponse }) {
  return (
    <div className="overview-panels">
      <LatestDiagnosticPanel overview={overview} />
      <LatestScheduledRunPanel overview={overview} />
      <RecentRunsPanel runs={overview.recent_runs} />
    </div>
  );
}