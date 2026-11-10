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

export interface RouteSummary {
  route_id: string;
  agency_id: string | null;
  short_name: string | null;
  long_name: string | null;
  description: string | null;
  route_type: number;
  route_url: string | null;
  route_color: string | null;
  text_color: string | null;
  sort_order: number | null;
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

export type PredictionSource =
  | "HISTORY_ADJUSTED"
  | "SCHEDULE_ONLY"
  | "TRIP_UPDATE"
  | string;

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

export interface ShapePoint {
  latitude: number;
  longitude: number;
  sequence: number;
  distance_traveled: number | null;
}

export interface RouteShape {
  shape_id: string;
  points: ShapePoint[];
}

export interface RouteMapStop {
  stop_id: string;
  name: string;
  code: string | null;
  latitude: number;
  longitude: number;
  stop_sequence: number;
  direction_id: number | null;
  wheelchair_boarding: number;
}

export interface RouteMapVehicle {
  entity_id: string;
  vehicle_id: string | null;
  vehicle_label: string | null;
  latitude: number;
  longitude: number;
  bearing: number | null;
  speed: number | null;
  current_status: number | null;
  trip_id: string | null;
  observed_at: string;
}

export interface RouteMapData {
  feed_slug: string;
  route_id: string;
  route_short_name: string | null;
  route_long_name: string | null;
  route_color: string | null;
  text_color: string | null;
  shapes: RouteShape[];
  stops: RouteMapStop[];
  vehicles: RouteMapVehicle[];
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

export interface FeedUpdateEvent {
  type: "feed_update";
  event_id?: string;
  feed_id: number;
  feed_slug: string;
  update_type: "vehicles" | "trip_updates" | "all";
  timestamp: string;
  vehicle_count?: number | null;
  trip_update_count?: number | null;
}

export type LiveConnectionStatus =
  | "connected"
  | "connecting"
  | "disconnected"
  | "fallback"
  | "paused";
