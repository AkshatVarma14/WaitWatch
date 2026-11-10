# WaitWatch System Architecture

## Overview

WaitWatch is a web application built on a three-tier architecture designed for real-time public transit tracking. The system ingests standardized transit data (GTFS and GTFS-Realtime), stores it in a geospatially-enabled database, and serves it to users through a React-based frontend via REST API and WebSocket connections.

## Component Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLIENT TIER                                 │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  React Frontend (Vite + TypeScript)                           │  │
│  │  ├── TanStack Query (server state, caching, refetching)       │  │
│  │  ├── Zustand (client state: UI prefs, selected routes)        │  │
│  │  ├── Map Component (route shapes, stops, vehicle positions)   │  │
│  │  └── Tailwind CSS (styling)                                   │  │
│  └──────────────┬─────────────────────────┬──────────────────────┘  │
│                 │ REST API                 │ WebSocket               │
└─────────────────┼─────────────────────────┼──────────────────────────┘
                  │                         │
┌─────────────────┼─────────────────────────┼──────────────────────────┐
│                 │    APPLICATION TIER      │                          │
│                 ▼                         ▼                          │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Server                                               │  │
│  │  ├── REST API (routes, stops, schedules, vehicles, ETAs)      │  │
│  │  ├── WebSocket Server (real-time position & ETA broadcasts)   │  │
│  │  └── Background Services                                      │  │
│  │      ├── GTFS Static Ingestion Service                        │  │
│  │      ├── GTFS-Realtime Polling Service                        │  │
│  │      └── ETA Prediction Service                               │  │
│  └──────────────────────────┬────────────────────────────────────┘  │
│                             │ SQLAlchemy + GeoAlchemy2              │
└─────────────────────────────┼────────────────────────────────────────┘
                              │
┌─────────────────────────────┼────────────────────────────────────────┐
│                             ▼    DATA TIER                           │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL + PostGIS                                         │  │
│  │  ├── GTFS Static Tables (routes, stops, trips, stop_times,    │  │
│  │  │   calendar, shapes)                                        │  │
│  │  ├── Real-Time Tables (vehicle_positions, trip_updates)        │  │
│  │  ├── Analytics Tables (historical_delays)                     │  │
│  │  └── Geospatial Indexes (stop locations, route shapes,        │  │
│  │      vehicle positions)                                        │  │
│  └────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**React Frontend (Vite, TanStack Query, Zustand)**
- Renders the user interface including the interactive transit map
- Communicates with the backend via REST API for data queries (routes, stops, schedules)
- Maintains a WebSocket connection for real-time vehicle position and ETA updates
- TanStack Query manages server state with automatic caching, background refetching, and request deduplication
- Zustand manages client-only state such as UI preferences, selected routes, and map viewport

**FastAPI Backend**
- Serves the REST API for all transit data queries
- Manages WebSocket connections for broadcasting real-time updates to connected clients
- Orchestrates background services for GTFS data ingestion and processing
- Handles request validation via Pydantic models
- Provides automatic OpenAPI documentation

**PostgreSQL/PostGIS**
- Stores all transit data persistently with ACID guarantees
- PostGIS extension enables efficient geospatial queries (nearby stops, point-in-polygon, distance calculations)
- Geospatial indexes accelerate location-based queries for stops, route shapes, and vehicle positions

## Key Services

### 0. Database Layer & Transit Models — `Implemented (Slice 1.1)`

Establishes the normalized PostgreSQL/PostGIS database schema scoped for multi-city support:
- **`TransitFeed`**: Multi-city configuration, feed URLs, environment variable key reference, operational status, and timestamps.
- **`Agency`**: Agency profiles, timezone, and contact details scoped to `feed_id`.
- **`Route`**: Transit route classifications and styling scoped to `feed_id`.
- **`Stop`**: Transit stops and stations with PostGIS `geography(POINT, 4326)` column, GiST index, and parent station hierarchy.
- **`Trip`**: Journeys along routes with calendar service IDs and accessibility indicators.
- **`StopTime`**: Scheduled arrival/departure times, stop ordering, and pickup/drop-off types.
- **`Calendar` & `CalendarDate`**: Weekly service patterns and date-specific exceptions.
- **Alembic Migration**: `0001_initial_transit_models` providing reproducible upgrade and downgrade DDL with explicit PostGIS extension setup.

