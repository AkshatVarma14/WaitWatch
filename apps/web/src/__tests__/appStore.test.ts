import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "../stores/appStore";
import type { StopSummary } from "../types/transit";

const mockStop: StopSummary = {
  stop_id: "stop-101",
  code: "101",
  name: "Central Station",
  description: "Platform A",
  latitude: 28.6139,
  longitude: 77.209,
  parent_station_id: null,
  location_type: 0,
  wheelchair_boarding: 1,
  platform_code: "1",
  timezone: "Asia/Kolkata",
};

describe("appStore", () => {
  beforeEach(() => {
    useAppStore.getState().reset();
  });

  it("initializes with null state", () => {
    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBeNull();
    expect(state.selectedRouteId).toBeNull();
    expect(state.selectedStop).toBeNull();
    expect(state.selectedVehicleId).toBeNull();
    expect(state.selectedCity).toBeNull();
  });

  it("can set selectedFeedSlug and updates selectedCity alias", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBe("delhi-metro");
    expect(state.selectedCity).toBe("delhi-metro");
  });

  it("can set and retrieve selectedRouteId", () => {
    useAppStore.getState().setSelectedRouteId("route-blue");
    expect(useAppStore.getState().selectedRouteId).toBe("route-blue");
  });

  it("can set and retrieve selectedStop", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedStop(mockStop);

    const state = useAppStore.getState();
    expect(state.selectedStop).toEqual(mockStop);
    expect(state.selectedStop?.stop_id).toBe("stop-101");
  });

  it("can set and retrieve selectedVehicleId", () => {
    useAppStore.getState().setSelectedVehicleId("veh-401");
    expect(useAppStore.getState().selectedVehicleId).toBe("veh-401");
  });

  it("changing route resets selectedVehicleId", () => {
    useAppStore.getState().setSelectedRouteId("route-blue");
    useAppStore.getState().setSelectedVehicleId("veh-401");
    expect(useAppStore.getState().selectedVehicleId).toBe("veh-401");

    useAppStore.getState().setSelectedRouteId("route-red");
    expect(useAppStore.getState().selectedRouteId).toBe("route-red");
    expect(useAppStore.getState().selectedVehicleId).toBeNull();
  });

  it("enforces feed isolation: switching feeds resets route, stop, and vehicle", () => {
    // 1. Set feed, route, stop, and vehicle in Feed A
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedRouteId("blue-line");
    useAppStore.getState().setSelectedStop(mockStop);
    useAppStore.getState().setSelectedVehicleId("bus-01");

    // 2. Switch to Feed B
    useAppStore.getState().setSelectedFeedSlug("mumbai-suburban");

    // 3. Verify route, stop, and vehicle are reset to prevent cross-feed contamination
    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBe("mumbai-suburban");
    expect(state.selectedRouteId).toBeNull();
    expect(state.selectedStop).toBeNull();
    expect(state.selectedVehicleId).toBeNull();
  });

  it("enforces feed isolation via backward-compatible setSelectedCity", () => {
    useAppStore.getState().setSelectedCity("delhi");
    useAppStore.getState().setSelectedRouteId("blue-line");
    useAppStore.getState().setSelectedStop(mockStop);
    useAppStore.getState().setSelectedVehicleId("bus-01");

    useAppStore.getState().setSelectedCity("bangalore");
    const state = useAppStore.getState();
    expect(state.selectedCity).toBe("bangalore");
    expect(state.selectedFeedSlug).toBe("bangalore");
    expect(state.selectedRouteId).toBeNull();
    expect(state.selectedStop).toBeNull();
    expect(state.selectedVehicleId).toBeNull();
  });

  it("resets all state on reset()", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedRouteId("blue-line");
    useAppStore.getState().setSelectedStop(mockStop);
    useAppStore.getState().setSelectedVehicleId("bus-01");

    useAppStore.getState().reset();

    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBeNull();
    expect(state.selectedRouteId).toBeNull();
    expect(state.selectedStop).toBeNull();
    expect(state.selectedVehicleId).toBeNull();
    expect(state.selectedCity).toBeNull();
  });
});
