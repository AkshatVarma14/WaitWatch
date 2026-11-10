import { useQuery } from "@tanstack/react-query";
import { fetchArrivals } from "../lib/api";
import {
  formatDelay,
  formatLastUpdated,
  formatObservationAge,
  formatPredictionSource,
  formatTime,
} from "../lib/formatters";
import {
  getPollingIntervalMs,
  useDocumentVisibility,
  usePollingVisibilityRefresh,
} from "../lib/polling";
import { useAppStore } from "../stores/appStore";
import type { StopArrivalPrediction } from "../types/transit";

export function ArrivalsBoard() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const selectedStop = useAppStore((state) => state.selectedStop);

  const pollingInterval = getPollingIntervalMs();
  const isPollingEnabled = Boolean(selectedFeedSlug && selectedStop);
  const isVisible = useDocumentVisibility();

  const {
    data: arrivals,
    dataUpdatedAt,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["arrivals", selectedFeedSlug, selectedStop?.stop_id],
    queryFn: () => fetchArrivals(selectedFeedSlug!, selectedStop!.stop_id),
    enabled: isPollingEnabled,
    refetchInterval: () => {
      if (!isPollingEnabled || !isVisible) {
        return false;
      }
      return pollingInterval;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const hasError = isError || Boolean(error);

  usePollingVisibilityRefresh(isPollingEnabled, () => {
    void refetch();
  }, isVisible);

  if (!selectedFeedSlug) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center text-gray-500">
        <p className="text-lg font-medium text-gray-400">No Feed Selected</p>
        <p className="text-sm mt-1">
          Choose a transit feed above to explore stops and arrival predictions.
        </p>
      </div>
    );
  }

  if (!selectedStop) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-8 text-center text-gray-500">
        <p className="text-lg font-medium text-gray-400">Select a Stop</p>
        <p className="text-sm mt-1">
          Pick any stop from the search list to view real-time arrivals and
          schedule predictions.
        </p>
      </div>
    );
  }

  const timezoneDisplay = selectedStop.timezone
    ? `${selectedStop.timezone} (Agency Time)`
    : "Local Time (Browser)";

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 sm:p-5 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-gray-800">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white tracking-tight">
              {selectedStop.name}
            </h2>
            {selectedStop.code && (
              <span className="text-xs font-mono text-gray-400 bg-gray-800 px-2 py-0.5 rounded">
                Stop #{selectedStop.code}
              </span>
            )}
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Times displayed in:{" "}
            <span className="text-gray-300 font-medium">{timezoneDisplay}</span>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Polling / Live Status Indicator */}
          <div className="flex items-center gap-1.5 text-xs">
            {!isVisible ? (
              <span
                role="status"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700 text-[11px]"
                title="Polling paused while window/tab is hidden"
              >
                ⏸ Paused
              </span>
            ) : hasError && arrivals ? (
              <span
                role="status"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800 text-[11px]"
                title="Live refresh encountered an error; displaying last successful data"
              >
                ⚠️ Stale
              </span>
            ) : (
              <span
                role="status"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800 text-[11px]"
                title={`Live polling active every ${Math.round(pollingInterval / 1000)} seconds`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                Live ({Math.round(pollingInterval / 1000)}s)
              </span>
            )}

            {dataUpdatedAt > 0 && (
              <span className="text-[11px] text-gray-500 hidden sm:inline">
                Updated {formatLastUpdated(dataUpdatedAt, selectedStop.timezone)}
              </span>
            )}
          </div>

          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            aria-label="Refresh arrivals"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-xs font-medium text-gray-200 rounded-md transition-colors cursor-pointer border border-gray-700"
          >
            <span className={isFetching ? "animate-spin" : ""}>🔄</span>
            <span>{isFetching ? "Refreshing..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Transient background refresh error warning (preserves last successful data) */}
      {hasError && arrivals && arrivals.length > 0 && (
        <div
          role="alert"
          className="bg-amber-950/80 border border-amber-800 text-amber-200 text-xs rounded-md p-3 flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <span>⚠️</span>
            <span>
              Live update failed ({error instanceof Error ? error.message : "Network error"}).
              Displaying predictions from {formatLastUpdated(dataUpdatedAt, selectedStop.timezone)}.
            </span>
          </div>
          <button
            type="button"
            onClick={() => void refetch()}
            disabled={isFetching}
            className="text-amber-100 underline hover:no-underline text-xs ml-2 cursor-pointer shrink-0 disabled:opacity-50"
          >
            Retry
          </button>
        </div>
      )}

      {/* Initial load error state (no data available) */}
      {hasError && (!arrivals || arrivals.length === 0) && (
        <div
          role="alert"
          className="bg-red-950/60 border border-red-800 text-red-300 text-sm rounded-md p-3 flex items-center justify-between"
        >
          <span>
            {error instanceof Error
              ? error.message
              : "Unable to load stop arrivals"}
          </span>
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-red-200 underline hover:text-white text-xs ml-2 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="py-12 text-center space-y-2 text-gray-400">
          <div className="inline-block animate-spin text-xl">⏳</div>
          <p className="text-sm">Calculating arrival predictions...</p>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && arrivals?.length === 0 && (
        <div className="py-12 text-center space-y-1 text-gray-400">
          <p className="text-base font-medium text-gray-300">
            No Upcoming Arrivals
          </p>
          <p className="text-xs text-gray-500">
            There are no active scheduled trips arriving at this stop in the
            immediate service window.
          </p>
        </div>
      )}

      {/* Arrivals list */}
      {!isLoading && arrivals && arrivals.length > 0 && (
        <div className="space-y-3" role="list" aria-label="Upcoming arrivals">
          {arrivals.map((arrival) => (
            <ArrivalCard
              key={`${arrival.trip_id}-${arrival.stop_sequence}`}
              arrival={arrival}
              timezone={selectedStop.timezone}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface ArrivalCardProps {
  arrival: StopArrivalPrediction;
  timezone?: string | null;
}

function ArrivalCard({ arrival, timezone }: ArrivalCardProps) {
  const delay = formatDelay(arrival.delay_seconds);
  const source = formatPredictionSource(arrival.prediction_source);
  const scheduledTime = formatTime(arrival.scheduled_arrival_time, timezone);
  const estimatedTime = formatTime(arrival.estimated_arrival_time, timezone);
  const telemetryAge = formatObservationAge(arrival.source_observation_time);

  return (
    <article
      className="bg-gray-950/70 border border-gray-800 rounded-lg p-3.5 hover:border-gray-700 transition-colors space-y-2.5"
      aria-label={`Arrival for ${arrival.route_short_name ?? arrival.route_id} towards ${arrival.trip_headsign ?? "destination"}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="font-bold text-sm bg-blue-600/30 text-blue-300 border border-blue-500/40 px-2.5 py-1 rounded">
            {arrival.route_short_name || arrival.route_id}
          </span>
          <div className="min-w-0">
            <h3 className="text-sm font-medium text-white truncate">
              {arrival.trip_headsign || "Scheduled Service"}
            </h3>
            <p className="text-[11px] text-gray-400 font-mono truncate">
              Trip: {arrival.trip_id}
              {arrival.vehicle_id && ` • Vehicle #${arrival.vehicle_id}`}
            </p>
          </div>
        </div>

        {/* Delay badge */}
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${delay.badgeClass}`}
          title={`Delay: ${arrival.delay_seconds}s`}
        >
          {delay.label}
        </span>
      </div>

      {/* Arrival times & source badge */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-900 text-xs">
        <div className="flex items-center gap-3">
          <div>
            <span className="text-gray-500 block text-[10px] uppercase tracking-wider">
              Estimated
            </span>
            <span className="text-base font-semibold text-white">
              {estimatedTime}
            </span>
          </div>

          <div className="text-gray-600">|</div>

          <div>
            <span className="text-gray-500 block text-[10px] uppercase tracking-wider">
              Scheduled
            </span>
            <span className="text-xs text-gray-400">{scheduledTime}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Prediction Source Badge */}
          <span
            className={`px-2 py-0.5 rounded text-[11px] font-medium ${source.badgeClass}`}
            title={source.description}
          >
            {source.label}
          </span>

          {/* Telemetry Age */}
          <span
            className="text-[11px] text-gray-500 hidden sm:inline"
            title={arrival.source_observation_time ?? "No telemetry"}
          >
            {telemetryAge}
          </span>
        </div>
      </div>
    </article>
  );
}