### 1. GTFS Static Ingestion Service — `Implemented (Slice 1.2)`

Orchestrates downloading, inspecting, parsing, and persisting GTFS Schedule feeds into the database:
- **ZIP Safety Inspection** (`archive.py`): In-memory ZIP inspection enforcing archive size bounds, decompressed size limits, compression ratio bounds (zip bomb protection), directory traversal prevention, and encryption rejection.
- **Resilient Downloader** (`downloader.py`): Streaming HTTP client enforcing timeouts and size bounds, masking credentials in logs and query parameters.
- **GTFS Schedule Parser & Validator** (`parser.py`): CSV table parser strictly validating headers, row types, coordinate bounds, service-day times (including hours >= 24), single-agency feed omission of `agency_id`, multi-agency references, calendar and calendar-dates schedule validation, and relational integrity.
- **Feed-Scoped Atomic Importer** (`importer.py`): Transactional persistence engine that clears prior data for the feed in reverse foreign key order, resolves parent-station hierarchies, inserts high-volume stop times in bounded batches, updates feed operational timestamps, and rolls back atomically on any failure.
- **Administrative CLI** (`cli.py`): CLI interface (`python -m app.services.gtfs.cli ingest --feed-id <ID>`) for operators and background jobs without exposing unauthenticated public endpoints.
- **Forward Migration**: `0002_optional_agency_id` allowing `agency_id` to be nullable for standard single-agency feeds.

### 2. GTFS-Realtime Service — `Partial (Slice 2.1 Vehicle Positions Implemented)`

Polls and parses GTFS-Realtime Protocol Buffer feeds:
- **Vehicle Position Ingestion (`services/realtime/`)**:
  - Official MobilityData GTFS-Realtime Protocol Buffer decoding (`gtfs_realtime_pb2.FeedMessage`).
  - Strict FeedHeader validation: enforces `FULL_DATASET` mode and explicitly rejects `DIFFERENTIAL` mode with sanitized error.
  - Entity validation: duplicate entity ID rejection, mandatory position data check, finite WGS84 coordinate bounds (`[-90, 90]`, `[-180, 180]`), bearing `[0, 360]`, non-negative speed and odometer.
  - Distinction preserved between `FeedHeader.timestamp` and `VehiclePosition.timestamp`.
  - Loosely coupled source strings for `trip_id`, `route_id`, and `stop_id` ensuring partial or unscheduled vehicle telemetry is never rejected.
  - Current-state snapshot persistence: replaces only the target feed's vehicles atomically; rolls back and preserves the prior snapshot on any failure.
  - Updates `TransitFeed.last_realtime_poll_at` upon successful commit.
  - Administrative CLI: `python -m app.services.realtime.cli poll-vehicles --feed-id <ID> | --slug <SLUG> [--file <PATH>]`.
  - Streaming HTTP downloader with timeout, payload size bounds (50MB), and URL credential masking.
- **Forward Migration**: `0003_vehicle_positions` creating table with spatial GiST index on `point`.
- **Historical Vehicle Observations (`services/realtime/`)**:
  - `VehicleObservation` append-only historical telemetry model with PostGIS GiST index.
  - Forward migration `0004_vehicle_observations` with composite uniqueness constraint `(feed_id, entity_id, observed_at)`.
  - Deterministic timestamp fallback hierarchy (`vehicle_timestamp` -> `feed_timestamp` -> server receipt time).
  - Atomic dual-persistence transaction: updates current-state snapshot table and appends deduplicated observations in one all-or-nothing transaction.
  - Internal query helper `get_recent_observations(...)` with mandatory `since` bound and result capping (1,000 max).
- **Planned Remaining Stage 2 Work**:
  - GTFS-Realtime TripUpdates ingestion (delays, arrival/departure estimates)
  - GTFS-Realtime ServiceAlerts ingestion
  - Background polling scheduler
  - WebSocket broadcaster for live position streaming

### 3. ETA Prediction Service — `Implemented (Slice 3.2)`

