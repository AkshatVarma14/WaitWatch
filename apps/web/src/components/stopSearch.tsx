import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchStops } from "../lib/api";
import { useAppStore } from "../stores/appStore";
import type { StopSummary } from "../types/transit";

export function StopSearch() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const selectedStop = useAppStore((state) => state.selectedStop);
  const setSelectedStop = useAppStore((state) => state.setSelectedStop);

  const [searchTerm, setSearchTerm] = useState("");

  const {
    data: stopResponse,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["stops", selectedFeedSlug, searchTerm],
    queryFn: () => fetchStops(selectedFeedSlug!, searchTerm),
    enabled: Boolean(selectedFeedSlug),
  });

  const stops = stopResponse?.data ?? [];

  if (!selectedFeedSlug) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center text-gray-500 text-sm">
        Select a transit feed above to search stops.
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <label
          htmlFor="stop-search-input"
          className="block text-sm font-medium text-gray-200"
        >
          Find a Stop
        </label>
        {isFetching && (
          <span className="text-xs text-blue-400 animate-pulse" role="status">
            Searching...
          </span>
        )}
      </div>

      <div className="relative">
        <input
          id="stop-search-input"
          type="search"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search by stop name, code, or ID..."
          aria-label="Search stops"
          className="w-full bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {searchTerm && (
          <button
            type="button"
            onClick={() => setSearchTerm("")}
            aria-label="Clear stop search"
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white text-xs px-1 cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>

      {isError && (
        <div
          role="alert"
          className="bg-red-950/60 border border-red-800 text-red-300 text-xs rounded p-2.5 flex items-center justify-between"
        >
          <span>
            {error instanceof Error ? error.message : "Failed to load stops"}
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

      {/* Stop list */}
      <div
        className="max-h-80 overflow-y-auto space-y-1.5 pr-1 scrollbar-thin"
        role="region"
        aria-label="Stop search results"
      >
        {isLoading && (
          <div className="py-6 text-center text-gray-500 text-sm">
            Loading stops...
          </div>
        )}

        {!isLoading && stops.length === 0 && (
          <div className="py-6 text-center text-gray-500 text-sm">
            {searchTerm.trim()
              ? `No stops found matching "${searchTerm}".`
              : "No stops found in this feed."}
          </div>
        )}

        {stops.map((stop) => {
          const isSelected = selectedStop?.stop_id === stop.stop_id;
          return (
            <StopItem
              key={stop.stop_id}
              stop={stop}
              isSelected={isSelected}
              onSelect={() => setSelectedStop(stop)}
            />
          );
        })}
      </div>

      {stopResponse && stopResponse.pagination.total > stops.length && (
        <p className="text-xs text-gray-500 text-center pt-1">
          Showing {stops.length} of {stopResponse.pagination.total} stops. Refine
          search for more.
        </p>
      )}
    </div>
  );
}

interface StopItemProps {
  stop: StopSummary;
  isSelected: boolean;
  onSelect: () => void;
}

function StopItem({ stop, isSelected, onSelect }: StopItemProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={isSelected}
      className={`w-full text-left p-2.5 rounded-md border transition-colors cursor-pointer flex items-start justify-between gap-2 ${
        isSelected
          ? "bg-blue-950/60 border-blue-500/80 text-white"
          : "bg-gray-950/60 border-gray-800 hover:border-gray-700 text-gray-300 hover:text-white"
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{stop.name}</span>
          {stop.code && (
            <span className="text-xs font-mono text-gray-400 bg-gray-800 px-1.5 py-0.5 rounded">
              #{stop.code}
            </span>
          )}
        </div>
        {stop.description && (
          <p className="text-xs text-gray-400 truncate mt-0.5">
            {stop.description}
          </p>
        )}
        <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-500">
          <span>ID: {stop.stop_id}</span>
          {stop.wheelchair_boarding === 1 && (
            <span
              className="text-blue-400"
              title="Wheelchair accessible"
              aria-label="Wheelchair accessible"
            >
              ♿ Accessible
            </span>
          )}
        </div>
      </div>

      {isSelected && (
        <span className="text-blue-400 text-xs font-medium shrink-0 pt-0.5">
          Selected ✓
        </span>
      )}
    </button>
  );
}
