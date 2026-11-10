import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
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

  it("renders the Stage 4 status badge", () => {
    renderWithClient(<Dashboard />);
    expect(
      screen.getByText(/Stage 4: Map & Transit Explorer/i),
    ).toBeInTheDocument();
  });
});
