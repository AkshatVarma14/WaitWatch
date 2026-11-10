import type {
  FeedSummary,
  ItemEnvelope,
  PaginatedResponse,
  RouteMapData,
  RouteSummary,
  StopArrivalPrediction,
  StopSummary,
} from "../types/transit";

const configuredApiUrl = import.meta.env.VITE_API_URL;
export const API_BASE_URL =
  typeof configuredApiUrl === "string"
    ? configuredApiUrl.replace(/\/+$/, "")
    : "http://localhost:8000";

/**
 * Return the WebSocket base URL derived from the configured API URL or browser origin.
 *
 * Rules:
 * - If VITE_API_URL is configured, convert http: to ws: and https: to wss:.
 * - Never use internal container DNS names (such as "api:8000") in browser code;
 *   fall back to window.location if an internal hostname is encountered.
 * - If VITE_API_URL is not configured and running in a browser, derive from window.location.
 * - In non-browser environments without VITE_API_URL, default to ws://localhost:8000.
 */
export function getWsBaseUrl(): string {
  const configured =
    typeof configuredApiUrl === "string" ? configuredApiUrl.trim() : "";
  if (
    configured &&
    !configured.includes("://api:") &&
    !configured.includes("://api/") &&
    configured !== "http://api" &&
    configured !== "https://api"
  ) {
    const trimmed = configured.replace(/\/+$/, "");
    if (trimmed.startsWith("https://")) {
      return trimmed.replace(/^https:\/\//, "wss://");
    }
    if (trimmed.startsWith("http://")) {
      return trimmed.replace(/^http:\/\//, "ws://");
    }
    return trimmed;
  }

  if (typeof window !== "undefined" && window.location?.host) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }

  return "ws://localhost:8000";
}

/**
 * Return the feed-scoped WebSocket endpoint URL.
 */
export function getFeedWebSocketUrl(feedSlug: string): string {
  const wsBase = getWsBaseUrl();
  return `${wsBase}/api/v1/feeds/${encodeURIComponent(feedSlug)}/ws`;
}

export async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    let message = `API error: ${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        message = body.detail;
      }
    } catch {
      // Keep default message if response is not JSON
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export interface HealthStatus {
  status: string;
  environment: string;
  database: string;
  version: string;
}

export function fetchHealth(): Promise<HealthStatus> {
  return fetchApi<HealthStatus>("/api/health");
}

export async function fetchFeeds(): Promise<FeedSummary[]> {
  const envelope = await fetchApi<ItemEnvelope<FeedSummary[]>>("/api/v1/feeds");
  return envelope.data;
}

export async function fetchRoutes(
  feedSlug: string,
  query?: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<PaginatedResponse<RouteSummary>> {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (query && query.trim()) {
    searchParams.set("q", query.trim());
  }
  return fetchApi<PaginatedResponse<RouteSummary>>(
    `/api/v1/feeds/${encodeURIComponent(feedSlug)}/routes?${searchParams.toString()}`,
  );
}

export async function fetchRouteMap(
  feedSlug: string,
  routeId: string,
): Promise<RouteMapData> {
  const envelope = await fetchApi<ItemEnvelope<RouteMapData>>(
    `/api/v1/feeds/${encodeURIComponent(feedSlug)}/routes/${encodeURIComponent(routeId)}/map`,
  );
  return envelope.data;
}

export async function fetchStops(
  feedSlug: string,
  query?: string,
  page: number = 1,
  pageSize: number = 20,
): Promise<PaginatedResponse<StopSummary>> {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (query && query.trim()) {
    searchParams.set("q", query.trim());
  }
  return fetchApi<PaginatedResponse<StopSummary>>(
    `/api/v1/feeds/${encodeURIComponent(feedSlug)}/stops?${searchParams.toString()}`,
  );
}

export async function fetchArrivals(
  feedSlug: string,
  stopId: string,
  limit: number = 10,
): Promise<StopArrivalPrediction[]> {
  const searchParams = new URLSearchParams({
    limit: String(limit),
  });
  const envelope = await fetchApi<ItemEnvelope<StopArrivalPrediction[]>>(
    `/api/v1/feeds/${encodeURIComponent(feedSlug)}/stops/${encodeURIComponent(stopId)}/arrivals?${searchParams.toString()}`,
  );
  return envelope.data;
}