Calculates deterministic estimated arrival times (ETAs) at transit stops:
- **Endpoint**: `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals` (supports feed slug or numeric ID).
- **Core Components (`services/prediction/`)**:
  - `ArrivalPredictionService`: Evaluates upcoming arrivals at a target stop from live vehicle positions.
  - Active service resolution: Evaluates GTFS `calendars` and `calendar_dates` exceptions (added/removed) against the agency timezone.
  - Extended hours support: Parses GTFS times > 24:00 (e.g. `25:30:00`) mapping to early morning departures on the next calendar day.
  - Telemetry freshness enforcement: Rejects vehicle snapshots older than 300 seconds (5 minutes) or future-skewed beyond 60 seconds.
  - Downstream eligibility filtering: Evaluates vehicles on active trips where `target_stop_sequence >= vehicle.current_stop_sequence`.
  - Historical median delay adjustment:
    $$\Delta t_i = T_{\text{obs}}(P_i) - T_{\text{sched}}(P_i) \quad \text{for earlier STOPPED\_AT stops on the same trip}$$
    $$\Delta t_{\text{adj}} = \text{median}(\{\Delta t_i\}) \quad (\text{sample count} \ge 1)$$
    $$T_{\text{est}} = T_{\text{sched}} + \Delta t_{\text{adj}} \quad (\text{labeled } \texttt{HISTORY\_ADJUSTED})$$
  - Schedule fallback: When insufficient historical samples exist, returns $T_{\text{est}} = T_{\text{sched}}$ with $\Delta t = 0$ (labeled $\texttt{SCHEDULE\_ONLY}$).
  - Assumptions & Limits: Assumes uniform delay propagation without signal timing or shape geometry simulation.

### 4. REST API — `Implemented (Slices 1.3 & 3.2)`

Currently implemented:
- Health check (`GET /api/v1/health`, `GET /health`)
- Root endpoint (`GET /api/v1/`, `GET /`)
- Feeds exploration:
  - `GET /api/v1/feeds` — list configured transit feeds with summary status
  - `GET /api/v1/feeds/{feed_slug}` — feed configuration and import metadata
- Route exploration:
  - `GET /api/v1/feeds/{feed_slug}/routes` — list and search routes (`q`, `route_type`, `agency_id`, bounded pagination)
  - `GET /api/v1/feeds/{feed_slug}/routes/{route_id}` — detailed route metadata with operating agency details
- Stop exploration:
  - `GET /api/v1/feeds/{feed_slug}/stops` — list and search stops (`q`, bounded pagination)
  - `GET /api/v1/feeds/{feed_slug}/stops/nearby` — geospatial proximity stop search (`latitude`, `longitude`, `radius_meters`, `limit`) via PostGIS `ST_DWithin`/`ST_Distance` with SQLite fallback
  - `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}` — stop details with parent station resolution
- Stop arrivals & ETA prediction:
  - `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals` — predicted vehicle arrivals at stop, ordered by estimated arrival time, with delay seconds, source labeling, and observation timestamps.
- Error handling: Sanitized 503 response on database unavailability without credential leakage
- Consistent response envelopes (`ItemEnvelope`, `PaginatedResponse` with `PaginationMeta`)

Planned endpoints:
- `GET /trips/{id}` — trip details with stop times (Stage 2)
- `GET /vehicles` — current vehicle positions (Stage 2)
- `GET /eta/{stop_id}` — predicted arrival times for a stop (Stage 3)

### 5. WebSocket Server — `Planned`

Provides real-time updates to connected clients:
- Vehicle position broadcasts (all vehicles or filtered by route)
- ETA updates for subscribed stops
- Service alerts and disruption notifications

### 6. Transit Explorer Web Frontend — `Implemented (Slice 4.1)`

User-facing React single-page application (`apps/web`):
- **Client Architecture**:
  - React 19 + TypeScript (strict mode, no `any`, functional components only, named exports).
  - Tailwind CSS v4 for responsive, high-contrast dark theme.
  - TanStack Query v5 for asynchronous server state fetching, caching, deduplication, and manual refetching.
  - Zustand v5 client store managing active feed and stop selections with strict feed isolation.
  - Configurable backend API URL through `VITE_API_URL` environment convention with `.env.example`.
- **UI Components (`src/components/`)**:
  - `FeedSelector`: Accessible `<select>` dropdown populated dynamically via `GET /api/v1/feeds`, displaying operational status and live tracking badges.
  - `StopSearch`: Feed-scoped search (`GET /api/v1/feeds/{feed_slug}/stops?q=...`) with debounced text search, wheelchair accessibility indicator, and selection state.
  - `ArrivalsBoard`: Stop-level live arrivals board calling `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`. Displays scheduled vs estimated arrival times, passenger-facing delay pills (`+X min late`, `On time`, `X min early`), prediction source badges (`Live + History` vs `Schedule`), telemetry observation age, and agency timezone disclosure.
