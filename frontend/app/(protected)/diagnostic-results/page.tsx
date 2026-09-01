"use client";

/** EP-029 M2a — diagnostic results page for initial DIAGNOSTIC/OPERATOR_UI runs.
 * Navigation contract (Home): `/diagnostic-results?site_id=<encoded-id>`.
 * This is a static route with no dynamic segment, so the site id is read from
 * the search params — never from useParams().
 */

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Card, EmptyState, ErrorState, LoadingState } from "@/components/primitives";
import {
  BrowserAccessClassification,
  DiagnosticResults,
  DiagnosticArtifactType,
} from "@/lib/api-types";
import { apiFetch, ApiError } from "@/lib/api";
import { DiagnosticStateBadge } from "@/components/domain";

const SCREENSHOT_TYPES: DiagnosticArtifactType[] = [
  "SCREENSHOT_VIEWPORT",
  "SCREENSHOT_VIEWPORT_PRECONSENT",
  "SCREENSHOT_VIEWPORT_POSTCONSENT",
  "SCREENSHOT_FULL_PAGE",
];

const DOWNLOAD_TYPES: DiagnosticArtifactType[] = ["NORMALIZED_DOM", "RAW_DOM", "MANIFEST"];

const ARTIFACT_LABELS: Record<DiagnosticArtifactType, string> = {
  SCREENSHOT_VIEWPORT: "Viewport screenshot",
  SCREENSHOT_VIEWPORT_PRECONSENT: "Viewport screenshot (pre-consent)",
  SCREENSHOT_VIEWPORT_POSTCONSENT: "Viewport screenshot (post-consent)",
  SCREENSHOT_FULL_PAGE: "Full-page screenshot",
  RAW_DOM: "Raw DOM",
  NORMALIZED_DOM: "Normalized DOM",
  MANIFEST: "Manifest",
};

