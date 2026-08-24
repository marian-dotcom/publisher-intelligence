"use client";

/** EP-025b M5 — minimal Investigate intake: the ONLY approved write interaction.
 * Fields mirror InvestigateRequest exactly; CSRF rides the typed wrapper. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Button, ErrorState, Field, Input } from "@/components/primitives";
import { apiFetch } from "@/lib/api";
import type { HomeStatus, InvestigateSuccess } from "@/lib/api-types";

const SYMPTOM_FAMILIES = [
  "OTHER",
  "GAM_ADSERVING",
  "SEARCH_DISCOVER",
  "CONSENT_CMP",
  "PREBID_HEADER_BIDDING",
  "VIDEO",
  "BROWSER_PERFORMANCE",
  "ANALYTICS_MEASUREMENT",
  "EXTERNAL_INFRASTRUCTURE",
  "REPORTING_DISCREPANCY",
  "POLICY_COMPLIANCE",
  "PROGRAMMATIC_MARKET",
] as const;

export function InvestigateDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [sites, setSites] = useState<{ site_id: string; name: string }[] | null>(null);
  const [siteId, setSiteId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [symptomFamily, setSymptomFamily] = useState("OTHER");
  const [reportedStart, setReportedStart] = useState("");
  const [reportedEnd, setReportedEnd] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // Site options come from the same home/status contract the shell already uses.
  useEffect(() => {
    if (!open || sites !== null) return;
    apiFetch<HomeStatus>("/product/home/status")
      .then((status) => {
        setSites(status.sites);
        if (status.selected_site_id) setSiteId(status.selected_site_id);
      })
      .catch(() => setFailure("Could not load your sites."));
  }, [open, sites]);

  useEffect(() => {
    if (open) {
      // Native dialog lifecycle.
      const dialog = document.getElementById("investigate-dialog") as HTMLDialogElement | null;
      dialog?.showModal();
    }
  }, [open]);

  function close() {
    const dialog = document.getElementById("investigate-dialog") as HTMLDialogElement | null;
    dialog?.close();
    onClose();
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return; // double-submit guard
    setSubmitting(true);
    setFailure(null);
    try {
      const result = await apiFetch<InvestigateSuccess>("/investigations", {
        method: "POST",
        body: {
          site_id: siteId,
          title,
          symptom_family: symptomFamily,
          description,
          ...(reportedStart ? { reported_start_at: new Date(reportedStart).toISOString() } : {}),
          ...(reportedEnd ? { reported_end_at: new Date(reportedEnd).toISOString() } : {}),
        },
      });
      close();
      router.push(`/incidents/${result.incident_id}`);
    } catch (error) {
      if (error && typeof error === "object" && "kind" in error) {
        const kind = (error as { kind: string }).kind;
        setFailure(
          kind === "not_found"
            ? "That site was not found."
            : kind === "forbidden"
              ? "Your session could not be verified. Reload and try again."
              : "Could not open the investigation. Try again.",
        );
      } else {
        setFailure("Could not open the investigation. Try again.");
      }
      setSubmitting(false);
    }
  }

  return (
    <dialog id="investigate-dialog" onClose={onClose} className="investigate-dialog">
      <form method="dialog" onSubmit={handleSubmit}>
        <h2>Investigate</h2>
        <Field label="Site" htmlFor="inv-site">
          {sites === null ? (
            <Input id="inv-site" disabled placeholder="Loading sites…" />
          ) : (
            <select
              id="inv-site"
              className="input"
              value={siteId}
              onChange={(event) => setSiteId(event.target.value)}
            >
              {(sites ?? []).map((site) => (
                <option key={site.site_id} value={site.site_id}>
                  {site.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="What happened?" htmlFor="inv-title">
          <Input
            id="inv-title"
            required
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Short summary of the symptom"
          />
        </Field>
        <Field label="Description" htmlFor="inv-description">
          <Input
            id="inv-description"
            required
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </Field>
        <Field label="Symptom family" htmlFor="inv-family">
          <select
            id="inv-family"
            className="input"
            value={symptomFamily}
            onChange={(event) => setSymptomFamily(event.target.value)}
          >
            {SYMPTOM_FAMILIES.map((family) => (
              <option key={family} value={family}>
                {family}
              </option>
            ))}
          </select>
        </Field>
        <Field label="When did it start? (optional)" htmlFor="inv-start">
          <Input
            id="inv-start"
            type="datetime-local"
            value={reportedStart}
            onChange={(event) => setReportedStart(event.target.value)}
          />
        </Field>
        <Field label="When did it end? (optional)" htmlFor="inv-end">
          <Input
            id="inv-end"
            type="datetime-local"
            value={reportedEnd}
            onChange={(event) => setReportedEnd(event.target.value)}
          />
        </Field>
        {failure ? <ErrorState message={failure} /> : null}
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={close}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting || !siteId || !title || !description}>
            {submitting ? "Opening…" : "Open investigation"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