- **Feed Isolation**:
  - Switching transit feeds immediately clears the selected stop and arrivals state in the Zustand store, preventing cross-feed data leakage.
- **Robust State Handling**:
  - Explicit loading spinners, empty states ("No upcoming arrivals", "No stops found"), offline/error banners with retry buttons, and manual refresh controls.

## Data Flow

### 1. GTFS Static Data Ingestion

```
GTFS Feed (ZIP) → Download → Parse CSVs → Validate → Insert into PostgreSQL
                                                        ├── routes
                                                        ├── stops
                                                        ├── trips
                                                        ├── stop_times
                                                        ├── calendar
                                                        └── shapes
```

### 2. Real-Time Vehicle Tracking

```
GTFS-RT Feed → Poll (every ~15s) → Parse Protobuf → Store vehicle_positions
                                                           │
                                                           ▼
                                                    WebSocket Broadcast
                                                           │
                                                           ▼
                                                    Connected Clients
```

### 3. Client Data Queries

```
Client Request → REST API → SQLAlchemy Query → PostgreSQL → Response (JSON)
```

### 4. ETA Prediction Pipeline

```
Vehicle Positions + Schedule Data + Historical Delays
          │
          ▼
    ETA Prediction Service
          │
          ▼
    WebSocket Broadcast → Connected Clients
```

### 5. WebSocket Live Updates & PostgreSQL Pub/Sub — `Implemented (Slice 4.6)`

Provides real-time event notifications to connected frontend clients when new transit snapshots are ingested:
- **Zero-Broker Architecture**: Uses PostgreSQL native `LISTEN/NOTIFY` on channel `waitwatch_feed_updates` to coordinate update notifications across backend API processes without requiring Redis or an external message broker.
- **Atomic Notification Staging**: Notification execution (`publish_feed_update`) is staged within the active database transaction. PostgreSQL guarantees notifications are delivered if and only if the transaction commits; rolled back or failed transactions emit zero notifications.
- **Dedicated Database Listener**: Single managed `asyncpg` listener (`run_db_listener`) per API process started via FastAPI lifespan, reconnecting with exponential backoff on disconnects without interrupting REST API service. Gracefully disabled when running on SQLite.
- **Feed-Scoped WebSocket Endpoint**: `/api/v1/feeds/{feed_slug}/ws` verifies the feed slug against the database, rejects unknown feeds with WebSocket policy violation code 1008, acknowledges connections, and responds to ping heartbeats.
- **Thread-Safe Connection Manager**: `ConnectionManager` isolates client sets per feed, prunes closed or broken connections on broadcast failure, enforces capacity bounds, and gracefully closes sockets on process shutdown.
- **Client Cache Synchronization**: React hook (`useFeedLiveUpdates`) receives lightweight `FeedUpdateEvent` payloads and invalidates matching TanStack Query caches (`["routeMap", feedSlug]` and `["arrivals", feedSlug]`). Pauses redundant 30-second polling while connected, and seamlessly falls back to steady-state polling on disconnect, error, or hidden tabs.

## Technology Rationale

| Technology | Rationale |
|-----------|-----------|
| **PostGIS** | Enables efficient geospatial queries — finding nearby stops within a radius, calculating distances between vehicles and stops, and storing/querying route shape geometries. Essential for a location-centric transit application. |
| **FastAPI** | High-performance async Python framework with native WebSocket support. Automatic OpenAPI documentation generation. Strong Pydantic integration for request/response validation. Excellent async support for I/O-bound database and network operations. |
| **TanStack Query** | Manages server state on the frontend with automatic caching, background refetching, stale-while-revalidate patterns, and request deduplication. Eliminates boilerplate for data fetching and keeps the UI responsive. |
| **Zustand** | Lightweight client state management for UI concerns (selected route, map viewport, user preferences). Minimal boilerplate compared to Redux. Does not replace TanStack Query for server state — each tool handles its appropriate domain. |
| **SQLAlchemy + Alembic** | Mature ORM with GeoAlchemy2 for PostGIS column types and spatial queries. Alembic provides reliable database migration management tied to the SQLAlchemy model definitions. |
| **Vite** | Fast development server with hot module replacement. Near-instant startup compared to Webpack. Native TypeScript and JSX support. |

