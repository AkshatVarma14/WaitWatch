import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { fetchRouteMap } from "../lib/api";
import { formatLastUpdated, formatObservationAge } from "../lib/formatters";
import {
  getPollingIntervalMs,
  useDocumentVisibility,
  usePollingVisibilityRefresh,
} from "../lib/polling";
import { useAppStore } from "../stores/appStore";
import type { RouteMapStop } from "../types/transit";

const DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';

export function MapView() {
  const selectedFeedSlug = useAppStore((state) => state.selectedFeedSlug);
  const selectedRouteId = useAppStore((state) => state.selectedRouteId);
  const selectedStop = useAppStore((state) => state.selectedStop);
  const setSelectedStop = useAppStore((state) => state.setSelectedStop);
  const selectedVehicleId = useAppStore((state) => state.selectedVehicleId);
  const setSelectedVehicleId = useAppStore((state) => state.setSelectedVehicleId);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const layerGroupRef = useRef<L.LayerGroup | null>(null);
  const lastFittedRouteRef = useRef<string | null>(null);

  const tileUrl = import.meta.env.VITE_MAP_TILE_URL || DEFAULT_TILE_URL;
  const pollingInterval = getPollingIntervalMs();
  const isPollingEnabled = Boolean(selectedFeedSlug && selectedRouteId);
  const isVisible = useDocumentVisibility();

  const {
    data: routeMapData,
    dataUpdatedAt,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useQuery({
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

  const hasError = isError || Boolean(error);

  usePollingVisibilityRefresh(isPollingEnabled, () => {
    void refetch();
  }, isVisible);

  // 1. Initialize Leaflet map instance once
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) {
      return;
    }

    const map = L.map(mapContainerRef.current, {
      center: [20.0, 0.0],
      zoom: 2,
      attributionControl: true,
      zoomControl: true,
    });

    L.tileLayer(tileUrl, {
      attribution: TILE_ATTRIBUTION,
      maxZoom: 19,
    }).addTo(map);

    const layerGroup = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;
    layerGroupRef.current = layerGroup;

    // Invalidate size when window resizes
    const handleResize = () => {
      map.invalidateSize();
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      map.remove();
      mapInstanceRef.current = null;
      layerGroupRef.current = null;
    };
  }, [tileUrl]);

  // 2. Render route shapes, stops, and vehicles when routeMapData changes
  useEffect(() => {
    const map = mapInstanceRef.current;
    const layerGroup = layerGroupRef.current;
    if (!map || !layerGroup) {
      return;
    }

    layerGroup.clearLayers();

    if (!routeMapData) {
      return;
    }

    const boundsPoints: L.LatLngTuple[] = [];

    // 2a. Render true GTFS shape polylines (never fabricated from stops)
    if (routeMapData.shapes && routeMapData.shapes.length > 0) {
      for (const shape of routeMapData.shapes) {
        const polylinePoints: L.LatLngTuple[] = shape.points.map((p) => [
          p.latitude,
          p.longitude,
        ]);
        if (polylinePoints.length > 0) {
          boundsPoints.push(...polylinePoints);
          L.polyline(polylinePoints, {
            color: routeMapData.route_color || "#3b82f6",
            weight: 4,
            opacity: 0.85,
            lineJoin: "round",
          }).addTo(layerGroup);
        }
      }
    }

    // 2b. Render route stops
    if (routeMapData.stops) {
      for (const stop of routeMapData.stops) {
        boundsPoints.push([stop.latitude, stop.longitude]);
        const isSelected = selectedStop?.stop_id === stop.stop_id;

        const marker = L.circleMarker([stop.latitude, stop.longitude], {
          radius: isSelected ? 8 : 6,
          color: isSelected ? "#60a5fa" : "#ffffff",
          fillColor: isSelected ? "#2563eb" : "#1e293b",
          fillOpacity: 0.95,
          weight: isSelected ? 3 : 2,
        });

        marker.bindTooltip(
          `<div><strong>${stop.name}</strong>${stop.code ? ` (#${stop.code})` : ""}<br/><span style="font-size:11px;color:#94a3b8">Sequence ${stop.stop_sequence}</span></div>`,
          { direction: "top", offset: [0, -6] },
        );

        marker.on("click", () => {
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
          });
        });

        marker.addTo(layerGroup);
      }
    }

    // 2c. Render fresh vehicle markers with bearing rotation
    if (routeMapData.vehicles) {
      for (const veh of routeMapData.vehicles) {
        boundsPoints.push([veh.latitude, veh.longitude]);
        const isSelected = selectedVehicleId === veh.entity_id;
        const bearing = veh.bearing ?? 0;
        const obsAge = formatObservationAge(veh.observed_at);

        const vehicleHtml = `
          <div style="transform: rotate(${bearing}deg); width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; background: ${
            isSelected ? "#22c55e" : "#0284c7"
          }; border: 2px solid white; border-radius: 9999px; box-shadow: 0 2px 6px rgba(0,0,0,0.4); cursor: pointer;" title="Vehicle ${
            veh.vehicle_label || veh.vehicle_id || veh.entity_id
          }">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="white">
              <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
            </svg>
          </div>
        `;

        const icon = L.divIcon({
          html: vehicleHtml,
          className: "ww-vehicle-icon",
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });

        const marker = L.marker([veh.latitude, veh.longitude], { icon });

        marker.bindTooltip(
          `<div><strong>Vehicle ${veh.vehicle_label || veh.vehicle_id || veh.entity_id}</strong><br/>Speed: ${
            veh.speed ? `${Math.round(veh.speed * 3.6)} km/h` : "N/A"
          }<br/><span style="font-size:11px;color:#94a3b8">Heading: ${Math.round(bearing)}° • ${obsAge}</span></div>`,
          { direction: "top", offset: [0, -14] },
        );

        marker.on("click", () => {
          setSelectedVehicleId(veh.entity_id);
        });

        marker.addTo(layerGroup);
      }
    }

    // 2d. Fit bounds to all route elements on initial load or route change
    // Avoid re-fitting on background polling ticks to preserve user zoom/pan and tile stability
    if (
      boundsPoints.length > 0 &&
      lastFittedRouteRef.current !== selectedRouteId
    ) {
      lastFittedRouteRef.current = selectedRouteId;
      const bounds = L.latLngBounds(boundsPoints);
      map.fitBounds(bounds, {
        padding: [30, 30],
        maxZoom: 15,
      });
    }
  }, [
    routeMapData,
    selectedRouteId,
    selectedStop?.stop_id,
    selectedVehicleId,
    setSelectedStop,
    setSelectedVehicleId,
  ]);

  // Reset fitted route reference when route selection is cleared
  useEffect(() => {
    if (!selectedRouteId) {
      lastFittedRouteRef.current = null;
    }
  }, [selectedRouteId]);

  return (
    <div
      className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden flex flex-col relative"
      aria-label="Interactive Route Map"
    >
      {/* Map Header Status Bar */}
      <div className="px-4 py-2.5 bg-gray-950/80 border-b border-gray-800 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-200">Interactive Map</span>
          {routeMapData && (
            <span className="text-gray-400">
              • Route {routeMapData.route_short_name || routeMapData.route_id}
            </span>
          )}
        </div>

        {/* Status Indicators & Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Polling / Live Status */}
          {isPollingEnabled && (
            <div className="flex items-center gap-1.5 text-xs">
              {!isVisible ? (
                <span
                  role="status"
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700"
                  title="Polling paused while window/tab is hidden"
                >
                  ⏸ Paused
                </span>
              ) : hasError && routeMapData ? (
                <span
                  role="status"
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800"
                  title="Live refresh encountered an error; displaying last successful data"
                >
                  ⚠️ Stale
                </span>
              ) : (
                <span
                  role="status"
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800"
                  title={`Live polling active every ${Math.round(pollingInterval / 1000)} seconds`}
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  Live ({Math.round(pollingInterval / 1000)}s)
                </span>
              )}

              {dataUpdatedAt > 0 && (
                <span className="text-[11px] text-gray-500 hidden sm:inline">
                  Updated {formatLastUpdated(dataUpdatedAt)}
                </span>
              )}
            </div>
          )}

          {/* Shape Availability Disclosure */}
          {routeMapData && (
            <>
              {routeMapData.shapes.length > 0 ? (
                <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-emerald-950/70 text-emerald-300 border border-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  GTFS Shape Active ({routeMapData.shapes.length}{" "}
                  {routeMapData.shapes.length === 1 ? "track" : "tracks"})
                </span>
              ) : (
                <span
                  role="status"
                  className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-800"
                  title="GTFS shapes.txt was not included in this feed. Displaying available stop locations."
                >
                  ⚠️ Route shape unavailable — showing stops only
                </span>
              )}

              {routeMapData.vehicles.length > 0 && (
                <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-blue-950/70 text-blue-300 border border-blue-800">
                  🚌 {routeMapData.vehicles.length} Live{" "}
                  {routeMapData.vehicles.length === 1 ? "Vehicle" : "Vehicles"}
                </span>
              )}
            </>
          )}

          {/* Manual Refresh Button */}
          {selectedRouteId && (
            <button
              type="button"
              onClick={() => void refetch()}
              disabled={isFetching}
              aria-label="Refresh route map"
              className="inline-flex items-center gap-1 px-2 py-0.5 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-[11px] text-gray-200 rounded border border-gray-700 transition-colors cursor-pointer"
            >
              <span className={isFetching ? "animate-spin" : ""}>🔄</span>
              <span className="hidden sm:inline">
                {isFetching ? "Refreshing..." : "Refresh"}
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Map Canvas Container */}
      <div className="relative h-80 sm:h-96 md:h-[420px] w-full bg-gray-950">
        <div
          ref={mapContainerRef}
          data-testid="leaflet-map-container"
          className="h-full w-full z-0"
        />

        {/* Empty state when no route is selected */}
        {!selectedRouteId && (
          <div className="absolute inset-0 bg-gray-950/80 backdrop-blur-xs flex items-center justify-center p-6 text-center z-10 pointer-events-none">
            <div className="max-w-md space-y-2">
              <span className="text-3xl" role="img" aria-label="Map">
                🗺️
              </span>
              <p className="text-sm font-medium text-gray-300">
                Select a Transit Route
              </p>
              <p className="text-xs text-gray-500">
                Choose a route above to visualize its true GTFS shape polyline,
                ordered passenger stops, and live vehicle positions.
              </p>
            </div>
          </div>
        )}

        {/* Loading Overlay (initial query only) */}
        {isLoading && (
          <div
            role="status"
            className="absolute inset-0 bg-gray-950/70 backdrop-blur-xs flex items-center justify-center p-6 z-10"
          >
            <div className="flex items-center gap-2 text-sm text-blue-400">
              <span className="animate-spin text-lg">⏳</span>
              <span>Loading route geometry & vehicles...</span>
            </div>
          </div>
        )}

        {/* Transient Refresh Error Warning (preserves existing map data) */}
        {hasError && routeMapData && (
          <div
            role="alert"
            className="absolute inset-x-4 top-4 bg-amber-950/90 border border-amber-800 text-amber-200 text-xs rounded-md p-2.5 flex items-center justify-between z-10"
          >
            <div className="flex items-center gap-2">
              <span>⚠️</span>
              <span>
                Live vehicle refresh failed ({error instanceof Error ? error.message : "Network error"}).
                Displaying data from {formatLastUpdated(dataUpdatedAt)}.
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

        {/* Initial Load Error Overlay (when no data exists) */}
        {hasError && !routeMapData && (
          <div
            role="alert"
            className="absolute inset-x-4 top-4 bg-red-950/90 border border-red-800 text-red-200 text-xs rounded-md p-3 flex items-center justify-between z-10"
          >
            <span>
              {error instanceof Error
                ? error.message
                : "Failed to load route map data"}
            </span>
            <button
              type="button"
              onClick={() => void refetch()}
              className="text-white underline hover:no-underline ml-2 cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}
      </div>

      {/* Map Footer: Attribution & Provider Policy Note */}
      <div className="px-4 py-2 bg-gray-950 border-t border-gray-800 flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-500">
        <span>
          Tiles: &copy;{" "}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noopener noreferrer"
            className="text-gray-400 underline hover:text-white"
          >
            OpenStreetMap
          </a>{" "}
          contributors (Demo standard tiles)
        </span>
        <span className="hidden sm:inline text-gray-600">
          Configurable via <code>VITE_MAP_TILE_URL</code>
        </span>
      </div>
    </div>
  );
}

export interface MapStopListProps {
  stops: RouteMapStop[];
  selectedStopId: string | null;
  onSelectStop: (stop: RouteMapStop) => void;
}
