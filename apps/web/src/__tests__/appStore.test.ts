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
    expect(state.selectedStop).toBeNull();
    expect(state.selectedCity).toBeNull();
  });

  it("can set selectedFeedSlug and updates selectedCity alias", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBe("delhi-metro");
    expect(state.selectedCity).toBe("delhi-metro");
  });

  it("can set and retrieve selectedStop", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedStop(mockStop);

    const state = useAppStore.getState();
    expect(state.selectedStop).toEqual(mockStop);
    expect(state.selectedStop?.stop_id).toBe("stop-101");
  });

  it("enforces feed isolation: switching feeds resets selectedStop", () => {
    // 1. Set feed and stop in Feed A
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedStop(mockStop);
    expect(useAppStore.getState().selectedStop).not.toBeNull();

    // 2. Switch to Feed B
    useAppStore.getState().setSelectedFeedSlug("mumbai-suburban");

    // 3. Verify selectedStop was wiped out to prevent cross-feed contamination
    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBe("mumbai-suburban");
    expect(state.selectedStop).toBeNull();
  });

  it("enforces feed isolation via backward-compatible setSelectedCity", () => {
    useAppStore.getState().setSelectedCity("delhi");
    useAppStore.getState().setSelectedStop(mockStop);
    expect(useAppStore.getState().selectedStop).not.toBeNull();

    useAppStore.getState().setSelectedCity("bangalore");
    expect(useAppStore.getState().selectedCity).toBe("bangalore");
    expect(useAppStore.getState().selectedFeedSlug).toBe("bangalore");
    expect(useAppStore.getState().selectedStop).toBeNull();
  });

  it("resets all state on reset()", () => {
    useAppStore.getState().setSelectedFeedSlug("delhi-metro");
    useAppStore.getState().setSelectedStop(mockStop);

    useAppStore.getState().reset();

    const state = useAppStore.getState();
    expect(state.selectedFeedSlug).toBeNull();
    expect(state.selectedStop).toBeNull();
    expect(state.selectedCity).toBeNull();
  });
});
