import { create } from "zustand";
import type { StopSummary } from "../types/transit";

export interface AppState {
  /** Currently selected transit feed slug */
  selectedFeedSlug: string | null;

  /** Currently selected route identifier */
  selectedRouteId: string | null;

  /** Currently selected transit stop */
  selectedStop: StopSummary | null;

  /** Currently selected realtime vehicle entity/vehicle ID on the map */
  selectedVehicleId: string | null;

  /** Backwards-compatible alias for selected city / feed slug */
  selectedCity: string | null;

  /** Update selected feed slug (enforces feed isolation by resetting route, stop, and vehicle) */
  setSelectedFeedSlug: (slug: string | null) => void;

  /** Update selected route */
  setSelectedRouteId: (routeId: string | null) => void;

  /** Select a specific stop within the active feed/route */
  setSelectedStop: (stop: StopSummary | null) => void;

  /** Select a vehicle on the map to inspect */
  setSelectedVehicleId: (vehicleId: string | null) => void;

  /** Backwards-compatible alias for setSelectedFeedSlug */
  setSelectedCity: (city: string | null) => void;

  /** Reset all selections */
  reset: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedFeedSlug: null,
  selectedRouteId: null,
  selectedStop: null,
  selectedVehicleId: null,
  selectedCity: null,

  setSelectedFeedSlug: (slug) =>
    set({
      selectedFeedSlug: slug,
      selectedCity: slug,
      // Feed isolation: changing feed clears previously selected route, stop, and vehicle
      selectedRouteId: null,
      selectedStop: null,
      selectedVehicleId: null,
    }),

  setSelectedRouteId: (routeId) =>
    set({
      selectedRouteId: routeId,
      selectedVehicleId: null,
    }),

  setSelectedStop: (stop) =>
    set({
      selectedStop: stop,
    }),

  setSelectedVehicleId: (vehicleId) =>
    set({
      selectedVehicleId: vehicleId,
    }),

  setSelectedCity: (city) =>
    set({
      selectedCity: city,
      selectedFeedSlug: city,
      selectedRouteId: null,
      selectedStop: null,
      selectedVehicleId: null,
    }),

  reset: () =>
    set({
      selectedFeedSlug: null,
      selectedRouteId: null,
      selectedStop: null,
      selectedVehicleId: null,
      selectedCity: null,
    }),
}));