const ARTIFACT_DESCRIPTIONS: Record<DiagnosticArtifactType, string> = {
  SCREENSHOT_VIEWPORT: "Rendered page viewport at checkpoint completion",
  SCREENSHOT_VIEWPORT_PRECONSENT: "Viewport before consent interaction",
  SCREENSHOT_VIEWPORT_POSTCONSENT: "Viewport after consent interaction",
  SCREENSHOT_FULL_PAGE: "Full-page scroll capture",
  RAW_DOM: "Complete HTML document as collected (download only)",
  NORMALIZED_DOM: "Normalized structural DOM for comparison (download only)",
  MANIFEST: "Collector manifest with provenance and summaries",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function ClassificationBadge({ classification }: { classification: BrowserAccessClassification | null }) {
  if (!classification) return <span className="badge badge-unknown">Access: unknown</span>;
  const labels: Record<BrowserAccessClassification, string> = {
    ok: "Access: normal",
    degraded: "Access: degraded",
    challenge_suspected: "Access: challenge suspected",
  };
  return <span className={`badge badge-${classification}`}>{labels[classification]}</span>;
}

function DiagnosticResultsContent() {
  const searchParams = useSearchParams();
  const siteId = (searchParams.get("site_id") ?? "").trim();

  const [results, setResults] = useState<DiagnosticResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // No API request until a valid non-empty site id exists.
    if (siteId.length === 0) {
      return;
    }
    let cancelled = false;
    (async () => {
      setError(null);
      setLoading(true);
      try {
        const data = await apiFetch<DiagnosticResults>(
          `/product/sites/${encodeURIComponent(siteId)}/diagnostic-results`,
        );
        if (!cancelled) setResults(data);
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiError) {
            if (e.status === 404) {
              setError("No diagnostic results available for this site.");
            } else if (e.kind === "unauthorized") {
              setError("Authentication required.");
            } else if (e.kind === "forbidden") {
              setError("Access denied.");
            } else {
              setError("Could not load diagnostic results. Try again.");
            }
          } else {
            setError("Could not load diagnostic results. Try again.");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [siteId]);

  async function downloadArtifact(artifact: { artifact_id: string; artifact_type: string }) {
    try {
      const response = await fetch(
        `/product/sites/${encodeURIComponent(siteId)}/diagnostic-artifacts/${encodeURIComponent(artifact.artifact_id)}`,
        { credentials: "same-origin" },
      );
      if (!response.ok) throw new Error("Download failed");
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = artifact.artifact_id;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch {
      alert("Failed to download artifact");
    }
  }

  if (siteId.length === 0) {
    return (
      <>
        <h1>Diagnostic Results</h1>
        <EmptyState message="Select a site to view diagnostic results." />
      </>
    );
  }
  if (loading) return <LoadingState label="Loading diagnostic results…" />;
  if (error) return <ErrorState message={error} />;
  if (!results) return <EmptyState message="No diagnostic results found." />;

  const { run, artifacts, site_name, site_domain, publisher_name } = results;
  const screenshots = artifacts.filter((a) => SCREENSHOT_TYPES.includes(a.artifact_type as DiagnosticArtifactType));
  const downloads = artifacts.filter((a) => DOWNLOAD_TYPES.includes(a.artifact_type as DiagnosticArtifactType));

  return (
    <>
      <h1>Diagnostic Results</h1>
      <p className="site-context">
        <strong>{site_name}</strong> · {site_domain}
        {publisher_name && <span> · {publisher_name}</span>}
      </p>

      <Card title="Run Summary">
        <dl className="run-summary">
          <dt>Status</dt>
          <dd><DiagnosticStateBadge diagnostic={{ status: run.status, browser_access_classification: run.browser_access_classification }} /></dd>

          <dt>Observation Kind</dt>
          <dd>{run.observation_kind}</dd>

          <dt>Trigger Source</dt>
          <dd>{run.trigger_source}</dd>

          <dt>Trigger Correlation ID</dt>
          <dd>{run.trigger_correlation_id ?? "—"}</dd>

          <dt>Attempt Count</dt>
          <dd>{run.attempt_count}</dd>

          <dt>Final URL</dt>
          <dd>{run.final_url ?? "—"}</dd>

          <dt>HTTP Status</dt>
          <dd>{run.http_status ?? "—"}</dd>

          <dt>Completed At</dt>
          <dd>{formatDate(run.completed_at)}</dd>

          <dt>Started At</dt>
          <dd>{formatDate(run.started_at)}</dd>

          <dt>Browser Access Classification</dt>
          <dd><ClassificationBadge classification={run.browser_access_classification} /></dd>

          <dt>Scenario ID</dt>
          <dd>{run.scenario_id}</dd>

          <dt>Collector Bundle Version</dt>
          <dd>{run.collector_bundle_version}</dd>

          {run.limitations.length > 0 && (
            <>
              <dt>Limitations</dt>
              <dd>
                <ul>
                  {run.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </dd>
            </>
          )}
        </dl>
      </Card>

      <Card title="Artifacts">
        {artifacts.length === 0 ? (
          <EmptyState message="No artifacts available for this diagnostic run." />
        ) : (
          <>
            {screenshots.length > 0 && (
              <section aria-label="Screenshots">
                <h3>Screenshots</h3>
                <div className="artifact-grid screenshots">
                  {screenshots.map((artifact) => (
                    <figure key={artifact.artifact_id} className="artifact-card">
                      <figcaption>
                        <strong>{ARTIFACT_LABELS[artifact.artifact_type]}</strong>
                        <span className="artifact-meta">
                          {formatBytes(artifact.byte_size)} · {artifact.content_type}
                        </span>
                        <p className="artifact-desc">{ARTIFACT_DESCRIPTIONS[artifact.artifact_type]}</p>
                      </figcaption>
                      {/* eslint-disable-next-line @next/next/no-img-element -- Authenticated same-origin private/no-store API endpoint; Next.js image optimization must not server-fetch/cache it without the operator's browser session. */}
                      <img
                        src={`/product/sites/${encodeURIComponent(siteId)}/diagnostic-artifacts/${artifact.artifact_id}`}
                        alt={ARTIFACT_LABELS[artifact.artifact_type]}
                        loading="lazy"
                      />
                    </figure>
                  ))}
                </div>
              </section>
            )}

            {downloads.length > 0 && (
              <section aria-label="Downloadable artifacts">
                <h3>Artifacts (download)</h3>
                <ul className="artifact-list">
                  {downloads.map((artifact) => (
                    <li key={artifact.artifact_id} className="artifact-item">
                      <div className="artifact-info">
                        <strong>{ARTIFACT_LABELS[artifact.artifact_type]}</strong>
                        <span className="artifact-meta">
                          {formatBytes(artifact.byte_size)} · {artifact.content_type}
                        </span>
                        <p className="artifact-desc">{ARTIFACT_DESCRIPTIONS[artifact.artifact_type]}</p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => downloadArtifact(artifact)}
                      >
                        Download
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </Card>
    </>
  );
}

/** Suspense allows the static route to consume useSearchParams() safely
 * (Next.js static-rendering requirement for search-param consumers). */
export default function DiagnosticResultsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading diagnostic results…" />}>
      <DiagnosticResultsContent />
    </Suspense>
  );
}