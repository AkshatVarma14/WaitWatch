import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as api from "../lib/api";
import { useAppStore } from "../stores/appStore";
import { TripPlanner } from "../components/tripPlanner";
import type { PaginatedResponse, StopSummary, TripPlanResponse } from "../types/transit";

const mockStops: StopSummary[] = [
  {
    stop_id: "MC-101",
    code: "101",
    name: "Downtown Terminal",
    description: "Bay 4",
    latitude: 40.7128,
    longitude: -74.006,
    parent_station_id: null,
    location_type: 0,
    wheelchair_boarding: 1,
    platform_code: "4",
    timezone: "America/New_York",
  },
  {
    stop_id: "MC-102",
    code: "102",
    name: "Central Park West",
    description: null,
    latitude: 40.785091,
    longitude: -73.968285,
    parent_station_id: null,
    location_type: 0,
    wheelchair_boarding: 0,
    platform_code: null,
    timezone: "America/New_York",
  },
  {
    stop_id: "MC-103",
    code: "103",
    name: "Uptown Plaza",
    description: null,
    latitude: 40.8000,
    longitude: -73.9500,
    parent_station_id: null,
    location_type: 0,
    wheelchair_boarding: 1,
    platform_code: null,
    timezone: "America/New_York",
  },
];

const mockPaginatedStops: PaginatedResponse<StopSummary> = {
  data: mockStops,
  pagination: {
    total: 3,
    page: 1,
    page_size: 100,
    total_pages: 1,
    has_next: false,
    has_prev: false,
  },
};

const mockTripPlan: TripPlanResponse = {
  feed_slug: "metro-city",
  origin_stop_id: "MC-101",
  destination_stop_id: "MC-103",
  target_date: "2026-11-10",
  target_time: "08:00:00",
  itineraries: [
    {
      trip_id: "trip-express-1",
      route_id: "route-blue",
      route_short_name: "B1",
      route_long_name: "Blue Crosstown",
      route_color: "0052CC",
      text_color: "FFFFFF",
      route_type: 3,
      trip_headsign: "Uptown Express",
      direction_id: 0,
      origin: {
        stop_id: "MC-101",
        name: "Downtown Terminal",
        latitude: 40.7128,
        longitude: -74.006,
        scheduled_time: "08:15:00",
        estimated_time: "08:20:00",
        delay_seconds: 300,
        stop_sequence: 1,
      },
      destination: {
        stop_id: "MC-103",
        name: "Uptown Plaza",
        latitude: 40.8000,
        longitude: -73.9500,
        scheduled_time: "08:45:00",
        estimated_time: "08:50:00",
        delay_seconds: 300,
        stop_sequence: 5,
      },
      duration_minutes: 30,
      intermediate_stops_count: 3,
      realtime_status: "REALTIME_DELAYED",
    },
    {
      trip_id: "trip-local-2",
      route_id: "route-red",
      route_short_name: "R9",
      route_long_name: "Red Line Metro",
      route_color: "D32F2F",
      text_color: "FFFFFF",
      route_type: 1,
      trip_headsign: null,
      direction_id: 0,
      origin: {
        stop_id: "MC-101",
        name: "Downtown Terminal",
        latitude: 40.7128,
        longitude: -74.006,
        scheduled_time: "08:30:00",
        estimated_time: "08:30:00",
        delay_seconds: null,
        stop_sequence: 1,
      },
      destination: {
        stop_id: "MC-103",
        name: "Uptown Plaza",
        latitude: 40.8000,
        longitude: -73.9500,
        scheduled_time: "08:55:00",
        estimated_time: "08:55:00",
        delay_seconds: null,
        stop_sequence: 2,
      },
      duration_minutes: 25,
      intermediate_stops_count: 0,
      realtime_status: "SCHEDULED",
    },
  ],
};

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 60_000,
      },
    },
  });
}

function renderWithClient(ui: ReactNode) {
  const queryClient = createTestQueryClient();
  return {
    ...render(
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    ),
    queryClient,
  };
}