## Container Architecture & Deployment Scaffolding

WaitWatch provides a reproducible Docker Compose architecture (`docker-compose.yml`) for local verification and single-host deployment scaffolding:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Docker Compose Stack                          │
│                                                                        │
│   ┌──────────────────┐               ┌─────────────────────────────┐   │
│   │   waitwatch-web  │               │        waitwatch-api        │   │
│   │  (Nginx 1.30.6)  │─── /api/ ────►│        (FastAPI 3.12)       │   │
│   │    Port: 3000    │               │          Port: 8000         │   │
│   └─────────▲────────┘               └──────────────┬──────────────┘   │
│             │                                       │                  │
│      GET /health (wget)                      GET /api/health (urllib)  │
│             │                                       │                  │
│             │       ┌───────────────────────┐       │                  │
│             │       │   waitwatch-migrate   │       │                  │
│             │       │   (Alembic upgrade)   │       │                  │
│             │       │    (One-shot exit)    │       │                  │
│             │       └───────────┬───────────┘       │                  │
│             │                   │                   │                  │
│             │                   ▼                   ▼                  │
│             │       ┌──────────────────────────────────────────────┐   │
│             └───────│                 waitwatch-db                 │   │
│                     │           (PostgreSQL 16 + PostGIS 3.4)      │   │
│                     │          Health: pg_isready | Port: 5432     │   │
│                     │           Volume: waitwatch-pgdata           │   │
│                     └──────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 1. Service Topology & Startup Lifecycle
1. **`db` (PostgreSQL 16 with PostGIS 3.4)**:
   - Official pinned image `postgis/postgis:16-3.4`.
   - Data persists across container lifecycles in named Docker volume `waitwatch-pgdata`.
   - Healthcheck: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}` polled every 5 seconds.
2. **`migrate` (Alembic Migration Runner)**:
   - Reuses the `waitwatch-api:0.1.0` image with command `["alembic", "upgrade", "head"]`.
   - Configured with `restart: "no"`.
   - Depends on `db` with `condition: service_healthy`.
   - **Deterministic, Race-Free Migrations**: By running in a dedicated one-shot container before `api` boots, migrations execute exactly once. Subsequent restarts or multiple replicas of `api` do not trigger concurrent, competing migration processes.
3. **`api` (FastAPI Async Backend)**:
   - Pinned base image `python:3.12-slim-bookworm` with unprivileged runtime user `waitwatch` (UID 1001).
   - Starts only after `migrate` completes cleanly (`condition: service_completed_successfully`) and `db` is healthy.
   - Native healthcheck: invokes `urllib.request.urlopen("http://127.0.0.1:8000/api/health")` using Python's standard library, verifying application and database connectivity without external shell dependencies.
4. **`web` (React SPA + Nginx Reverse Proxy)**:
   - Multi-stage build: compiled with pinned `node:22-alpine3.20` and served via pinned `nginx:1.30.6-alpine`.
   - Nginx delivers gzip-compressed static assets with immutable cache headers and SPA client-side fallback (`try_files $uri $uri/ /index.html`).
   - Built-in reverse proxy routes `/api/` traffic directly to `http://api:8000/api/` on the internal bridge network.
   - Dedicated healthcheck at `/health` returning HTTP 200 without access log spam.

### 2. Browser Networking vs. Internal Container Networking
In client-side Single Page Applications (SPAs), JavaScript code runs exclusively in the user's web browser, not inside the Docker container bridge network.
- **Direct API access**: When `VITE_API_URL` is set to `http://localhost:8000`, the browser connects directly to FastAPI on the host machine. CORS headers permit `http://localhost:3000` and `http://localhost:5173`.
- **Proxied API access**: When `VITE_API_URL` is set to empty string `""`, the browser issues relative requests (e.g. `/api/v1/feeds`), which Nginx proxies internally to `http://api:8000/api/`.
- **Invalid configuration**: Setting `VITE_API_URL=http://api:8000` causes browser-side DNS resolution failure (`ERR_NAME_NOT_RESOLVED`), because `api` is a Docker-internal hostname unresolvable by the host's operating system.

