import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Dashboard } from "../pages/Dashboard";

describe("Dashboard", () => {
  it("renders the WaitWatch heading", () => {
    render(<Dashboard />);
    expect(screen.getByText("WaitWatch")).toBeDefined();
  });

  it("displays the purpose tagline", () => {
    render(<Dashboard />);
    expect(screen.getByText("Real-Time Transit Tracking")).toBeDefined();
  });

  it("shows initialization status", () => {
    render(<Dashboard />);
    expect(
      screen.getByText("Setting up the foundation"),
    ).toBeDefined();
  });

  it("lists planned features", () => {
    render(<Dashboard />);
    expect(screen.getByText("Route & stop explorer")).toBeDefined();
    expect(screen.getByText("Live vehicle tracking")).toBeDefined();
    expect(screen.getByText("ETA predictions")).toBeDefined();
  });
});
