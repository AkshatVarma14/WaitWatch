import { useQuery } from "@tanstack/react-query";
import { fetchFeeds } from "../lib/api";
import { useAppStore } from "../stores/appStore";

export function FeedSelector() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const setSelectedFeedSlug = useAppStore((state) => state.setSelectedFeedSlug);

  const {
    data: feeds,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["feeds"],
    queryFn: fetchFeeds,
  });

  const activeFeed = feeds?.find((f) => f.slug === selectedFeedSlug);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <label
          htmlFor="feed-select"
          className="block text-sm font-medium text-gray-200"
        >
          Transit Feed / City
        </label>
        {isLoading && (
          <span className="text-xs text-blue-400 animate-pulse" role="status">
            Loading feeds...
          </span>
        )}
      </div>

      {isError && (
        <div
          role="alert"
          className="bg-red-950/60 border border-red-800 text-red-300 text-xs rounded p-2.5 flex items-center justify-between"
        >
          <span>{error instanceof Error ? error.message : "Failed to load feeds"}</span>
          <button
            type="button"
            onClick={() => void refetch()}
            className="text-red-200 underline hover:text-white text-xs ml-2 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      <select
        id="feed-select"
        value={selectedFeedSlug ?? ""}
        onChange={(e) => setSelectedFeedSlug(e.target.value || null)}
        disabled={isLoading || isError}
        aria-label="Select transit feed"
        className="w-full bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
      >
        <option value="">Select a transit feed...</option>
        {feeds?.map((feed) => (
          <option key={feed.slug} value={feed.slug}>
            {feed.city_name} ({feed.slug})
            {feed.is_live_tracking_enabled ? " — Live Tracking" : ""}
          </option>
        ))}
      </select>

      {activeFeed && (
        <div className="pt-2 border-t border-gray-800/80 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
            <span
              className={`w-2 h-2 rounded-full ${
                activeFeed.feed_status === "active"
                  ? "bg-emerald-400"
                  : "bg-amber-400"
              }`}
              aria-hidden="true"
            />
            Status: {activeFeed.feed_status}
          </span>

          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${
              activeFeed.is_live_tracking_enabled
                ? "bg-emerald-950/70 text-emerald-300 border-emerald-800"
                : "bg-gray-800 text-gray-400 border-gray-700"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                activeFeed.is_live_tracking_enabled
                  ? "bg-emerald-400 animate-pulse"
                  : "bg-gray-500"
              }`}
              aria-hidden="true"
            />
            {activeFeed.is_live_tracking_enabled
              ? "Live Tracking Active"
              : "Live Tracking Off"}
          </span>

          {activeFeed.last_realtime_poll_at && (
            <span className="text-gray-500 text-xs ml-auto">
              Updated:{" "}
              {new Date(activeFeed.last_realtime_poll_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
