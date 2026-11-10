const API_BASE_URL =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
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
