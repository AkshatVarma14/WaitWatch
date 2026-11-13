import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getFeedWebSocketUrl } from "./api";
import { useDocumentVisibility } from "./polling";
import { useAppStore } from "../stores/appStore";
import type { FeedUpdateEvent } from "../types/transit";

const HEARTBEAT_INTERVAL_MS = 30_000;
const INITIAL_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

/**
 * React hook that manages a persistent, feed-scoped WebSocket connection
 * for real-time transit update notifications.
 *
 * Responsibilities:
 * - Connects to `/api/v1/feeds/{feedSlug}/ws` when a feed is selected and tab is visible.
 * - Emits periodic ping heartbeats to maintain socket health.
 * - On receiving a feed_update event, invalidates matching TanStack Query caches
 *   (`routeMap` and `arrivals` for this feed), triggering instant UI refresh.
 * - Gracefully suspends connection when the browser tab is hidden to save battery/bandwidth.
 * - Automatically falls back to steady-state REST polling on disconnect or error.
 * - Reconnects with exponential backoff and refetches immediately upon reconnect.
 */
export function useFeedLiveUpdates(feedSlug: string | null) {
  const queryClient = useQueryClient();
  const isVisible = useDocumentVisibility();
  const setLiveStatus = useAppStore((state) => state.setLiveStatus);
  const setLastLiveUpdateAt = useAppStore((state) => state.setLastLiveUpdateAt);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(
    null,
  );
  const retryCountRef = useRef<number>(0);
  const isCleanClosureRef = useRef<boolean>(false);
  const lastProcessedEventRef = useRef<string | null>(null);

  useEffect(() => {
    // If no WebSocket support in environment, enter fallback mode
    if (typeof WebSocket === "undefined") {
      setLiveStatus("fallback");
      return;
    }

    // If no feed is selected, reset status to disconnected and clean up
    if (!feedSlug) {
      lastProcessedEventRef.current = null;
      setLiveStatus("disconnected");
      if (socketRef.current) {
        isCleanClosureRef.current = true;
        socketRef.current.close(1000, "No feed selected");
        socketRef.current = null;
      }
      return;
    }

    // If tab is hidden, pause live updates
    if (!isVisible) {
      setLiveStatus("paused");
      if (socketRef.current) {
        isCleanClosureRef.current = true;
        socketRef.current.close(1000, "Window hidden");
        socketRef.current = null;
      }
      return;
    }

    let isMounted = true;

    function cleanupTimers() {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = null;
      }
    }

    function scheduleReconnect() {
      cleanupTimers();
      if (!isMounted || !feedSlug || !isVisible) return;

      const delay = Math.min(
        INITIAL_RECONNECT_DELAY_MS * Math.pow(2, retryCountRef.current),
        MAX_RECONNECT_DELAY_MS,
      );
      retryCountRef.current += 1;

      reconnectTimeoutRef.current = setTimeout(() => {
        connect();
      }, delay);
    }

    function connect() {
      cleanupTimers();

      if (!isMounted || !feedSlug || !isVisible) {
        return;
      }

      setLiveStatus("connecting");
      isCleanClosureRef.current = false;

      let ws: WebSocket;
      try {
        const url = getFeedWebSocketUrl(feedSlug);
        ws = new WebSocket(url);
      } catch {
        setLiveStatus("fallback");
        scheduleReconnect();
        return;
      }

      socketRef.current = ws;

      ws.onopen = () => {
        if (!isMounted || socketRef.current !== ws) return;
        setLiveStatus("connected");
        const hadRetried = retryCountRef.current > 0;
        retryCountRef.current = 0;

        // Catch up on missed data if reconnecting
        if (hadRetried) {
          void queryClient.invalidateQueries({
            queryKey: ["routeMap", feedSlug],
          });
          void queryClient.invalidateQueries({
            queryKey: ["feedVehicles", feedSlug],
          });
          void queryClient.invalidateQueries({
            queryKey: ["arrivals", feedSlug],
          });
        }

        // Setup periodic ping heartbeat
        heartbeatIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send("ping");
            } catch {
              // Disconnect will be handled by onerror / onclose
            }
          }
        }, HEARTBEAT_INTERVAL_MS);
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!isMounted || socketRef.current !== ws) return;

        if (event.data === "pong" || event.data === "ping") {
          return;
        }

        try {
          const parsed = JSON.parse(event.data);
          if (parsed.type === "pong" || parsed.type === "connected") {
            return;
          }

          if (parsed.type === "feed_update") {
            const feedUpdate = parsed as FeedUpdateEvent;
            const eventKey =
              feedUpdate.event_id ||
              `${feedUpdate.feed_slug}:${feedUpdate.update_type}:${feedUpdate.timestamp}`;
            if (lastProcessedEventRef.current === eventKey) {
              return;
            }
            lastProcessedEventRef.current = eventKey;

            if (feedUpdate.feed_slug === feedSlug) {
              setLastLiveUpdateAt(feedUpdate.timestamp);
              void queryClient.invalidateQueries({
                queryKey: ["routeMap", feedSlug],
              });
              void queryClient.invalidateQueries({
                queryKey: ["feedVehicles", feedSlug],
              });
              void queryClient.invalidateQueries({
                queryKey: ["arrivals", feedSlug],
              });
            }
          }
        } catch {
          // Ignore unparseable frames
        }
      };

      ws.onerror = () => {
        if (!isMounted || socketRef.current !== ws) return;
        setLiveStatus("fallback");
      };

      ws.onclose = (event: CloseEvent) => {
        cleanupTimers();
        if (!isMounted) return;

        // Policy violation (unknown feed) -> do not loop retries
        if (event.code === 1008) {
          setLiveStatus("disconnected");
          return;
        }

        if (!isCleanClosureRef.current) {
          setLiveStatus("fallback");
          scheduleReconnect();
        } else {
          setLiveStatus("disconnected");
        }
      };
    }

    connect();

    return () => {
      isMounted = false;
      cleanupTimers();
      if (socketRef.current) {
        isCleanClosureRef.current = true;
        socketRef.current.close(1000, "Hook unmounted or feed changed");
        socketRef.current = null;
      }
    };
  }, [feedSlug, isVisible, queryClient, setLiveStatus, setLastLiveUpdateAt]);
}
