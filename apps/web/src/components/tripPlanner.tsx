import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStops, planTrip } from "../lib/api";
import { useAppStore } from "../stores/appStore";
import type { TripItinerary } from "../types/transit";

export function TripPlanner() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const setSelectedRouteId = useAppStore((state) => state.setSelectedRouteId);

  const [originStopId, setOriginStopId] = useState<string>("");
  const [destStopId, setDestStopId] = useState<string>("");
  const [departureTime, setDepartureTime] = useState<string>("");

  // Fetch stops for the selected feed
  const { data: stopsData, isLoading: isLoadingStops } = useQuery({
    queryKey: ["stops", selectedFeedSlug, 1, 100],
    queryFn: () => fetchStops(selectedFeedSlug!, "", 1, 100),
    enabled: Boolean(selectedFeedSlug),
    staleTime: 60_000,
  });

  const stops = stopsData?.data ?? [];

  // Query direct trip itineraries
  const canPlan = Boolean(
    selectedFeedSlug && originStopId && destStopId && originStopId !== destStopId,
  );

  const {
    data: planData,
    isLoading: isLoadingPlan,
    isError: isPlanError,
    error: planError,
    refetch: refetchPlan,
  } = useQuery({
    queryKey: [
      "tripPlan",
      selectedFeedSlug,
      originStopId,
      destStopId,
      departureTime,
    ],
    queryFn: () =>
      planTrip(
        selectedFeedSlug!,
        originStopId,
        destStopId,
        departureTime || undefined,
      ),
    enabled: canPlan,
    staleTime: 15_000,
  });

  const itineraries = planData?.itineraries ?? [];

  const handleSwapStops = () => {
    setOriginStopId(destStopId);
    setDestStopId(originStopId);
  };

  const handleSelectRoute = (routeId: string) => {
    setSelectedRouteId(routeId);
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <span className="text-xl" role="img" aria-label="Compass">
            🧭
          </span>
          <h2 className="text-lg font-bold text-white tracking-tight">
            Direct Trip Planner
          </h2>
        </div>
        <p className="text-xs text-gray-400 mt-1">
          Find direct scheduled and live trips between two stops in the active feed.
        </p>
      </div>

      {!selectedFeedSlug ? (
        <div
          role="status"
          className="text-center py-8 px-4 bg-gray-950/50 rounded-lg border border-gray-800/80 text-gray-400 text-sm"
        >
          <p className="text-gray-300 font-medium">No Feed Selected</p>
          <p className="text-xs text-gray-500 mt-1">
            Please choose a transit feed above to start planning trips.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Stop Selectors */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
            {/* Origin Stop */}
            <div className="sm:col-span-5 space-y-1.5">
              <label
                htmlFor="planner-origin-stop"
                className="block text-xs font-medium text-gray-300"
              >
                Origin Stop
              </label>
              <select
                id="planner-origin-stop"
                aria-label="Origin Stop"
                value={originStopId}
                onChange={(e) => setOriginStopId(e.target.value)}
                disabled={isLoadingStops || stops.length === 0}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              >
                <option value="">Select origin stop...</option>
                {stops.map((stop) => (
                  <option key={`origin-${stop.stop_id}`} value={stop.stop_id}>
                    {stop.name} ({stop.stop_id})
                  </option>
                ))}
              </select>
            </div>

            {/* Swap Button */}
            <div className="sm:col-span-2 flex justify-center pb-1">
              <button
                type="button"
                onClick={handleSwapStops}
                disabled={!originStopId && !destStopId}
                aria-label="Swap origin and destination stops"
                title="Swap origin and destination"
                className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white border border-gray-700 transition disabled:opacity-30 disabled:pointer-events-none"
              >
                ⇄
              </button>
            </div>

            {/* Destination Stop */}
            <div className="sm:col-span-5 space-y-1.5">
              <label
                htmlFor="planner-dest-stop"
                className="block text-xs font-medium text-gray-300"
              >
                Destination Stop
              </label>
              <select
                id="planner-dest-stop"
                aria-label="Destination Stop"
                value={destStopId}
                onChange={(e) => setDestStopId(e.target.value)}
                disabled={isLoadingStops || stops.length === 0}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
              >
                <option value="">Select destination stop...</option>
                {stops.map((stop) => (
                  <option key={`dest-${stop.stop_id}`} value={stop.stop_id}>
                    {stop.name} ({stop.stop_id})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Time & Options */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <div className="flex items-center gap-2">
              <label
                htmlFor="planner-time"
                className="text-xs text-gray-400 whitespace-nowrap"
              >
                Departure:
              </label>
              <input
                id="planner-time"
                type="time"
                aria-label="Departure Time"
                value={departureTime}
                onChange={(e) => setDepartureTime(e.target.value)}
                className="bg-gray-950 border border-gray-800 rounded-md px-2.5 py-1 text-xs text-white focus:outline-none focus:border-blue-500"
              />
            </div>
            {departureTime && (
              <button
                type="button"
                onClick={() => setDepartureTime("")}
                className="text-[11px] text-blue-400 hover:text-blue-300 underline"
              >
                Reset to Now
              </button>
            )}
          </div>

          {/* Validation Errors */}
          {originStopId && destStopId && originStopId === destStopId && (
            <div
              role="alert"
              className="p-3 bg-red-950/40 border border-red-800/80 rounded-lg text-red-300 text-xs"
            >
              Origin and destination stops must be different.
            </div>
          )}

          {/* Prompt State */}
          {(!originStopId || !destStopId) && (
            <div className="text-center py-6 px-4 bg-gray-950/30 rounded-lg border border-gray-800/60 text-gray-400 text-xs">
              Select both an origin and a destination stop above to view available direct trips.
            </div>
          )}

          {/* Loading State */}
          {canPlan && isLoadingPlan && (
            <div
              role="status"
              className="text-center py-8 space-y-2 text-gray-400 text-xs"
            >
              <div className="inline-block w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              <p>Searching for direct trips...</p>
            </div>
          )}

          {/* Error State */}
          {canPlan && isPlanError && (
            <div
              role="alert"
              className="p-4 bg-red-950/40 border border-red-800/80 rounded-lg text-red-300 text-xs space-y-2"
            >
              <p className="font-medium">Failed to plan trip</p>
              <p className="text-red-400 text-[11px]">
                {planError instanceof Error
                  ? planError.message
                  : "An unexpected error occurred while planning your trip."}
              </p>
              <button
                type="button"
                onClick={() => void refetchPlan()}
                className="px-3 py-1 bg-red-900 hover:bg-red-800 text-white rounded text-xs transition"
              >
                Try Again
              </button>
            </div>
          )}

          {/* Itineraries List */}
          {canPlan && !isLoadingPlan && !isPlanError && (
            <div className="space-y-3 pt-2">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span className="font-medium text-gray-300">
                  {itineraries.length}{" "}
                  {itineraries.length === 1 ? "direct trip" : "direct trips"} found
                </span>
                <span>Departing on or after {departureTime || "current time"}</span>
              </div>

              {itineraries.length === 0 ? (
                <div
                  role="status"
                  className="text-center py-8 px-4 bg-gray-950/40 rounded-lg border border-gray-800/80 text-gray-400 text-xs space-y-1"
                >
                  <p className="text-gray-300 font-medium">No Direct Trips Found</p>
                  <p className="text-gray-500 text-[11px]">
                    No scheduled direct trips connect these two stops at or after the selected departure time.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {itineraries.map((itinerary, index) => (
                    <ItineraryCard
                      key={`${itinerary.trip_id}-${index}`}
                      itinerary={itinerary}
                      onSelectRoute={handleSelectRoute}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ItineraryCardProps {
  itinerary: TripItinerary;
  onSelectRoute: (routeId: string) => void;
}

function ItineraryCard({ itinerary, onSelectRoute }: ItineraryCardProps) {
  const routeColor = itinerary.route_color ? `#${itinerary.route_color}` : "#0055A5";
  const textColor = itinerary.text_color ? `#${itinerary.text_color}` : "#FFFFFF";

  return (
    <article
      aria-label={`Trip on route ${itinerary.route_short_name || itinerary.route_id}`}
      className="p-4 bg-gray-950 border border-gray-800 hover:border-gray-700 rounded-lg transition space-y-3"
    >
      {/* Route & Headsign Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            style={{ backgroundColor: routeColor, color: textColor }}
            className="px-2.5 py-1 rounded font-bold text-xs shadow-sm"
          >
            {itinerary.route_short_name || itinerary.route_id}
          </span>
          <span className="text-xs font-medium text-white truncate max-w-[200px] sm:max-w-xs">
            {itinerary.trip_headsign
              ? `to ${itinerary.trip_headsign}`
              : itinerary.route_long_name || "Direct Journey"}
          </span>
        </div>

        {/* Real-time Status Badge */}
        <div>
          {itinerary.realtime_status === "REALTIME_DELAYED" && (
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-amber-950/70 text-amber-300 border border-amber-800">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
              Delayed (+{Math.round((itinerary.origin.delay_seconds || 0) / 60)}m)
            </span>
          )}
          {itinerary.realtime_status === "REALTIME_EARLY" && (
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-blue-950/70 text-blue-300 border border-blue-800">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Early ({Math.round((itinerary.origin.delay_seconds || 0) / 60)}m)
            </span>
          )}
          {itinerary.realtime_status === "REALTIME_ON_TIME" && (
            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              On Time
            </span>
          )}
          {itinerary.realtime_status === "SCHEDULED" && (
            <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-900 text-gray-400 border border-gray-800">
              Scheduled
            </span>
          )}
        </div>
      </div>

      {/* Origin -> Destination Times */}
      <div className="grid grid-cols-2 gap-4 py-2 border-y border-gray-900 text-xs">
        <div>
          <span className="text-[11px] text-gray-500 uppercase tracking-wider block">
            Departs {itinerary.origin.name}
          </span>
          <span className="text-base font-semibold text-white">
            {itinerary.origin.estimated_time || itinerary.origin.scheduled_time}
          </span>
          {itinerary.origin.delay_seconds ? (
            <span className="text-[10px] text-gray-500 block">
              Sched: {itinerary.origin.scheduled_time}
            </span>
          ) : null}
        </div>

        <div className="text-right">
          <span className="text-[11px] text-gray-500 uppercase tracking-wider block">
            Arrives {itinerary.destination.name}
          </span>
          <span className="text-base font-semibold text-white">
            {itinerary.destination.estimated_time ||
              itinerary.destination.scheduled_time}
          </span>
          {itinerary.destination.delay_seconds ? (
            <span className="text-[10px] text-gray-500 block">
              Sched: {itinerary.destination.scheduled_time}
            </span>
          ) : null}
        </div>
      </div>

      {/* Footer Info & Action */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-3">
          <span>⏱️ {itinerary.duration_minutes} min</span>
          <span>•</span>
          <span>
            {itinerary.intermediate_stops_count === 0
              ? "Non-stop"
              : `${itinerary.intermediate_stops_count} ${
                  itinerary.intermediate_stops_count === 1 ? "stop" : "stops"
                }`}
          </span>
        </div>

        <button
          type="button"
          onClick={() => onSelectRoute(itinerary.route_id)}
          className="text-xs text-blue-400 hover:text-blue-300 font-medium transition"
        >
          View Route on Map →
        </button>
      </div>
    </article>
  );
}
