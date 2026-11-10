import { beforeEach, describe, expect, it, vi, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as api from "../lib/api";
import { useAppStore } from "../stores/appStore";
import { FeedSelector } from "../components/feedSelector";
import { StopSearch } from "../components/stopSearch";
import { ArrivalsBoard } from "../components/arrivalsBoard";
import { RouteSelector } from "../components/routeSelector";
import { MapView } from "../components/mapView";
import { MapDetailsPanel } from "../components/mapDetailsPanel";
import type {
  FeedSummary,
  PaginatedResponse,
  RouteMapData,
  RouteSummary,
  StopArrivalPrediction,
  StopSummary,
} from "../types/transit";

const mockFeeds: FeedSummary[] = [
  {
    id: 1,
    city_name: "Metro City",
    slug: "metro-city",
    feed_status: "active",
    is_live_tracking_enabled: true,
    last_static_import_at: "2026-11-10T08:00:00Z",
    last_realtime_poll_at: "2026-11-10T12:00:00Z",
  },
  {
    id: 2,
    city_name: "Valley Transit",
    slug: "valley-transit",
    feed_status: "active",
    is_live_tracking_enabled: false,
    last_static_import_at: "2026-11-10T07:00:00Z",
    last_realtime_poll_at: null,
  },
];

const mockRoutesMetro: RouteSummary[] = [
  {
    route_id: "route-blue",
    agency_id: "agency-1",
    short_name: "B1",
    long_name: "Blue Crosstown",
    description: "Main crosstown service",
    route_type: 3,
    route_url: null,
    route_color: "0052CC",
    text_color: "FFFFFF",
    sort_order: 1,
  },
  {
    route_id: "route-red",
    agency_id: "agency-1",
    short_name: "R9",
    long_name: "Red Line Metro",
    description: "Rapid transit spine",
    route_type: 1,
    route_url: null,
    route_color: "D32F2F",
    text_color: "FFFFFF",
    sort_order: 2,
  },
];

const mockRouteMapWithShapes: RouteMapData = {
  feed_slug: "metro-city",
  route_id: "route-blue",
  route_short_name: "B1",
  route_long_name: "Blue Crosstown",
  route_color: "#0052CC",
  text_color: "#FFFFFF",
  shapes: [
    {
      shape_id: "shape_blue_01",
      points: [
        { latitude: 40.7128, longitude: -74.006, sequence: 1, distance_traveled: 0.0 },
        { latitude: 40.7300, longitude: -73.995, sequence: 2, distance_traveled: 2100.5 },
        { latitude: 40.7580, longitude: -73.985, sequence: 3, distance_traveled: 5200.0 },
      ],
    },
  ],
  stops: [
    {
      stop_id: "MC-101",
      name: "Downtown Terminal",
      code: "101",
      latitude: 40.7128,
      longitude: -74.006,
      stop_sequence: 1,
      direction_id: 0,
      wheelchair_boarding: 1,
    },
    {
      stop_id: "MC-102",
      name: "Central Park West",
      code: "102",
      latitude: 40.785091,
      longitude: -73.968285,
      stop_sequence: 2,
      direction_id: 0,
      wheelchair_boarding: 0,
    },
  ],
  vehicles: [
    {
      entity_id: "veh-4001",
      vehicle_id: "4001",
      vehicle_label: "Fleet 4001",
      latitude: 40.7300,
      longitude: -73.995,
      bearing: 45.0,
      speed: 12.5,
      current_status: 1,
      trip_id: "trip-blue-1",
      observed_at: "2026-11-10T12:14:30Z",
    },
    {
      entity_id: "veh-4002",
      vehicle_id: "4002",
      vehicle_label: null,
      latitude: 40.7450,
      longitude: -73.990,
      bearing: 180.0,
      speed: 8.0,
      current_status: 2,
      trip_id: "trip-blue-2",
      observed_at: "2026-11-10T12:13:50Z",
    },
  ],
};

const mockRouteMapWithoutShapes: RouteMapData = {
  feed_slug: "metro-city",
  route_id: "route-red",
  route_short_name: "R9",
  route_long_name: "Red Line Metro",
  route_color: "#D32F2F",
  text_color: "#FFFFFF",
  shapes: [], // Explicitly empty shapes
  stops: [
    {
      stop_id: "MC-201",
      name: "South Station",
      code: "201",
      latitude: 40.7600,
      longitude: -73.9700,
      stop_sequence: 1,
      direction_id: 0,
      wheelchair_boarding: 1,
    },
  ],
  vehicles: [],
};

const mockStopsMetro: StopSummary[] = [
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
];

const mockArrivals: StopArrivalPrediction[] = [
  {
    feed_slug: "metro-city",
    feed_id: 1,
    stop_id: "MC-101",
    trip_id: "trip-blue-1",
    route_id: "route-blue",
    route_short_name: "B1",
    trip_headsign: "Uptown Express",
    vehicle_id: "veh-4001",
    stop_sequence: 5,
    scheduled_arrival_time: "2026-11-10T12:15:00Z",
    estimated_arrival_time: "2026-11-10T12:18:00Z",
    delay_seconds: 180, // +3 min late
    prediction_source: "HISTORY_ADJUSTED",
    source_observation_time: "2026-11-10T12:14:30Z",
  },
  {
    feed_slug: "metro-city",
    feed_id: 1,
    stop_id: "MC-101",
    trip_id: "trip-red-9",
    route_id: "route-red",
    route_short_name: "R9",
    trip_headsign: "South Station",
    vehicle_id: null,
    stop_sequence: 2,
    scheduled_arrival_time: "2026-11-10T12:20:00Z",
    estimated_arrival_time: "2026-11-10T12:20:00Z",
    delay_seconds: 0, // On time
    prediction_source: "SCHEDULE_ONLY",
    source_observation_time: null,
  },
];

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

describe("Transit Explorer Components", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.getState().reset();
  });

  describe("FeedSelector", () => {
    it("renders feed options from API", async () => {
      vi.spyOn(api, "fetchFeeds").mockResolvedValue(mockFeeds);

      renderWithClient(<FeedSelector />);

      expect(screen.getByRole("status")).toHaveTextContent("Loading feeds...");

      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /Metro City/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("option", { name: /Valley Transit/i }),
        ).toBeInTheDocument();
      });
    });

    it("selecting a feed updates app store and displays status badges", async () => {
      vi.spyOn(api, "fetchFeeds").mockResolvedValue(mockFeeds);

      renderWithClient(<FeedSelector />);

      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /Metro City/i }),
        ).toBeInTheDocument();
      });

      const select = screen.getByRole("combobox", {
        name: /Select transit feed/i,
      });
      fireEvent.change(select, { target: { value: "metro-city" } });

      expect(useAppStore.getState().selectedFeedSlug).toBe("metro-city");
      expect(screen.getByText(/Live Tracking Active/i)).toBeInTheDocument();
      expect(screen.getByText(/Status: active/i)).toBeInTheDocument();
    });

    it("shows error alert and retry button on fetch failure", async () => {
      const fetchSpy = vi
        .spyOn(api, "fetchFeeds")
        .mockRejectedValueOnce(new Error("Network connection refused"))
        .mockResolvedValueOnce(mockFeeds);

      renderWithClient(<FeedSelector />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Network connection refused",
        );
      });

      const retryBtn = screen.getByRole("button", { name: /Retry/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("StopSearch", () => {
    it("displays prompt when no feed is selected", () => {
      renderWithClient(<StopSearch />);
      expect(
        screen.getByText(/Select a transit feed above to search stops/i),
      ).toBeInTheDocument();
    });

    it("fetches and renders stops when a feed is selected", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");

      const mockResponse: PaginatedResponse<StopSummary> = {
        data: mockStopsMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 20,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      };

      vi.spyOn(api, "fetchStops").mockResolvedValue(mockResponse);

      renderWithClient(<StopSearch />);

      await waitFor(() => {
        expect(screen.getByText("Downtown Terminal")).toBeInTheDocument();
        expect(screen.getByText("Central Park West")).toBeInTheDocument();
      });

      expect(screen.getByText("#101")).toBeInTheDocument();
      expect(screen.getByText("Bay 4")).toBeInTheDocument();
      expect(screen.getByText(/♿ Accessible/i)).toBeInTheDocument();
    });

    it("selecting a stop updates the store with selected stop", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");

      const mockResponse: PaginatedResponse<StopSummary> = {
        data: mockStopsMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 20,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      };

      vi.spyOn(api, "fetchStops").mockResolvedValue(mockResponse);

      renderWithClient(<StopSearch />);

      await waitFor(() => {
        expect(screen.getByText("Downtown Terminal")).toBeInTheDocument();
      });

      const stopBtn = screen.getByText("Downtown Terminal").closest("button");
      expect(stopBtn).not.toBeNull();
      fireEvent.click(stopBtn!);

      expect(useAppStore.getState().selectedStop?.stop_id).toBe("MC-101");
      expect(screen.getByText("Selected ✓")).toBeInTheDocument();
    });

    it("displays empty state when no stops match", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");

      const emptyResponse: PaginatedResponse<StopSummary> = {
        data: [],
        pagination: {
          total: 0,
          page: 1,
          page_size: 20,
          total_pages: 0,
          has_next: false,
          has_prev: false,
        },
      };

      vi.spyOn(api, "fetchStops").mockResolvedValue(emptyResponse);

      renderWithClient(<StopSearch />);

      await waitFor(() => {
        expect(
          screen.getByText(/No stops found in this feed/i),
        ).toBeInTheDocument();
      });
    });
  });

  describe("ArrivalsBoard", () => {
    it("prompts to select a feed when no feed is active", () => {
      renderWithClient(<ArrivalsBoard />);
      expect(screen.getByText("No Feed Selected")).toBeInTheDocument();
    });

    it("prompts to select a stop when feed is active but stop is null", () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      renderWithClient(<ArrivalsBoard />);
      expect(screen.getByText("Select a Stop")).toBeInTheDocument();
    });

    it("renders arrival cards with scheduled/estimated times, delays, and source badges", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      vi.spyOn(api, "fetchArrivals").mockResolvedValue(mockArrivals);

      renderWithClient(<ArrivalsBoard />);

      // Wait for arrivals to load and render cards
      await waitFor(() => {
        expect(screen.getByText("B1")).toBeInTheDocument();
        expect(screen.getByText("Uptown Express")).toBeInTheDocument();
      });

      // Stop details
      expect(screen.getByText("Downtown Terminal")).toBeInTheDocument();
      expect(screen.getByText("Stop #101")).toBeInTheDocument();

      // Agency timezone disclosure
      expect(
        screen.getByText(/America\/New_York \(Agency Time\)/i),
      ).toBeInTheDocument();

      // Trip 1: B1 Uptown Express (+3 min late, Live + History)
      expect(screen.getByText("+3 min late")).toBeInTheDocument();
      expect(screen.getByText("Live + History")).toBeInTheDocument();
      expect(screen.getByText(/Vehicle #veh-4001/i)).toBeInTheDocument();

      // Trip 2: R9 South Station (On time, Schedule)
      expect(screen.getByText("R9")).toBeInTheDocument();
      expect(screen.getByText("South Station")).toBeInTheDocument();
      expect(screen.getByText("On time")).toBeInTheDocument();
      expect(screen.getByText("Schedule")).toBeInTheDocument();
    });

    it("triggers refetch when Refresh button is clicked", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      const fetchSpy = vi
        .spyOn(api, "fetchArrivals")
        .mockResolvedValue(mockArrivals);

      renderWithClient(<ArrivalsBoard />);

      // Wait for initial fetch to settle so the refresh button is enabled
      await waitFor(() => {
        expect(screen.getByText("Uptown Express")).toBeInTheDocument();
      });

      const refreshBtn = screen.getByRole("button", {
        name: /Refresh arrivals/i,
      });
      expect(refreshBtn).not.toBeDisabled();
      fireEvent.click(refreshBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(2);
      });
    });

    it("renders empty state when there are no arrivals", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      vi.spyOn(api, "fetchArrivals").mockResolvedValue([]);

      renderWithClient(<ArrivalsBoard />);

      await waitFor(() => {
        expect(screen.getByText("No Upcoming Arrivals")).toBeInTheDocument();
      });
    });

    it("renders error alert with retry on failure", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      vi.spyOn(api, "fetchArrivals").mockRejectedValue(
        new Error("Database service is temporarily unavailable"),
      );

      renderWithClient(<ArrivalsBoard />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Database service is temporarily unavailable",
        );
      });
    });
  });

  describe("RouteSelector", () => {
    it("returns null when no feed is selected", () => {
      const { container } = renderWithClient(<RouteSelector />);
      expect(container.firstChild).toBeNull();
    });

    it("fetches and renders route options when feed is selected", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      vi.spyOn(api, "fetchRoutes").mockResolvedValue({
        data: mockRoutesMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 50,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      });

      renderWithClient(<RouteSelector />);

      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /B1 — Blue Crosstown/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("option", { name: /R9 — Red Line Metro/i }),
        ).toBeInTheDocument();
      });
    });

    it("selecting a route updates selectedRouteId in appStore", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      vi.spyOn(api, "fetchRoutes").mockResolvedValue({
        data: mockRoutesMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 50,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      });

      renderWithClient(<RouteSelector />);

      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /B1 — Blue Crosstown/i }),
        ).toBeInTheDocument();
      });

      const select = screen.getByRole("combobox", {
        name: /Select transit route/i,
      });
      fireEvent.change(select, { target: { value: "route-blue" } });

      expect(useAppStore.getState().selectedRouteId).toBe("route-blue");
    });

    it("displays error alert and retry button when route fetch fails", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      const fetchSpy = vi
        .spyOn(api, "fetchRoutes")
        .mockRejectedValueOnce(new Error("Route service timeout"))
        .mockResolvedValueOnce({
          data: mockRoutesMetro,
          pagination: {
            total: 2,
            page: 1,
            page_size: 50,
            total_pages: 1,
            has_next: false,
            has_prev: false,
          },
        });

      renderWithClient(<RouteSelector />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Route service timeout",
        );
      });

      const retryBtn = screen.getByRole("button", { name: /Retry/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("MapView", () => {
    it("displays select route prompt when no route is selected", () => {
      renderWithClient(<MapView />);
      expect(screen.getByText("Select a Transit Route")).toBeInTheDocument();
      expect(
        screen.getByText(/Choose a route above to visualize its true GTFS shape polyline/i),
      ).toBeInTheDocument();
      // Tile attribution is present
      expect(screen.getAllByText(/OpenStreetMap/i).length).toBeGreaterThanOrEqual(1);
    });

    it("renders active shape badge and vehicle count when shapes and vehicles are present", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");
      vi.spyOn(api, "fetchRouteMap").mockResolvedValue(mockRouteMapWithShapes);

      renderWithClient(<MapView />);

      await waitFor(() => {
        expect(screen.getByText(/• Route B1/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/GTFS Shape Active \(1 track\)/i)).toBeInTheDocument();
      expect(screen.getByText(/2 Live Vehicles/i)).toBeInTheDocument();
      expect(screen.getAllByText(/OpenStreetMap/i).length).toBeGreaterThanOrEqual(1);
    });

    it("displays warning badge when route shape is unavailable without fabricating lines", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-red");
      vi.spyOn(api, "fetchRouteMap").mockResolvedValue(mockRouteMapWithoutShapes);

      renderWithClient(<MapView />);

      await waitFor(() => {
        expect(screen.getByText(/• Route R9/i)).toBeInTheDocument();
      });

      // Crucial requirement: clear "route shape unavailable" warning state
      expect(
        screen.getByText(/⚠️ Route shape unavailable — showing stops only/i),
      ).toBeInTheDocument();
      // No live vehicle badge when vehicles array is empty
      expect(screen.queryByText(/Live Vehicles/i)).not.toBeInTheDocument();
    });

    it("displays error banner and retry button when route map fetch fails", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");
      const fetchSpy = vi
        .spyOn(api, "fetchRouteMap")
        .mockRejectedValueOnce(new Error("Geometry data corrupted"))
        .mockResolvedValueOnce(mockRouteMapWithShapes);

      renderWithClient(<MapView />);

      await waitFor(() => {
        expect(screen.getByRole("alert")).toHaveTextContent(
          "Geometry data corrupted",
        );
      });

      const retryBtn = screen.getByRole("button", { name: /Retry/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("MapDetailsPanel", () => {
    it("returns null when no route or route data is loaded", () => {
      const { container } = renderWithClient(<MapDetailsPanel />);
      expect(container.firstChild).toBeNull();
    });

    it("renders stops tab with count and allows stop selection", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");
      vi.spyOn(api, "fetchRouteMap").mockResolvedValue(mockRouteMapWithShapes);

      renderWithClient(<MapDetailsPanel />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Stops \(2\)/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /Live Vehicles \(2\)/i }),
        ).toBeInTheDocument();
      });

      expect(screen.getByText("Downtown Terminal")).toBeInTheDocument();
      expect(screen.getByText("Central Park West")).toBeInTheDocument();

      // Click Downtown Terminal stop
      const stopBtn = screen.getByText("Downtown Terminal").closest("button");
      expect(stopBtn).not.toBeNull();
      fireEvent.click(stopBtn!);

      expect(useAppStore.getState().selectedStop?.stop_id).toBe("MC-101");
      expect(screen.getByText("Active ✓")).toBeInTheDocument();
    });

    it("switches to vehicles tab and selects vehicle to inspect telemetry", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");
      vi.spyOn(api, "fetchRouteMap").mockResolvedValue(mockRouteMapWithShapes);

      renderWithClient(<MapDetailsPanel />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Live Vehicles \(2\)/i }),
        ).toBeInTheDocument();
      });

      // Click Live Vehicles tab
      fireEvent.click(screen.getByRole("button", { name: /Live Vehicles \(2\)/i }));

      // Vehicle cards
      expect(screen.getByText("Vehicle #Fleet 4001")).toBeInTheDocument();
      expect(screen.getByText("Vehicle #4002")).toBeInTheDocument();

      // Click first vehicle to inspect telemetry
      fireEvent.click(screen.getByText("Vehicle #Fleet 4001").closest("button")!);

      expect(useAppStore.getState().selectedVehicleId).toBe("veh-4001");

      // Detailed telemetry card rendered
      expect(screen.getAllByText(/45 km\/h/i).length).toBeGreaterThanOrEqual(1); // 12.5 * 3.6 = 45 km/h
      expect(screen.getByText(/45°/i)).toBeInTheDocument();
      expect(screen.getByText(/Stopped at station/i)).toBeInTheDocument();
      expect(screen.getByText(/40.7300, -73.9950/i)).toBeInTheDocument();

      // Clear selection button works
      const clearBtn = screen.getByRole("button", { name: /Clear selection/i });
      fireEvent.click(clearBtn);
      expect(useAppStore.getState().selectedVehicleId).toBeNull();
    });
  });

  describe("Feed Isolation Integration", () => {
    it("switching feeds clears previously selected stop and isolates arrivals", async () => {
      vi.spyOn(api, "fetchFeeds").mockResolvedValue(mockFeeds);
      vi.spyOn(api, "fetchStops").mockResolvedValue({
        data: mockStopsMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 20,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      });
      vi.spyOn(api, "fetchArrivals").mockResolvedValue(mockArrivals);

      // Render all three connected components
      renderWithClient(
        <div>
          <FeedSelector />
          <StopSearch />
          <ArrivalsBoard />
        </div>,
      );

      // 1. Select Metro City feed
      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /Metro City/i }),
        ).toBeInTheDocument();
      });
      const feedSelect = screen.getByRole("combobox", {
        name: /Select transit feed/i,
      });
      fireEvent.change(feedSelect, { target: { value: "metro-city" } });

      // 2. Select Downtown Terminal stop
      await waitFor(() => {
        expect(screen.getByText("Downtown Terminal")).toBeInTheDocument();
      });
      fireEvent.click(
        screen.getByText("Downtown Terminal").closest("button")!,
      );

      // Arrivals are displayed for Downtown Terminal
      await waitFor(() => {
        expect(screen.getByText("Uptown Express")).toBeInTheDocument();
      });

      // 3. Now switch feed to Valley Transit
      fireEvent.change(feedSelect, { target: { value: "valley-transit" } });

      // 4. Verify feed isolation: selected stop was reset to null, arrivals view reset to "Select a Stop"
      expect(useAppStore.getState().selectedFeedSlug).toBe("valley-transit");
      expect(useAppStore.getState().selectedStop).toBeNull();

      await waitFor(() => {
        expect(screen.getByText("Select a Stop")).toBeInTheDocument();
      });
      // Downtown Terminal arrivals should no longer be displayed
      expect(screen.queryByText("Uptown Express")).not.toBeInTheDocument();
    });

    it("switching feeds clears selected route, stop, vehicle, and resets map navigator", async () => {
      vi.spyOn(api, "fetchFeeds").mockResolvedValue(mockFeeds);
      vi.spyOn(api, "fetchRoutes").mockResolvedValue({
        data: mockRoutesMetro,
        pagination: {
          total: 2,
          page: 1,
          page_size: 50,
          total_pages: 1,
          has_next: false,
          has_prev: false,
        },
      });
      vi.spyOn(api, "fetchRouteMap").mockResolvedValue(mockRouteMapWithShapes);

      renderWithClient(
        <div>
          <FeedSelector />
          <RouteSelector />
          <MapView />
          <MapDetailsPanel />
        </div>,
      );

      // 1. Select Metro City feed
      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /Metro City/i }),
        ).toBeInTheDocument();
      });
      const feedSelect = screen.getByRole("combobox", {
        name: /Select transit feed/i,
      });
      fireEvent.change(feedSelect, { target: { value: "metro-city" } });

      // 2. Select Route B1
      await waitFor(() => {
        expect(
          screen.getByRole("option", { name: /B1 — Blue Crosstown/i }),
        ).toBeInTheDocument();
      });
      const routeSelect = screen.getByRole("combobox", {
        name: /Select transit route/i,
      });
      fireEvent.change(routeSelect, { target: { value: "route-blue" } });

      // 3. Map loads Route B1 with active shapes and vehicles
      await waitFor(() => {
        expect(screen.getByText(/• Route B1/i)).toBeInTheDocument();
        expect(screen.getByText(/GTFS Shape Active \(1 track\)/i)).toBeInTheDocument();
      });

      // 4. In details panel, select vehicle Fleet 4001
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /Live Vehicles \(2\)/i })).toBeInTheDocument();
      });
      fireEvent.click(screen.getByRole("button", { name: /Live Vehicles \(2\)/i }));
      fireEvent.click(screen.getByText("Vehicle #Fleet 4001").closest("button")!);
      expect(useAppStore.getState().selectedVehicleId).toBe("veh-4001");

      // 5. Now switch feed to Valley Transit
      fireEvent.change(feedSelect, { target: { value: "valley-transit" } });

      // 6. Verify full isolation: feed changed, route reset, vehicle reset, stop reset
      expect(useAppStore.getState().selectedFeedSlug).toBe("valley-transit");
      expect(useAppStore.getState().selectedRouteId).toBeNull();
      expect(useAppStore.getState().selectedVehicleId).toBeNull();
      expect(useAppStore.getState().selectedStop).toBeNull();

      // Map returns to "Select a Transit Route" prompt
      await waitFor(() => {
        expect(screen.getByText("Select a Transit Route")).toBeInTheDocument();
      });
      expect(screen.queryByText(/• Route B1/i)).not.toBeInTheDocument();
    });
  });

  describe("Realtime Polling and Live Refresh", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it("displays live polling indicator and timestamp on ArrivalsBoard", async () => {
      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);
      vi.spyOn(api, "fetchArrivals").mockResolvedValue(mockArrivals);

      renderWithClient(<ArrivalsBoard />);

      await waitFor(() => {
        expect(screen.getByText("B1")).toBeInTheDocument();
      });

      // Accessible live polling status and timestamp
      expect(screen.getByText(/Live \(30s\)/i)).toBeInTheDocument();
      expect(screen.getByText(/Updated/i)).toBeInTheDocument();
    });

    it("periodically refreshes stop arrivals every 30 seconds using fake timers", async () => {
      vi.useFakeTimers();

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      const fetchSpy = vi
        .spyOn(api, "fetchArrivals")
        .mockResolvedValue(mockArrivals);

      renderWithClient(<ArrivalsBoard />);

      // Flush initial query
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Advance by 30 seconds (default polling interval)
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      // Advance by another 30 seconds
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(3);
    });

    it("periodically refreshes route map and vehicles every 30 seconds using fake timers", async () => {
      vi.useFakeTimers();

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");

      const fetchSpy = vi
        .spyOn(api, "fetchRouteMap")
        .mockResolvedValue(mockRouteMapWithShapes);

      renderWithClient(<MapView />);

      // Flush initial query
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Advance by 30 seconds
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);
    });

    it("preserves last successful arrivals on transient background refresh failure", async () => {
      vi.useFakeTimers();

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      // First call succeeds, second call fails with transient error
      const fetchSpy = vi
        .spyOn(api, "fetchArrivals")
        .mockResolvedValueOnce(mockArrivals)
        .mockRejectedValueOnce(new Error("503 Backend Service Temporarily Unavailable"));

      renderWithClient(<ArrivalsBoard />);

      // Flush initial successful load
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(screen.getByText("B1")).toBeInTheDocument();
      expect(screen.getByText("Uptown Express")).toBeInTheDocument();

      // Trigger background poll which fails
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      // Crucial requirements:
      // 1. Existing arrival data is NOT wiped or replaced by blank screen
      expect(screen.getByText("B1")).toBeInTheDocument();
      expect(screen.getByText("Uptown Express")).toBeInTheDocument();

      // 2. Clear warning banner is displayed with last updated timestamp
      expect(
        screen.getByText(/Live update failed/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Displaying predictions from/i),
      ).toBeInTheDocument();

      // 3. Status indicator shows "Stale"
      expect(screen.getByText(/⚠️ Stale/i)).toBeInTheDocument();
    });

    it("preserves map view on transient background refresh failure", async () => {
      vi.useFakeTimers();

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedRouteId("route-blue");

      const fetchSpy = vi
        .spyOn(api, "fetchRouteMap")
        .mockResolvedValueOnce(mockRouteMapWithShapes)
        .mockRejectedValueOnce(new Error("500 Internal Error"));

      renderWithClient(<MapView />);

      // Initial successful load
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/• Route B1/i)).toBeInTheDocument();

      // Background poll failure
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(100);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      // Route header and map remain visible
      expect(screen.getByText(/• Route B1/i)).toBeInTheDocument();
      expect(screen.getByText(/⚠️ Stale/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Live vehicle refresh failed/i),
      ).toBeInTheDocument();
    });

    it("pauses polling while document is hidden and resumes on visibility return", async () => {
      vi.useFakeTimers();

      let visibilityState = "visible";
      const visibilitySpy = vi
        .spyOn(document, "visibilityState", "get")
        .mockImplementation(() => visibilityState as DocumentVisibilityState);

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      const fetchSpy = vi
        .spyOn(api, "fetchArrivals")
        .mockResolvedValue(mockArrivals);

      renderWithClient(<ArrivalsBoard />);

      // Initial query resolves
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Document becomes hidden
      visibilityState = "hidden";
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // Advance by 60 seconds (2 intervals) while hidden
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      // No extra calls should have been made while hidden
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Document returns to visible
      visibilityState = "visible";
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });

      // Visibility return triggers immediate refresh
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(2);

      visibilitySpy.mockRestore();
    });

    it("does not poll when stop is deselected or feed is cleared", async () => {
      vi.useFakeTimers();

      useAppStore.getState().setSelectedFeedSlug("metro-city");
      useAppStore.getState().setSelectedStop(mockStopsMetro[0]!);

      const fetchSpy = vi
        .spyOn(api, "fetchArrivals")
        .mockResolvedValue(mockArrivals);

      const { rerender } = renderWithClient(<ArrivalsBoard />);

      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Deselect stop
      act(() => {
        useAppStore.getState().setSelectedStop(null);
      });
      rerender(
        <QueryClientProvider client={createTestQueryClient()}>
          <ArrivalsBoard />
        </QueryClientProvider>,
      );

      // Advance by 60s
      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000);
      });
      // No additional calls for deselected stop
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });
  });
});
