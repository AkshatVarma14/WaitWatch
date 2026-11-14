import { useQuery } from "@tanstack/react-query";
import { fetchRoutes } from "../lib/api";
import { useAppStore } from "../stores/appStore";

export function RouteSelector() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const selectedRouteId = useAppStore((state) => state.selectedRouteId);
  const setSelectedRouteId = useAppStore((state) => state.setSelectedRouteId);

  const {
    data: routeResponse,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["routes", selectedFeedSlug],
    queryFn: () => fetchRoutes(selectedFeedSlug!),
    enabled: Boolean(selectedFeedSlug),
  });

  const routes = routeResponse?.data ?? [];
  const activeRoute = routes.find((r) => r.route_id === selectedRouteId);

  if (!selectedFeedSlug) {
    return null;
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <label
          htmlFor="route-select"
          className="block text-sm font-medium text-gray-200"
        >
          Select Transit Route
        </label>
        {isLoading && (
          <span className="text-xs text-blue-400 animate-pulse" role="status">
            Loading routes...
          </span>
        )}
      </div>

      {isError && (
        <div
          role="alert"
          className="bg-red-950/60 border border-red-800 text-red-300 text-xs rounded p-2.5 flex items-center justify-between"
        >
          <span>
            {error instanceof Error ? error.message : "Failed to load routes"}
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

      <select
        id="route-select"
        value={selectedRouteId ?? ""}
        onChange={(e) => setSelectedRouteId(e.target.value || null)}
        disabled={isLoading || isError}
        aria-label="Select transit route"
        className="w-full bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
      >
        <option value="">Select a route to view on map...</option>
        {routes.map((route) => (
          <option key={route.route_id} value={route.route_id}>
            {route.short_name ? `${route.short_name} — ` : ""}
            {route.long_name || route.route_id}
          </option>
        ))}
      </select>

      {!isLoading && !isError && routes.length === 0 && (
        <p role="status" className="text-xs text-amber-300">
          Scheduled routes are not currently available for this feed. Live
          vehicle positions remain visible on the map.
        </p>
      )}

      {activeRoute && (
        <div className="pt-2 border-t border-gray-800 flex items-center gap-2 text-xs">
          <span
            className="w-3 h-3 rounded-full shrink-0 border border-white/20"
            style={{
              backgroundColor: activeRoute.route_color || "#3b82f6",
            }}
            aria-hidden="true"
          />
          <span className="font-medium text-gray-200 truncate">
            {activeRoute.short_name || activeRoute.route_id}
            {activeRoute.long_name ? ` • ${activeRoute.long_name}` : ""}
          </span>
          {activeRoute.description && (
            <span className="text-gray-500 truncate hidden sm:inline ml-auto">
              {activeRoute.description}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
