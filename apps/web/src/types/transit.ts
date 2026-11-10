/**
 * Transit domain interfaces matching the WaitWatch API v1 schemas.
 */

export interface FeedSummary {
  id: number;
  city_name: string;
  slug: string;
  feed_status: string;
  is_live_tracking_enabled: boolean;
  last_static_import_at: string | null;
  last_realtime_poll_at: string | null;
}

export interface StopSummary {
  stop_id: string;
  code: string | null;
  name: string;
  description: string | null;
  latitude: number;
  longitude: number;
  parent_station_id: string | null;
  location_type: number;
  wheelchair_boarding: number;
  platform_code: string | null;
  timezone: string | null;
}

export type PredictionSource = "HISTORY_ADJUSTED" | "SCHEDULE_ONLY" | string;

export interface StopArrivalPrediction {
  feed_slug: string;
  feed_id: number;
  stop_id: string;
  trip_id: string;
  route_id: string;
  route_short_name: string | null;
  trip_headsign: string | null;
  vehicle_id: string | null;
  stop_sequence: number;
  scheduled_arrival_time: string;
  estimated_arrival_time: string;
  delay_seconds: number;
  prediction_source: PredictionSource;
  source_observation_time: string | null;
}

export interface ItemEnvelope<T> {
  data: T;
}

export interface PaginationMeta {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: PaginationMeta;
}
