import type {
  FeedSummary,
  ItemEnvelope,
  PaginatedResponse,
  StopArrivalPrediction,
  StopSummary,
} from "../types/transit";

const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
