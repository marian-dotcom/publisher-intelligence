"use client";

/** EP-028 M3 — Add Site dialog: compact form for internal operator site registration. */

import { useEffect, useRef, useState } from "react";

import { Button, ErrorState, Field, Input } from "@/components/primitives";
import { apiFetch, ApiError } from "@/lib/api";
import type { RegisterSiteSuccess } from "@/lib/api-types";

interface AddSiteDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (siteId: string) => void;
}

export function AddSiteDialog({ open, onClose, onSuccess }: AddSiteDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inflightRef = useRef(false);

  const [publisherName, setPublisherName] = useState("");
  const [siteName, setSiteName] = useState("");
  const [url, setUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  // Native dialog lifecycle.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open) {
      dialog.showModal();
    } else {
      dialog.close();
    }
  }, [open]);

  function resetForm() {
    setPublisherName("");
    setSiteName("");
    setUrl("");
    setFailure(null);
    setSubmitting(false);
    inflightRef.current = false;
  }

  function handleClose() {
    resetForm();
    onClose();
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Prevent duplicate in-flight submission at the handler level.
    if (inflightRef.current) return;
    inflightRef.current = true;
    setSubmitting(true);
    setFailure(null);

    const trimmedPublisher = publisherName.trim();
    const trimmedSite = siteName.trim();
    const trimmedUrl = url.trim();

    if (!trimmedPublisher || !trimmedSite || !trimmedUrl) {
      setSubmitting(false);
      inflightRef.current = false;
      return;
    }

    try {
      const result = await apiFetch<RegisterSiteSuccess>("/product/sites", {
        method: "POST",
        body: {
          publisher_name: trimmedPublisher,
          site_name: trimmedSite,
          url: trimmedUrl,
        },
      });
      resetForm();
      // Close the native dialog.
      dialogRef.current?.close();
      onSuccess(result.site_id);
    } catch (error) {
      const message = mapRegistrationError(error);
      setFailure(message);
      setSubmitting(false);
      inflightRef.current = false;
    }
  }

  function mapRegistrationError(error: unknown): string {
    if (error instanceof ApiError) {
      if (error.status === 409) return "This website is already registered.";
      if (error.status === 400) return "Enter a valid public website URL.";
      if (error.status === 401) return "Your session has expired. Reload and try again.";
      if (error.status === 403)
        return "You do not have permission to add this site, or your session could not be verified.";
    }
    return "Could not register the site. Try again.";
  }

  const trimmedPublisher = publisherName.trim();
  const trimmedSite = siteName.trim();
  const trimmedUrl = url.trim();
  const canSubmit = !submitting && !!trimmedPublisher && !!trimmedSite && !!trimmedUrl;

  return (
    <dialog
      ref={dialogRef}
      id="add-site-dialog"
      onClose={handleClose}
      className="add-site-dialog"
      aria-labelledby="add-site-title"
    >
      <form method="dialog" onSubmit={handleSubmit}>
        <h2 id="add-site-title">Add site</h2>
        <Field label="Publisher name" htmlFor="add-site-publisher">
          <Input
            id="add-site-publisher"
            required
            maxLength={200}
            autoFocus
            value={publisherName}
            onChange={(event) => setPublisherName(event.target.value)}
            placeholder="Example Publisher"
          />
        </Field>
        <Field label="Site name" htmlFor="add-site-name">
          <Input
            id="add-site-name"
            required
            maxLength={200}
            value={siteName}
            onChange={(event) => setSiteName(event.target.value)}
            placeholder="Example News"
          />
        </Field>
        <Field label="Website URL" htmlFor="add-site-url">
          <Input
            id="add-site-url"
            required
            type="url"
            maxLength={2048}
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://news.example/"
          />
        </Field>
        {failure ? <ErrorState message={failure} /> : null}
        <div className="dialog-actions">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={!canSubmit}>
            {submitting ? "Adding…" : "Add site"}
          </Button>
        </div>
      </form>
    </dialog>
  );
}
