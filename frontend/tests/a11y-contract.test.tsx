import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, ErrorState, LoadingState } from "../components/primitives";
import { EvidenceRelationView, SourceHealthBadge } from "../components/domain";

/** EP-025b M6 — accessibility & semantic-contract sweep. */

describe("accessibility sweep", () => {
  it("conveys source health through text, never color alone", () => {
    render(<SourceHealthBadge source="GAM" health="DEGRADED" />);
    expect(screen.getByText(/Ad Manager · DEGRADED/)).toBeInTheDocument();
  });

  it("uses live-region roles for loading and error states", () => {
    render(
      <>
        <LoadingState />
        <ErrorState message="Something failed." />
        <EmptyState message="Nothing here." />
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/Nothing here\./)).toBeInTheDocument();
  });

  it("keeps observation-gap semantics distinct from contradiction", () => {
    render(<EvidenceRelationView relation="CONTEXT" sourceKind="OBSERVATION_GAP" />);
    expect(screen.getByText(/not observed \/ unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Contradicts$/)).not.toBeInTheDocument();
  });
});
