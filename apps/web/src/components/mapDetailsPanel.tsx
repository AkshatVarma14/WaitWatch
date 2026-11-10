import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRouteMap } from "../lib/api";
import { formatObservationAge } from "../lib/formatters";
import {
  getPollingIntervalMs,
  useDocumentVisibility,
} from "../lib/polling";
import { useAppStore } from "../stores/appStore";

export function MapDetailsPanel() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const selectedRouteId = useAppStore((state) => state.selectedRouteId);
  const selectedStop = useAppStore((state) => state.selectedStop);
  const setSelectedStop = useAppStore((state) => state.setSelectedStop);
  const selectedVehicleId = useAppStore((state) => state.selectedVehicleId);
  const setSelectedVehicleId = useAppStore((state) => state.setSelectedVehicleId);

  const [activeTab, setActiveTab] = useState<"stops" | "vehicles">("stops");

  const pollingInterval = getPollingIntervalMs();
  const isPollingEnabled = Boolean(selectedFeedSlug && selectedRouteId);
  const isVisible = useDocumentVisibility();

  const { data: routeMapData } = useQuery({
    queryKey: ["routeMap", selectedFeedSlug, selectedRouteId],
    queryFn: () => fetchRouteMap(selectedFeedSlug!, selectedRouteId!),
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

  if (!selectedRouteId || !routeMapData) {
    return null;
  }

  const stops = routeMapData.stops || [];
  const vehicles = routeMapData.vehicles || [];

  const activeVehicle = vehicles.find((v) => v.entity_id === selectedVehicleId);

  return (
    <div
      className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-3"
      aria-label="Route details and map navigator"
    >
      {/* Tabs */}
      <div className="flex items-center justify-between border-b border-gray-800 pb-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("stops")}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer ${
              activeTab === "stops"
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
          >
            Stops ({stops.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("vehicles")}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer ${
              activeTab === "vehicles"
                ? "bg-blue-600 text-white"
                : "bg-gray-800 text-gray-400 hover:text-white"
            }`}
          >
            Live Vehicles ({vehicles.length})
          </button>
        </div>

        {selectedVehicleId && (
          <button
            type="button"
            onClick={() => setSelectedVehicleId(null)}
            className="text-[11px] text-gray-400 hover:text-white underline cursor-pointer"
          >
            Clear selection
          </button>
        )}
      </div>

      {/* Selected Vehicle Card */}
      {activeVehicle && (
        <div className="bg-blue-950/40 border border-blue-800/80 rounded-md p-3 text-xs space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-blue-300">
              Vehicle #{activeVehicle.vehicle_label || activeVehicle.vehicle_id || activeVehicle.entity_id}
            </span>
            <span className="text-gray-400">
              {formatObservationAge(activeVehicle.observed_at)}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[11px] text-gray-300">
            <div>
              <span className="text-gray-500">Speed: </span>
              {activeVehicle.speed
                ? `${Math.round(activeVehicle.speed * 3.6)} km/h`
                : "Stationary / N/A"}
            </div>
            <div>
              <span className="text-gray-500">Heading: </span>
              {activeVehicle.bearing != null
                ? `${Math.round(activeVehicle.bearing)}°`
                : "N/A"}
            </div>
            <div>
              <span className="text-gray-500">Coordinates: </span>
              {activeVehicle.latitude.toFixed(4)}, {activeVehicle.longitude.toFixed(4)}
            </div>
            <div>
              <span className="text-gray-500">Status: </span>
              {activeVehicle.current_status === 1
                ? "Stopped at station"
                : activeVehicle.current_status === 2
                ? "In transit"
                : "Incoming"}
            </div>
          </div>
        </div>
      )}

      {/* Tab: Stops List */}
      {activeTab === "stops" && (
        <div className="max-h-60 overflow-y-auto space-y-1 pr-1 scrollbar-thin">
          {stops.length === 0 ? (
            <p className="text-xs text-gray-500 py-3 text-center">
              No stops associated with this route.
            </p>
          ) : (
            stops.map((stop) => {
              const isSelected = selectedStop?.stop_id === stop.stop_id;
              return (
                <button
                  key={stop.stop_id}
                  type="button"
                  onClick={() =>
                    setSelectedStop({
                      stop_id: stop.stop_id,
                      code: stop.code,
                      name: stop.name,
                      description: null,
                      latitude: stop.latitude,
                      longitude: stop.longitude,
                      parent_station_id: null,
                      location_type: 0,
                      wheelchair_boarding: stop.wheelchair_boarding,
                      platform_code: null,
                      timezone: null,
                    })
                  }
                  aria-pressed={isSelected}
                  className={`w-full text-left p-2 rounded text-xs flex items-center justify-between gap-2 border transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-blue-950/80 border-blue-500 text-white"
                      : "bg-gray-950 border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white"
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="font-mono text-[10px] text-gray-500 w-5 shrink-0">
                      {stop.stop_sequence}
                    </span>
                    <span className="truncate">{stop.name}</span>
                    {stop.code && (
                      <span className="text-[10px] font-mono text-gray-500">
                        #{stop.code}
                      </span>
                    )}
                  </div>
                  {isSelected && (
                    <span className="text-[11px] text-blue-400 shrink-0">
                      Active ✓
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      )}

      {/* Tab: Vehicles List */}
      {activeTab === "vehicles" && (
        <div className="max-h-60 overflow-y-auto space-y-1 pr-1 scrollbar-thin">
          {vehicles.length === 0 ? (
            <p className="text-xs text-gray-500 py-3 text-center">
              No live vehicles currently reporting on this route.
            </p>
          ) : (
            vehicles.map((veh) => {
              const isSelected = selectedVehicleId === veh.entity_id;
              const obsAge = formatObservationAge(veh.observed_at);
              return (
                <button
                  key={veh.entity_id}
                  type="button"
                  onClick={() => setSelectedVehicleId(veh.entity_id)}
                  aria-pressed={isSelected}
                  className={`w-full text-left p-2 rounded text-xs flex items-center justify-between gap-2 border transition-colors cursor-pointer ${
                    isSelected
                      ? "bg-blue-950/80 border-blue-500 text-white"
                      : "bg-gray-950 border-gray-800 text-gray-300 hover:border-gray-700 hover:text-white"
                  }`}
                >
                  <div className="truncate">
                    <span className="font-medium text-white">
                      Vehicle #{veh.vehicle_label || veh.vehicle_id || veh.entity_id}
                    </span>
                    <span className="text-[11px] text-gray-500 ml-2">
                      {veh.speed ? `${Math.round(veh.speed * 3.6)} km/h` : "Stationary"}
                    </span>
                  </div>
                  <span className="text-[11px] text-gray-400 shrink-0">
                    {obsAge}
                  </span>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
