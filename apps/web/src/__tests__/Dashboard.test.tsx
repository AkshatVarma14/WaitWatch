import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Dashboard } from "../pages/Dashboard";

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

describe("Dashboard", () => {
  it("renders the WaitWatch heading", () => {
    renderWithClient(<Dashboard />);
    expect(screen.getByRole("heading", { name: "WaitWatch" })).toBeInTheDocument();
  });

  it("displays the purpose tagline", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByRole("heading", { name: "Real-Time Transit Tracking" }),
    ).toBeInTheDocument();
  });

  it("renders the feed and route selection section", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByRole("region", { name: /Feed and route selection/i }),
    ).toBeInTheDocument();
  });

  it("renders the route map visualization section", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByRole("region", { name: /Route map visualization/i }),
    ).toBeInTheDocument();
  });

  it("renders the feed and stop navigation section", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByRole("region", { name: /Feed and stop navigation/i }),
    ).toBeInTheDocument();
  });

  it("renders the arrivals display section", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByRole("region", { name: /Stop arrivals display/i }),
    ).toBeInTheDocument();
  });

  it("does not render development milestone badges", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.queryByText(/Stage 4/i),
    ).not.toBeInTheDocument();
  });

  it("renders navigation tabs and switches between Stop Explorer and Direct Trip Planner", () => {
    renderWithClient(<Dashboard />);
    const explorerTab = screen.getByRole("tab", { name: /Stop Explorer & Arrivals/i });
    const plannerTab = screen.getByRole("tab", { name: /Direct Trip Planner/i });

    expect(explorerTab).toBeInTheDocument();
    expect(plannerTab).toBeInTheDocument();
    expect(explorerTab).toHaveAttribute("aria-selected", "true");
    expect(plannerTab).toHaveAttribute("aria-selected", "false");

    // Click planner tab
    fireEvent.click(plannerTab);
    expect(plannerTab).toHaveAttribute("aria-selected", "true");
    expect(explorerTab).toHaveAttribute("aria-selected", "false");
    expect(
      screen.getByRole("region", { name: /Direct trip planner/i }),
    ).toBeInTheDocument();
  });
});
