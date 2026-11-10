import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useFeedLiveUpdates } from "../lib/useFeedLiveUpdates";
import { useAppStore } from "../stores/appStore";

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];
  url: string;
  readyState: number = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code: number = 1000, reason: string = "") {
    this.readyState = 3; // CLOSED
    if (this.onclose) {
      this.onclose({ code, reason } as CloseEvent);
    }
  }

  triggerOpen() {
    this.readyState = 1; // OPEN
    if (this.onopen) {
      this.onopen(new Event("open"));
    }
  }

  triggerMessage(data: unknown) {
    if (this.onmessage) {
      const payload = typeof data === "string" ? data : JSON.stringify(data);
      this.onmessage({ data: payload } as MessageEvent);
    }
  }

  triggerError() {
    if (this.onerror) {
      this.onerror(new Event("error"));
    }
  }
}

describe("useFeedLiveUpdates hook", () => {
  let originalWebSocket: typeof WebSocket;
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.useFakeTimers();
    MockWebSocket.instances = [];
    originalWebSocket = globalThis.WebSocket;
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket;

    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    useAppStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
    globalThis.WebSocket = originalWebSocket;
    useAppStore.getState().reset();
  });

  function createWrapper() {
    return ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  }

  it("does not connect when feedSlug is null", () => {
    renderHook(() => useFeedLiveUpdates(null), { wrapper: createWrapper() });

    expect(MockWebSocket.instances.length).toBe(0);
    expect(useAppStore.getState().liveStatus).toBe("disconnected");
  });

  it("connects to feed websocket when feedSlug is provided and updates status", () => {
    renderHook(() => useFeedLiveUpdates("metro-city"), {
      wrapper: createWrapper(),
    });

    expect(MockWebSocket.instances.length).toBe(1);
    const ws = MockWebSocket.instances[0]!;
    expect(ws.url).toContain("/api/v1/feeds/metro-city/ws");
    expect(useAppStore.getState().liveStatus).toBe("connecting");

    // Open connection
    act(() => {
      ws.triggerOpen();
    });

    expect(useAppStore.getState().liveStatus).toBe("connected");
  });

  it("invalidates routeMap and arrivals queries when feed_update event matches", () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    renderHook(() => useFeedLiveUpdates("metro-city"), {
      wrapper: createWrapper(),
    });

    const ws = MockWebSocket.instances[0]!;
    act(() => {
      ws.triggerOpen();
    });

    const event = {
      type: "feed_update",
      feed_id: 1,
      feed_slug: "metro-city",
      update_type: "vehicles",
      timestamp: "2026-11-10T12:00:00Z",
      vehicle_count: 5,
    };

    act(() => {
      ws.triggerMessage(event);
    });

    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["routeMap", "metro-city"],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["arrivals", "metro-city"],
    });
    expect(useAppStore.getState().lastLiveUpdateAt).toBe("2026-11-10T12:00:00Z");
  });

  it("ignores feed_update events for a different feed slug", () => {
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    renderHook(() => useFeedLiveUpdates("metro-city"), {
      wrapper: createWrapper(),
    });

    const ws = MockWebSocket.instances[0]!;
    act(() => {
      ws.triggerOpen();
    });

    const eventForOtherFeed = {
      type: "feed_update",
      feed_id: 2,
      feed_slug: "uptown-bus",
      update_type: "vehicles",
      timestamp: "2026-11-10T12:05:00Z",
      vehicle_count: 3,
    };

    act(() => {
      ws.triggerMessage(eventForOtherFeed);
    });

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(useAppStore.getState().lastLiveUpdateAt).toBeNull();
  });

  it("sends ping heartbeat periodically when connected", () => {
    renderHook(() => useFeedLiveUpdates("metro-city"), {
      wrapper: createWrapper(),
    });

    const ws = MockWebSocket.instances[0]!;
    act(() => {
      ws.triggerOpen();
    });

    expect(ws.sentMessages).toEqual([]);

    // Advance 30s
    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(ws.sentMessages).toContain("ping");
  });

  it("transitions to fallback status and reconnects on unexpected close", () => {
    renderHook(() => useFeedLiveUpdates("metro-city"), {
      wrapper: createWrapper(),
    });

    const ws = MockWebSocket.instances[0]!;
    act(() => {
      ws.triggerOpen();
    });
    expect(useAppStore.getState().liveStatus).toBe("connected");

    // Unexpected close (code 1006 abnormal or server disconnect)
    act(() => {
      ws.close(1006, "Abnormal closure");
    });

    expect(useAppStore.getState().liveStatus).toBe("fallback");

    // Advance timer past backoff delay (1s)
    act(() => {
      vi.advanceTimersByTime(1_500);
    });

    // Should have created a new connection attempt
    expect(MockWebSocket.instances.length).toBe(2);
    expect(useAppStore.getState().liveStatus).toBe("connecting");
  });

  it("does not reconnect when server rejects with code 1008 (policy violation / not found)", () => {
    renderHook(() => useFeedLiveUpdates("unknown-feed"), {
      wrapper: createWrapper(),
    });

    const ws = MockWebSocket.instances[0]!;
    act(() => {
      ws.close(1008, "Feed 'unknown-feed' not found");
    });

    expect(useAppStore.getState().liveStatus).toBe("disconnected");

    // Advance timers significantly
    act(() => {
      vi.advanceTimersByTime(60_000);
    });

    // Should NOT have attempted reconnect
    expect(MockWebSocket.instances.length).toBe(1);
  });
});
