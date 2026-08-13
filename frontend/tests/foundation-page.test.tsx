import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FoundationPage from "../app/page";

describe("FoundationPage", () => {
  it("states the current implementation boundary", () => {
    render(<FoundationPage />);

    expect(
      screen.getByRole("heading", { name: "Repository foundation is running." }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Browser evidence collection starts in EP-002/)).toBeInTheDocument();
  });
});
