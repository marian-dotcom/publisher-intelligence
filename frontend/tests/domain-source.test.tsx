import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  MonetizationCapabilityView,
  SiteCondition,
  SourceHealthBadge,
} from "../components/domain";

describe("SourceHealthBadge", () => {
  it("renders DEGRADED with its own degraded tone", () => {
    render(<SourceHealthBadge source="BROWSER_MONITORING" health="DEGRADED" />);
    expect(screen.getByText(/Browser Monitoring · DEGRADED/)).toHaveClass("badge-degraded");
  });

  it("renders UNKNOWN as absence of evidence, never styled as failure", () => {
    render(<SourceHealthBadge source="GA4" health="UNKNOWN" />);
    const badge = screen.getByText(/GA4 · UNKNOWN/);
    expect(badge).toHaveClass("badge-unknown");
    expect(badge).not.toHaveClass("badge-failure");
    expect(badge).not.toHaveClass("badge-degraded");
    expect(screen.getByTitle("GA4: no evidence available")).toBeInTheDocument();
  });

  it("keeps source identity visible so sources are never conflated", () => {
    render(<SourceHealthBadge source="GAM" health="HEALTHY" />);
    expect(screen.getByText(/Ad Manager · HEALTHY/)).toBeInTheDocument();
  });
});

describe("SiteCondition", () => {
  it("is serialized independently of any source-health state", () => {
    // The component accepts only a condition; it cannot read source health.
    render(<SiteCondition condition="ACTIVE" />);
    expect(screen.getByText("Publisher/site: ACTIVE")).toBeInTheDocument();
  });

  it("does not transform a healthy site into a degraded/failure state", () => {
    render(<SiteCondition condition="ACTIVE" />);
    expect(screen.getByText(/ACTIVE/)).not.toHaveClass("badge-degraded");
    expect(screen.getByText(/ACTIVE/)).not.toHaveClass("badge-failure");
  });
});

describe("MonetizationCapabilityView", () => {
  it("labels RELATIVE_ONLY without implying absolute revenue", () => {
    render(<MonetizationCapabilityView capability="RELATIVE_ONLY" />);
    expect(screen.getByText(/relative metrics only/)).toBeInTheDocument();
    expect(screen.queryByText(/absolute values available/i)).not.toBeInTheDocument();
  });

  it("fails closed for UNKNOWN", () => {
    render(<MonetizationCapabilityView capability="UNKNOWN" />);
    expect(screen.getByText(/unknown/i)).toBeInTheDocument();
  });
});
