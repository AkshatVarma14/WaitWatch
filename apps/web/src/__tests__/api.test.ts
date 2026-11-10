import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  API_BASE_URL,
  fetchApi,
  fetchArrivals,
  fetchFeeds,
  fetchHealth,
  fetchRouteMap,
  fetchRoutes,
  fetchStops,
  getFeedWebSocketUrl,
  getWsBaseUrl,
  planTrip,
} from "../lib/api";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("exports normalized API_BASE_URL and forms expected URL", async () => {
    expect(API_BASE_URL).not.toMatch(/\/$/);
    const mockJson = { ok: true };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockJson), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await fetchApi("/api/health");
    expect(fetchSpy).toHaveBeenCalledWith(`${API_BASE_URL}/api/health`);
  });

  it("fetchApi returns parsed json on ok response", async () => {
    const mockJson = { message: "hello" };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockJson), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await fetchApi<{ message: string }>("/test");
    expect(result).toEqual(mockJson);
  });

  it("fetchApi extracts detail message on non-ok response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Feed not found" }), {
        status: 404,
        statusText: "Not Found",
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(fetchApi("/test")).rejects.toThrow("Feed not found");
  });

  it("fetchApi falls back to statusText if error is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("plain error", {
        status: 500,
        statusText: "Internal Server Error",
      }),
    );

    await expect(fetchApi("/test")).rejects.toThrow(
      "API error: 500 Internal Server Error",
    );
  });

  it("fetchFeeds requests /api/v1/feeds and returns unwrapped list", async () => {
    const mockFeeds = [{ id: 1, slug: "sf-muni", city_name: "San Francisco" }];
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: mockFeeds }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const feeds = await fetchFeeds();
    expect(feeds).toEqual(mockFeeds);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/feeds"),
    );
  });

  it("fetchRoutes requests /api/v1/feeds/:slug/routes with query params", async () => {
    const mockRoutesResponse = {
      data: [{ route_id: "R1", short_name: "101" }],
      pagination: {
        total: 1,
        page: 1,
        page_size: 50,
        total_pages: 1,
        has_next: false,
        has_prev: false,
      },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockRoutesResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await fetchRoutes("metro-city", "express", 1, 50);
    expect(res).toEqual(mockRoutesResponse);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/api\/v1\/feeds\/metro-city\/routes\?page=1&page_size=50&q=express/,
      ),
    );
  });

  it("fetchRouteMap requests /api/v1/feeds/:slug/routes/:id/map", async () => {
    const mockMapData = {
      feed_slug: "metro-city",
      route_id: "R1",
      shapes: [],
      stops: [],
      vehicles: [],
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: mockMapData }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await fetchRouteMap("metro-city", "R1");
    expect(res).toEqual(mockMapData);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/v1\/feeds\/metro-city\/routes\/R1\/map/),
    );
  });

  it("fetchStops encodes parameters and requests /api/v1/feeds/:slug/stops", async () => {
    const mockStopsResponse = {
      data: [{ stop_id: "S1", name: "Market St" }],
      pagination: {
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
        has_next: false,
        has_prev: false,
      },
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockStopsResponse), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await fetchStops("sf-muni", "market", 1, 20);
    expect(res).toEqual(mockStopsResponse);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/api\/v1\/feeds\/sf-muni\/stops\?page=1&page_size=20&q=market/,
      ),
    );
  });

  it("fetchArrivals requests /api/v1/feeds/:slug/stops/:id/arrivals", async () => {
    const mockArrivals = [{ trip_id: "T1", scheduled_arrival_time: "..." }];
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: mockArrivals }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await fetchArrivals("sf-muni", "S1", 5);
    expect(res).toEqual(mockArrivals);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/api\/v1\/feeds\/sf-muni\/stops\/S1\/arrivals\?limit=5/,
      ),
    );
  });

  it("fetchHealth requests /api/health", async () => {
    const mockHealth = {
      status: "ok",
      environment: "test",
      database: "connected",
      version: "0.1.0",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify(mockHealth), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await fetchHealth();
    expect(res).toEqual(mockHealth);
  });

  it("getWsBaseUrl returns a valid ws or wss base URL", () => {
    const wsBase = getWsBaseUrl();
    expect(wsBase).toMatch(/^wss?:\/\//);
    expect(wsBase).not.toMatch(/\/$/);
    expect(wsBase).not.toContain("://api:");
  });

  it("getFeedWebSocketUrl properly formats and encodes feed slug path", () => {
    const url = getFeedWebSocketUrl("metro-city");
    expect(url).toMatch(/^wss?:\/\/.*\/api\/v1\/feeds\/metro-city\/ws$/);

    const encodedUrl = getFeedWebSocketUrl("metro city/uptown");
    expect(encodedUrl).toContain("/api/v1/feeds/metro%20city%2Fuptown/ws");
  });

  it("planTrip requests /api/v1/feeds/:slug/plan with query parameters", async () => {
    const mockPlanData = {
      feed_slug: "sf-muni",
      origin_stop_id: "S1",
      destination_stop_id: "S2",
      target_time: "08:00:00",
      target_date: "2026-11-10",
      itineraries: [],
    };
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ data: mockPlanData }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const res = await planTrip("sf-muni", "S1", "S2", "08:00:00", "2026-11-10", 3);
    expect(res).toEqual(mockPlanData);
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringMatching(
        /\/api\/v1\/feeds\/sf-muni\/plan\?origin_stop_id=S1&destination_stop_id=S2&limit=3&time=08%3A00%3A00&date=2026-11-10/,
      ),
    );
  });
});
