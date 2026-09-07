"use client";

/** EP-030 M3 — minimal Home monitoring controls.
 *
 * Renders the canonical per-site monitoring authorization states on the Home
 * surface and, for ADMIN operators only, an Enable/Pause confirmation via the
 * repository's native <dialog> pattern. Monitoring authorization is a separate
 * fact from Browser Monitoring source health, diagnostic status, and site
 * lifecycle; this card never conflates them.
 *
 * Every displayed state is derived from the server-provided projection; the
 * frontend never infers a persisted state and never fabricates a boundary.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Button, ErrorState } from "@/components/primitives";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-client";
import type { MonitoringProjection, UpdateMonitoringResponse } from "@/lib/api-types";

const CADENCE_HOURS = 6;

type MonitoringMode = "enable" | "pause";

interface MonitoringCardProps {
  monitoring: MonitoringProjection | null;
  siteId: string | null;
  /** Re-fetch the selected site's home status after a successful mutation.
   * Receives the site the request was issued for, so the parent can refuse a
   * stale completion once the selection/generation has moved on. */
  onRefetch: (requestSiteId: string) => void | Promise<void>;
}

function formatBoundary(iso: string | null): string | null {
  if (!iso) return null;
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return null;
  return value.toLocaleString();
}

export function MonitoringCard({
  monitoring,
  siteId,
  onRefetch,
}: MonitoringCardProps) {
  // The dialog captures the site under which it was opened so a site change
  // (which re-renders this card for the new selection) can never let the
  // confirmation act on a stale site or display a stale projection.
  const [dialog, setDialog] = useState<{ siteId: string; mode: MonitoringMode } | null>(null);

  // Canonical auth: ADMIN is derived strictly from the authenticated session
  // role. Loading/unauthenticated/missing-provider states never expose mutation.
  const auth = useAuth();
  const isAdmin = auth.status === "authenticated" && auth.session?.role === "ADMIN";

  const enabled = monitoring == null ? null : monitoring.enabled;
  const inFlight =
    monitoring == null ? null : monitoring.in_flight_scheduled_run_status;
  const nextCheck = monitoring == null ? null : formatBoundary(monitoring?.next_scheduled_for ?? null);

  let title: string;
  let supporting: ReactNode;
  let actionMode: MonitoringMode | null = null;

  if (monitoring == null || enabled === null) {
    // Fail closed: never claim Monitoring active when the read is unavailable.
    title = "Monitoring state unavailable";
    supporting = "Automatic monitoring is treated as paused.";
  } else if (enabled) {
    title = "Monitoring active";
    supporting = (
      <>
        Every {CADENCE_HOURS} hours.
        {nextCheck ? ` Next scheduled check: ${nextCheck}.` : ""}
      </>
    );
    actionMode = "pause";
  } else if (inFlight === "PENDING" || inFlight === "RUNNING") {
    title = "Paused — current check finishing";
    supporting =
      "Pausing prevents new automatic checks, but a check already in progress may finish.";
    actionMode = "enable";
  } else {
    title = "Paused";
    supporting = "No automatic checks will start.";
    actionMode = "enable";
  }

  const showAction = isAdmin && siteId !== null && actionMode !== null;

  // Derived open state: the dialog only stays open while the site it was
  // captured for is still the selected site. On a selected-site change the
  // dialog closes automatically (no effect-driven setState needed).
  const dialogOpen = dialog !== null && dialog.siteId === siteId;

  return (
    <section className="card monitoring-card" aria-label="Automatic monitoring">
      <h2>Automatic monitoring</h2>
      <p className="monitoring-title">{title}</p>
      <p className="monitoring-support">{supporting}</p>
      {showAction && actionMode !== null ? (
        <MonitoringAction
          mode={actionMode}
          onClick={() => {
            if (siteId !== null) setDialog({ siteId, mode: actionMode });
          }}
        />
      ) : null}
      {dialog !== null ? (
        <MonitoringDialog
          open={dialogOpen}
          mode={dialog.mode}
          siteId={dialog.siteId}
          onClose={() => setDialog(null)}
          onConfirm={(requestSiteId) => {
            setDialog(null);
            void onRefetch(requestSiteId);
          }}
        />
      ) : null}
    </section>
  );
}

function MonitoringAction({ mode, onClick }: { mode: MonitoringMode; onClick: () => void }) {
  return (
    <div className="monitoring-action">
      <Button variant="secondary" onClick={onClick}>
        {mode === "enable" ? "Enable monitoring" : "Pause monitoring"}
      </Button>
    </div>
  );
}

interface MonitoringDialogProps {
  open: boolean;
  mode: MonitoringMode;
  siteId: string | null;
  onClose: () => void;
  onConfirm: (requestSiteId: string) => void;
}

function MonitoringDialog({ open, mode, siteId, onClose, onConfirm }: MonitoringDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inflightRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      dialog.showModal();
    } else {
      dialog.close();
    }
  }, [open]);

  function reset() {
    setFailure(null);
    setSubmitting(false);
    inflightRef.current = false;
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function handleConfirm() {
    if (inflightRef.current) return;
    if (siteId === null) return;
    inflightRef.current = true;
    setSubmitting(true);
    setFailure(null);
    let result: UpdateMonitoringResponse | null = null;
    try {
      result = await apiFetch<UpdateMonitoringResponse>(
        `/product/sites/${encodeURIComponent(siteId)}/monitoring`,
        { method: "PUT", body: { enabled: mode === "enable" } },
      );
    } catch (error) {
      setFailure(mapMonitoringError(error));
      setSubmitting(false);
      inflightRef.current = false;
      return;
    }
    if (result !== null) {
      dialogRef.current?.close();
      reset();
      onConfirm(siteId);
    }
  }

  const isEnable = mode === "enable";

  return (
    <dialog
      ref={dialogRef}
      id="monitoring-dialog"
      onClose={handleClose}
      className="monitoring-dialog"
      aria-labelledby="monitoring-dialog-title"
      aria-describedby="monitoring-dialog-description"
    >
      <h2 id="monitoring-dialog-title">
        {isEnable ? "Enable monitoring" : "Pause monitoring"}
      </h2>
      <p id="monitoring-dialog-description">
        {isEnable ? (
          <>
            Automatic monitoring will run every {CADENCE_HOURS} hours. Enabling does
            not run a check immediately; the first eligible check starts at the next
            future scheduled boundary, and no backfill occurs.
          </>
        ) : (
          <>
            No new automatic checks will start. A check that already passed
            pre-flight may finish. Existing history and evidence are retained; this
            does not delete data.
          </>
        )}
      </p>
      {failure ? <ErrorState message={failure} /> : null}
      <div className="dialog-actions">
        <Button type="button" variant="secondary" onClick={handleClose} disabled={submitting}>
          Cancel
        </Button>
        <Button type="button" variant="secondary" onClick={() => void handleConfirm()} disabled={submitting}>
          {submitting
            ? "Processing…"
            : isEnable
              ? "Enable monitoring"
              : "Pause monitoring"}
        </Button>
      </div>
    </dialog>
  );
}

function mapMonitoringError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Reload and try again.";
    if (error.status === 403)
      return "You do not have permission to change monitoring for this site.";
    if (error.status === 404) return "That site was not found.";
  }
  return "Could not update monitoring. Try again.";
}
