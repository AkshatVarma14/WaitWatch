import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as api from "../lib/api";
import { useAppStore } from "../stores/appStore";
import { FeedSelector } from "../components/feedSelector";
import { StopSearch } from "../components/stopSearch";
import { ArrivalsBoard } from "../components/arrivalsBoard";
import type {
  FeedSummary,
  PaginatedResponse,
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
        gcTime: 0,
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
  });
});
