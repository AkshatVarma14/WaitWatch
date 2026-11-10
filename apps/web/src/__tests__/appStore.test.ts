import { describe, it, expect } from "vitest";
import { useAppStore } from "../stores/appStore";

describe("appStore", () => {
  it("initializes with null selectedCity", () => {
    const state = useAppStore.getState();
    expect(state.selectedCity).toBeNull();
  });

  it("can set selectedCity", () => {
    useAppStore.getState().setSelectedCity("delhi");
    expect(useAppStore.getState().selectedCity).toBe("delhi");
    // Reset
    useAppStore.getState().setSelectedCity(null);
  });
});