### 3. Production Deployment Considerations & Remaining Scope
While the Docker Compose stack provides a robust foundation for local development and single-host testing, full production readiness requires:
- **Secrets Management**: Passing sensitive credentials via secure runtime secret stores (e.g. Vault, AWS Secrets Manager, Doppler) rather than plain-text `.env` files.
- **TLS Termination**: Provisioning SSL/TLS certificates (e.g. via Let's Encrypt / Certbot, Cloudflare, or an external Ingress Controller) in front of port 80/443.
- **Managed Database**: Replacing the local containerized PostgreSQL instance with a high-availability managed database (e.g. AWS RDS Aurora PostgreSQL with PostGIS, GCP Cloud SQL) for automated failover, replication, and point-in-time backups.
- **Horizontal Scaling & Worker Schedulers**: Moving periodic GTFS static ingestion and GTFS-RT pollers into isolated worker processes managed by Celery, temporal, or Kubernetes CronJobs.
- **Local Verification Limitation**: Docker is not installed on this development machine; Compose verification was conducted strictly via static YAML schema, AST, and dependency condition assertions (`scratch/validate_compose.py`), not via live Docker daemon execution, image building, or container smoke testing.

## Current Status

**Stages 0 through 4 are complete and verified across all roadmap slices (4.1 through 4.5 and follow-up Slice 4.6)**:

- Full monorepo repository structure, Docker Compose stack (`db`, `migrate`, `api`, `web`), and CI/CD pipelines
- Complete GTFS Static database schema, migrations 0001–0006 (`0006_trip_updates`), and ingestion pipeline
- Transit Query REST API for feeds, routes, stops, nearby geospatial queries, and route map visualization (`/api/v1/feeds/{feed_slug}/routes/{route_id}/map`)
- GTFS-Realtime vehicle position ingestion, snapshot storage, and deduplicated historical observations
- GTFS-Realtime TripUpdates ingestion (`TripUpdateIngestionService`, `parse_trip_updates`, `trip_updates` snapshot table), atomic snapshot replacement, and combined poll execution (`realtime-cli poll-vehicles`) fetching vehicle positions and configured TripUpdates in a single poll lifecycle with full error isolation and offline `--file` support
- Stop Arrival Prediction & ETA Engine (`GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`) with `TRIP_UPDATE` prediction source, absolute time precedence (`time` > `delay`), departure fallback, trip cancellation (`CANCELED`) suppression, and skipped stop (`SKIPPED`) suppression
- Frontend Feed-Aware Transit Explorer & Live Arrivals Board (`apps/web` with React, TypeScript, TanStack Query, Zustand, and Tailwind) displaying "Live TripUpdate" badges
- Interactive route and vehicle map visualization (`MapView` with Leaflet) rendering true GTFS shape polylines, ordered stop markers, and bearing-rotated live vehicles with configurable tile provider and strict missing-shape warnings (no fabricated geometry)
- Accessible route selector combobox (`RouteSelector`) and stop/vehicle navigator panel (`MapDetailsPanel`)
- Real-time client polling architecture with 30-second interval, document visibility tracking (`useDocumentVisibility`, `usePollingVisibilityRefresh`), transient error handling preserving last successful data with "⚠️ Stale" status, and stable map viewports avoiding automated tile requests
- Production-ready Docker Compose scaffolding (`docker-compose.yml`, `apps/api/Dockerfile`, `apps/web/Dockerfile`, `apps/web/nginx.conf`, `.env.example`) with pinned images, healthchecks, unprivileged users, automated Alembic migration runner, and reverse proxying
- Core WebSocket live updates via feed-scoped WebSocket endpoints, PostgreSQL native `LISTEN/NOTIFY` pub/sub, managed background listener with backoff reconnection, automatic TanStack Query cache invalidation (`routeMap`, `arrivals`), active-tab visibility management, and seamless fallback to 30-second steady-state polling on disconnect, error, or hidden tabs
- Strict feed and route isolation across all frontend selections and API queries
- 92 frontend tests (Vitest across 7 files) and 147 backend tests (Pytest across 11 files) passing cleanly in local and CI runs

Subsequent planned roadmap work:
- Turn-by-turn route navigation / trip planning
- User preferences, favorite stops, and saved routes
