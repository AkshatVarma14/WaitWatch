import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MockInstance } from "vitest";
import {
  DEFAULT_POLLING_INTERVAL_MS,
  getPollingIntervalMs,
  useDocumentVisibility,
  usePollingVisibilityRefresh,
} from "../lib/polling";

describe("polling utilities", () => {
  describe("getPollingIntervalMs", () => {
    it("returns default 30000ms (30s) interval", () => {
      expect(DEFAULT_POLLING_INTERVAL_MS).toBe(30_000);
      expect(getPollingIntervalMs()).toBe(30_000);
    });
  });

  describe("useDocumentVisibility", () => {
    let visibilityStateSpy: MockInstance;

    beforeEach(() => {
      const state = "visible";
      visibilityStateSpy = vi
        .spyOn(document, "visibilityState", "get")
        .mockImplementation(() => state as DocumentVisibilityState);
    });

    afterEach(() => {
      visibilityStateSpy.mockRestore();
    });

    it("returns true when visibilityState is 'visible'", () => {
      const { result } = renderHook(() => useDocumentVisibility());
      expect(result.current).toBe(true);
    });

    it("updates state when visibilitychange event fires", () => {
      const { result } = renderHook(() => useDocumentVisibility());
      expect(result.current).toBe(true);

      // Simulate document becoming hidden
      visibilityStateSpy.mockReturnValue("hidden");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(result.current).toBe(false);

      // Simulate document becoming visible again
      visibilityStateSpy.mockReturnValue("visible");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(result.current).toBe(true);
    });

    it("cleans up visibilitychange listener on unmount", () => {
      const removeEventListenerSpy = vi.spyOn(
        document,
        "removeEventListener",
      );
      const { unmount } = renderHook(() => useDocumentVisibility());
      unmount();
      expect(removeEventListenerSpy).toHaveBeenCalledWith(
        "visibilitychange",
        expect.any(Function),
      );
      removeEventListenerSpy.mockRestore();
    });
  });

  describe("usePollingVisibilityRefresh", () => {
    let visibilityStateSpy: MockInstance;

    beforeEach(() => {
      visibilityStateSpy = vi
        .spyOn(document, "visibilityState", "get")
        .mockReturnValue("visible");
    });

    afterEach(() => {
      visibilityStateSpy.mockRestore();
    });

    it("calls refetch when page transitions from hidden to visible", () => {
      const refetch = vi.fn();
      const { rerender } = renderHook(
        ({ enabled }) => usePollingVisibilityRefresh(enabled, refetch),
        { initialProps: { enabled: true } },
      );

      // Document hidden
      visibilityStateSpy.mockReturnValue("hidden");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      rerender({ enabled: true });
      expect(refetch).not.toHaveBeenCalled();

      // Document visible again -> triggers refetch once
      visibilityStateSpy.mockReturnValue("visible");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      rerender({ enabled: true });
      expect(refetch).toHaveBeenCalledTimes(1);
    });

    it("does not call refetch on visibility return if polling is disabled", () => {
      const refetch = vi.fn();
      const { rerender } = renderHook(
        ({ enabled }) => usePollingVisibilityRefresh(enabled, refetch),
        { initialProps: { enabled: false } },
      );

      visibilityStateSpy.mockReturnValue("hidden");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      rerender({ enabled: false });

      visibilityStateSpy.mockReturnValue("visible");
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      rerender({ enabled: false });

      expect(refetch).not.toHaveBeenCalled();
    });
  });
});
