import { useEffect, useRef, useState } from "react";

/**
 * Real-time transit client polling configuration and utilities.
 *
 * Interval: 30 seconds (default).
 * A conservative 30-second interval provides responsive real-time ETA updates
 * and live vehicle movement without creating excessive network traffic or
 * overburdening client devices and backend API services.
 */
export const DEFAULT_POLLING_INTERVAL_MS = 30_000;

/**
 * Retrieves the effective polling interval in milliseconds.
 * Configurable in code or via the optional VITE_POLLING_INTERVAL_SEC environment variable.
 */
export function getPollingIntervalMs(): number {
  if (
    typeof import.meta !== "undefined" &&
    import.meta.env &&
    import.meta.env.VITE_POLLING_INTERVAL_SEC
  ) {
    const parsed = parseInt(
      String(import.meta.env.VITE_POLLING_INTERVAL_SEC),
      10,
    );
    if (!isNaN(parsed) && parsed >= 10 && parsed <= 300) {
      return parsed * 1000;
    }
  }
  return DEFAULT_POLLING_INTERVAL_MS;
}

/**
 * Custom React hook that tracks document visibility (page active vs hidden).
 * Automatically cleans up its event listener on unmount.
 */
export function useDocumentVisibility(): boolean {
  const [isVisible, setIsVisible] = useState<boolean>(() => {
    if (typeof document !== "undefined") {
      return document.visibilityState !== "hidden";
    }
    return true;
  });

  useEffect(() => {
    if (typeof document === "undefined") return;

    const handleVisibilityChange = () => {
      setIsVisible(document.visibilityState !== "hidden");
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return isVisible;
}

/**
 * Custom hook that monitors document visibility changes when polling is enabled.
 * If the page transitions from hidden back to visible, it invokes the refetch
 * callback once to immediately synchronize transit data with the backend.
 *
 * @param enabled Whether polling/data fetching is currently active for this query
 * @param refetch Callback to execute an immediate data refresh
 * @returns boolean indicating whether the document is currently visible
 */
export function usePollingVisibilityRefresh(
  enabled: boolean,
  refetch: () => void,
  externalIsVisible?: boolean,
): boolean {
  const internalIsVisible = useDocumentVisibility();
  const isVisible =
    externalIsVisible !== undefined ? externalIsVisible : internalIsVisible;
  const wasHiddenRef = useRef<boolean>(false);

  useEffect(() => {
    if (!enabled) {
      wasHiddenRef.current = false;
      return;
    }

    if (!isVisible) {
      wasHiddenRef.current = true;
    } else if (wasHiddenRef.current) {
      wasHiddenRef.current = false;
      refetch();
    }
  }, [isVisible, enabled, refetch]);

  return isVisible;
}
