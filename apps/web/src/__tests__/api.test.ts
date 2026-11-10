import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchApi,
  fetchArrivals,
  fetchFeeds,
  fetchHealth,
  fetchStops,
} from "../lib/api";

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
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
});