describe("TripPlanner Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.getState().reset();
  });

  it("renders 'No Feed Selected' status when no feed is chosen", () => {
    renderWithClient(<TripPlanner />);
    expect(screen.getByText("No Feed Selected")).toBeInTheDocument();
    expect(
      screen.getByText(/Please choose a transit feed above/i),
    ).toBeInTheDocument();
  });

  it("loads and populates stops when feed is selected", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
      expect(screen.getAllByText(/Central Park West \(MC-102\)/i)).toHaveLength(2);
      expect(screen.getAllByText(/Uptown Plaza \(MC-103\)/i)).toHaveLength(2);
    });

    expect(
      screen.getByText(
        "Select both an origin and a destination stop above to view available direct trips.",
      ),
    ).toBeInTheDocument();
  });

  it("shows error alert when origin and destination stops are identical", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-101" },
    });

    expect(
      screen.getByText("Origin and destination stops must be different."),
    ).toBeInTheDocument();
  });

  it("swaps origin and destination stops when swap button is clicked", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    expect(screen.getByLabelText("Origin Stop")).toHaveValue("MC-101");
    expect(screen.getByLabelText("Destination Stop")).toHaveValue("MC-103");

    const swapButton = screen.getByLabelText("Swap origin and destination stops");
    fireEvent.click(swapButton);

    expect(screen.getByLabelText("Origin Stop")).toHaveValue("MC-103");
    expect(screen.getByLabelText("Destination Stop")).toHaveValue("MC-101");
  });

  it("plans trip and renders itineraries with real-time status and non-stop badges", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    const planTripSpy = vi.spyOn(api, "planTrip").mockResolvedValue(mockTripPlan);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    await waitFor(() => {
      expect(planTripSpy).toHaveBeenCalledWith("metro-city", "MC-101", "MC-103", undefined);
      expect(screen.getByText("2 direct trips found")).toBeInTheDocument();
    });

    // Check itinerary 1 (delayed)
    expect(screen.getByText("B1")).toBeInTheDocument();
    expect(screen.getByText("to Uptown Express")).toBeInTheDocument();
    expect(screen.getByText("Delayed (+5m)")).toBeInTheDocument();
    expect(screen.getByText("08:20:00")).toBeInTheDocument();
    expect(screen.getByText("Sched: 08:15:00")).toBeInTheDocument();
    expect(screen.getByText("⏱️ 30 min")).toBeInTheDocument();
    expect(screen.getByText("3 stops")).toBeInTheDocument();

    // Check itinerary 2 (scheduled, non-stop)
    expect(screen.getByText("R9")).toBeInTheDocument();
    expect(screen.getByText("Red Line Metro")).toBeInTheDocument();
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText("⏱️ 25 min")).toBeInTheDocument();
    expect(screen.getByText("Non-stop")).toBeInTheDocument();
  });

  it("calls setSelectedRouteId when 'View Route on Map' is clicked", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    vi.spyOn(api, "planTrip").mockResolvedValue(mockTripPlan);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    await waitFor(() => {
      expect(screen.getAllByText("View Route on Map →").length).toBe(2);
    });

    const routeButtons = screen.getAllByText("View Route on Map →");
    fireEvent.click(routeButtons[0]!);

    expect(useAppStore.getState().selectedRouteId).toBe("route-blue");
  });

  it("renders empty state when no itineraries are found", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    vi.spyOn(api, "planTrip").mockResolvedValue({
      ...mockTripPlan,
      itineraries: [],
    });
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    await waitFor(() => {
      expect(screen.getByText("No Direct Trips Found")).toBeInTheDocument();
      expect(
        screen.getByText(
          "No scheduled direct trips connect these two stops at or after the selected departure time.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("renders error state when planTrip fails and allows retry", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    const planTripSpy = vi.spyOn(api, "planTrip").mockRejectedValue(new Error("Network timeout"));
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    await waitFor(() => {
      expect(screen.getByText("Failed to plan trip")).toBeInTheDocument();
      expect(screen.getByText("Network timeout")).toBeInTheDocument();
    });

    planTripSpy.mockResolvedValueOnce(mockTripPlan);
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));

    await waitFor(() => {
      expect(screen.getByText("2 direct trips found")).toBeInTheDocument();
    });
  });

  it("supports departure time input and reset", async () => {
    vi.spyOn(api, "fetchStops").mockResolvedValue(mockPaginatedStops);
    const planTripSpy = vi.spyOn(api, "planTrip").mockResolvedValue(mockTripPlan);
    useAppStore.getState().setSelectedFeedSlug("metro-city");

    renderWithClient(<TripPlanner />);

    await waitFor(() => {
      expect(screen.getAllByText(/Downtown Terminal \(MC-101\)/i)).toHaveLength(2);
    });

    fireEvent.change(screen.getByLabelText("Origin Stop"), {
      target: { value: "MC-101" },
    });
    fireEvent.change(screen.getByLabelText("Destination Stop"), {
      target: { value: "MC-103" },
    });

    await waitFor(() => {
      expect(planTripSpy).toHaveBeenCalledWith("metro-city", "MC-101", "MC-103", undefined);
    });

    const timeInput = screen.getByLabelText("Departure Time");
    fireEvent.change(timeInput, { target: { value: "09:30" } });

    await waitFor(() => {
      expect(planTripSpy).toHaveBeenCalledWith("metro-city", "MC-101", "MC-103", "09:30");
    });

    const resetButton = screen.getByRole("button", { name: "Reset to Now" });
    fireEvent.click(resetButton);

    await waitFor(() => {
      expect(planTripSpy).toHaveBeenCalledWith("metro-city", "MC-101", "MC-103", undefined);
    });
  });
});
