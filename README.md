# 🚌 WaitWatch

**Real-time public transit tracking**

## Problem Statement

Public transit riders often lack accurate, real-time information about vehicle locations and arrival times. Existing apps may not cover all cities or provide reliable predictions. Riders are left guessing whether their bus is around the corner or still twenty minutes away.

WaitWatch aims to solve this by ingesting standardized GTFS and GTFS-Realtime data, displaying live vehicle positions on an interactive map, and providing estimated arrival times based on real-time tracking and historical delay patterns.

## Features

### Implemented Functionality

- 📍 **Route and stop exploration** — Feed-aware explorer to browse transit agencies, routes, and ordered stops.
- 🗺️ **Interactive map visualization** — Feed-scoped Leaflet map displaying real GTFS route shapes, stops, and live vehicle markers.
- ⏱️ **Real-time arrivals & ETA prediction** — Stop-level arrivals board combining scheduled stop times, GTFS-RT TripUpdates, and live vehicle positions with delay calculation.
- ⚡ **Live WebSocket updates & pub/sub** — Instant UI refresh over feed-scoped WebSockets backed by PostgreSQL `LISTEN/NOTIFY`, with LRU deduplication and automatic fallback to 30-second steady-state REST polling.
- 🔄 **GTFS & GTFS-Realtime ingestion** — Atomic ingestion pipelines for static GTFS archives (shapes, routes, stops, trips, calendar) and GTFS-RT vehicle positions and trip updates.
- 🏙️ **Multi-feed configuration** — Database-backed feed registry for configuring independent transit feeds by city/agency with operational status management.

### Future Roadmap

- 🧭 **Multi-modal trip planning** — Turn-by-turn route planning between arbitrary locations (e.g. via Connection Scan Algorithm or RAPTOR).
- ⭐ **User preferences & saved stops** — Bookmarks and favorites for frequent routes and stops.
- ☁️ **Cloud deployment & multi-city production hosting** — Managed multi-region hosting and automated feed polling workers.

## Technology Stack

| Category | Technologies |
|----------|-------------|
| **Frontend** | React, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand |
| **Backend** | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| **Database** | PostgreSQL, PostGIS |
| **Testing** | Vitest (frontend), Pytest (backend) |
| **CI/CD** | GitHub Actions |

## Architecture Overview

WaitWatch follows a three-tier architecture:

1. **React SPA** — The frontend serves the UI, renders the map, and communicates with the backend via REST API and WebSocket connections
2. **FastAPI Backend** — Serves REST endpoints for transit data, manages WebSocket connections for real-time updates, and runs background services for GTFS ingestion and ETA prediction
3. **PostgreSQL/PostGIS** — Stores all transit data (routes, stops, schedules, vehicle positions) with geospatial indexing for efficient location-based queries

```
User → React SPA → FastAPI (REST + WebSocket) → PostgreSQL/PostGIS
                                ↑
              GTFS Static Feed ─┘
              GTFS-RT Feed ─────┘
```

## Repository Structure

```
WaitWatch/
├── apps/
│   ├── web/               # React frontend (Vite + TypeScript + Tailwind)
│   └── api/               # FastAPI backend (Python)
├── docs/
│   ├── architecture/      # System architecture documentation
│   └── decisions/         # Architectural Decision Records (ADRs)
├── infrastructure/        # Docker, deployment configs
├── scripts/               # Utility scripts
├── .github/workflows/     # CI/CD pipeline definitions
├── .env.example           # Environment variable template
├── AGENTS.md              # Agent coding guidelines
├── PROJECT_INSTRUCTIONS.md # Development instructions
└── README.md              # This file
```

## Local Setup

### Prerequisites

- **Node.js** 20+
- **Python** 3.11+
- **PostgreSQL** 15+ with PostGIS extension
- **Git**

### Clone the Repository

```bash
git clone https://github.com/AkshatVarma14/WaitWatch.git
cd WaitWatch
```

### Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your local configuration. See [Environment Configuration](#environment-configuration) below.

### Docker Compose Full Stack (Recommended)

WaitWatch includes a complete Docker Compose scaffolding for running the database, migrations, API, and web frontend in isolated containers:

```bash
# 1. Copy configuration template and configure credentials
cp .env.example .env

# 2. Start the full application stack
docker compose up -d --build

# 3. Check service health and status
docker compose ps

# 4. View logs
docker compose logs -f api

# 5. Stop the stack
docker compose down
```

#### Service Architecture & Startup Order
1. **`db`** (`postgis/postgis:16-3.4`): Starts PostgreSQL/PostGIS and verifies readiness via `pg_isready` health check. Data persists in named volume `waitwatch-pgdata`.
2. **`migrate`** (`waitwatch-api:0.1.0`): One-shot container that waits for `db` to be healthy, executes `alembic upgrade head` to apply all database migrations safely, and exits cleanly. This prevents concurrent migration race conditions on restarts or scaling.
3. **`api`** (`waitwatch-api:0.1.0`): Starts FastAPI on port 8000 only after `migrate` completes successfully (`condition: service_completed_successfully`) and `db` is healthy. Verified via native Python `GET /api/health` health check.
4. **`web`** (`waitwatch-web:0.1.0`): Multi-stage build (`node:22-alpine` builder + `nginx:1.30.6-alpine` runtime) serving the React SPA on port 3000 (`http://localhost:3000`) and reverse-proxying `/api/` to the backend. Verified via Nginx `/health` check.

> **Browser Networking Note**: Client-side JavaScript executes in the user's browser, not inside the Docker network. Use `http://localhost:8000` (or leave empty `""` to use Nginx reverse proxying). Never set `VITE_API_URL` to internal Docker hostnames like `http://api:8000`.

> **Verification Note**: Docker is not installed on this local Windows development host; Compose verification is performed via static configuration and dependency analysis rather than live `docker compose up` execution.

## Environment Configuration

The `.env.example` file contains all required environment variables. Copy it to `.env` and configure each section:

| Variable Group | Description |
|---------------|-------------|
| **Database** | PostgreSQL connection string, host, port, credentials |
| **GTFS** | GTFS static feed URLs, download paths |
| **GTFS-RT** | GTFS-Realtime feed URLs, API keys (if required by transit agency) |
| **Server** | Backend host, port, CORS origins |
| **Frontend** | API base URL, WebSocket URL |

> **Security:** Never commit your `.env` file. It is included in `.gitignore`.

## Running the Frontend

```bash
cd apps/web
npm install
npm run dev
```

The development server starts at `http://localhost:5173` by default.

## Running the Backend

```bash
cd apps/api
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

The API server starts at `http://localhost:8000` by default. API documentation is available at `http://localhost:8000/docs`.

## Testing

### Frontend Tests

```bash
cd apps/web
npm test
```

### Backend Tests

```bash
cd apps/api
pytest
```

### Run All Tests in CI

The GitHub Actions pipeline runs both frontend and backend tests automatically on every push.

## Current Development Status

| Stage | Description | Status |
|-------|------------|--------|
| Stage 0 | Project initialization and foundation | ✅ Complete |
| Stage 1 | GTFS static data ingestion | ✅ Complete (Slices 1.1, 1.2 & 1.3) |
| Stage 2 | GTFS-Realtime integration | ✅ Complete (Slice 2.1 Complete) |
| Stage 3 | Historical Observation & ETA Prediction | ✅ Complete (Slices 3.1 & 3.2 Complete) |
| Stage 4 | UI polish and deployment | ✅ Complete (Slices 4.1–4.5 & Slice 4.6 Follow-Up Complete) |

### Completed Milestones
- **Stage 0**: Full foundation with React/TS/Tailwind frontend, FastAPI backend, CI workflows, and documentation.
- **Stage 1, Slice 1.1**: Database foundation, PostgreSQL/PostGIS connection handling, transit data models (`TransitFeed`, `Agency`, `Route`, `Stop`, `Trip`, `StopTime`, `Calendar`, `CalendarDate`), and initial Alembic migration (`0001_initial_transit_models`).
- **Stage 1, Slice 1.2**: GTFS Static Ingestion Pipeline (`GTFSIngestionService`), in-memory safe ZIP extraction (protecting against decompression bombs, path traversal, encryption), robust CSV parsing with full GTFS Schedule compliance (single-agency without `agency_id`, multi-agency validation, post-midnight times e.g. `25:35:00`, calendar exception dates, coordinate bounds, referential checks), feed-scoped atomic/idempotent persistence, forward migration `0002_optional_agency_id`, and administrative CLI.
- **Stage 1, Slice 1.3**: Transit Query API & Route/Stop Exploration (`/api/v1/feeds/...`), feed isolation, route listing/search/filtering by GTFS route_type and agency, GTFS string ID detail endpoints, stop listing/search, geospatial nearby stop search (`/stops/nearby`) via PostGIS `ST_DWithin`/`ST_Distance` with SQLite fallback, bounded pagination metadata, sanitized 503 database unavailability error handling, and comprehensive test suite (59 total backend tests).
- **Stage 2, Slice 2.1**: GTFS-Realtime Vehicle-Position Ingestion (`VehiclePositionIngestionService`), official MobilityData protobuf decoding (`gtfs_realtime_pb2.FeedMessage`), FeedHeader incrementality validation with explicit `DIFFERENTIAL` rejection, duplicate entity ID validation, coordinate bounds checking (`[-90, 90]`, `[-180, 180]`), `vehicle_positions` snapshot model with PostGIS GiST index, forward migration `0003_vehicle_positions`, atomic snapshot persistence, rollback preservation of previous snapshots, administrative CLI (`realtime-cli poll-vehicles`), and comprehensive test suite (86 total backend tests).
- **Stage 3, Slice 3.1**: Historical Vehicle Observation Storage (`VehicleObservation` model, forward migration `0004_vehicle_observations`), composite idempotency constraint on `(feed_id, entity_id, observed_at)` with deterministic timestamp fallback (`vehicle_timestamp` → `feed_timestamp` → server receipt time), atomic transaction combining current snapshot replacement and duplicate-sample deduplication, internal query helper `get_recent_observations(...)` with mandatory `since` bound and result capping, PostGIS spatial GiST indexing, and 9 new deterministic integration tests (96 total backend tests).
- **Stage 3, Slice 3.2**: Stop Arrival Predictions & ETA Engine (`ArrivalPredictionService`, endpoint `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`), GTFS calendar and calendar_dates active service evaluation, agency timezone resolution, extended-hour service times (>24:00) handling, downstream stop eligibility filtering based on vehicle `current_stop_sequence`, realtime telemetry freshness window enforcement (<= 300s), deterministic historical median delay calculation from `STOPPED_AT` observations at scheduled stops, transparent schedule fallback when history is absent, and 9 new comprehensive integration tests (105 total backend tests).
- **Stage 4, Slice 4.1**: Feed-Aware Transit Explorer & Live Arrivals (`apps/web` React/TypeScript SPA with TanStack Query and Zustand):
  - Enriched backend `GET /api/v1/feeds` returning bounded public UI metadata (`id`, `slug`, `city_name`, `feed_status`, `is_live_tracking_enabled`, `last_static_import_at`, `last_realtime_poll_at`) without exposing secrets, credentials, or private URLs.
  - Configurable backend API base URL via `VITE_API_URL` environment convention with `.env.example`.
  - Accessible, responsive UI components: `FeedSelector` with operational and live tracking badges, `StopSearch` with text filtering and wheelchair accessibility indicators, and `ArrivalsBoard` with scheduled/estimated arrival times, formatted delay badges (`+X min late`, `On time`, `X min early`), prediction source labels (`Live + History` vs `Schedule`), telemetry observation age, and agency timezone disclosure.
  - Strict feed isolation: switching transit feeds immediately resets the active stop and arrivals view to prevent cross-feed data leakage.
  - Comprehensive unit and integration test suite: 46 Vitest frontend tests across 5 files, and 105 backend Pytest tests.
- **Stage 4, Slice 4.2**: Interactive Map & Route Visualization:
  - Feed-scoped GTFS `shapes.txt` ingestion into new `shapes` PostGIS model with spatial GiST indexing and forward migration `0005_shapes`.
  - Read-only bounded route map endpoint (`GET /api/v1/feeds/{feed_slug}/routes/{route_id}/map`) returning true shape point sequences, ordered stops served, and fresh route-scoped vehicle positions with bearing and freshness window (<= 300s). Strict avoidance of fabricated geometry: routes without shapes return an empty shape list and a prominent warning.
  - Leaflet-based responsive map component (`MapView`) rendering true shape polylines in route colors, stop circle markers, and bearing-oriented live vehicle markers.
  - Configurable tile provider URL via `VITE_MAP_TILE_URL` (defaulting to OpenStreetMap standard tiles) with persistent attribution and documented usage policy.
  - Keyboard-accessible route selector (`RouteSelector`) and dual-tab stop/vehicle inspector panel (`MapDetailsPanel`).
  - Feed and route isolation: switching feeds clears active routes, stops, vehicles, and map layers.
  - Comprehensive test suite: 65 Vitest frontend tests and 114 Pytest backend tests.
- **Stage 4, Slice 4.3**: Realtime Polling & Live Map Refresh:
  - Added periodic client refresh for active stop arrivals and route vehicle positions with a conservative, configurable 30-second interval (`DEFAULT_POLLING_INTERVAL_MS = 30_000`, `VITE_POLLING_INTERVAL_SEC=30`).
  - Active-tab visibility management (`useDocumentVisibility`, `usePollingVisibilityRefresh`): pauses polling while the page or tab is hidden, and performs an immediate refresh on visibility return.
  - Strict selection scoping: polling runs only when relevant entities are selected (`feed + stop` for arrivals, `feed + route` for map and vehicle positions); switching feeds or routes immediately halts stale polling and prevents cross-feed data leakage.
  - Transient failure resilience: preserves the last successful predictions and vehicle positions on transient refresh errors, accompanied by a non-blocking warning banner, last updated timestamp (`formatLastUpdated`), "⚠️ Stale" status pill, and manual retry controls.
  - JSON API polling only: Leaflet map tiles are untouched during background polling, vector layers update in-place, and map bounds auto-fit only on initial route selection to maintain stable viewports.
  - Comprehensive test suite: 81 Vitest frontend tests across 6 files, and 114 Pytest backend tests.
- **Stage 4, Slice 4.4**: GTFS-Realtime TripUpdates Ingestion:
  - GTFS-RT TripUpdate model (`TripUpdate`) and forward migration `0006_trip_updates` storing feed-scoped stop-time predictions and trip cancellations.
  - Protocol buffer parser (`parse_trip_updates`) with `DIFFERENTIAL` incrementality rejection, duplicate entity ID validation, timestamp bounds enforcement, and defensive handling of partial descriptors.
  - Ingestion service (`TripUpdateIngestionService`) with atomic snapshot replacement, feed isolation, and graceful skip when `realtime_trip_updates_url` is omitted.
  - Combined poll lifecycle in `realtime-cli poll-vehicles`: fetches vehicle positions and configured TripUpdates in a single poll execution, while local `--file` mode remains fully offline without outbound network calls. Error isolation ensures failed TripUpdates download/parsing preserves previous snapshot state and does not lose processed vehicle observations. Retains `poll-trip-updates` as an operator fallback command.
  - Prediction service integration (`ArrivalPredictionService`): priority evaluation for `TRIP_UPDATE` prediction source, absolute event time precedence over delay (`time` > `delay`), departure fallback, trip cancellation (`CANCELED`) suppression, and skipped stop (`SKIPPED`) suppression, gracefully coexisting with vehicle positions and schedule fallbacks.
  - Frontend integration: `TRIP_UPDATE` prediction source formatting with prominent "Live TripUpdate" badge styling in `ArrivalsBoard`.
  - Comprehensive test suite: 82 Vitest frontend tests across 6 files, and 136 Pytest backend tests across 10 files.
- **Stage 4, Slice 4.5**: Docker Compose Production Scaffolding & Application Polish:
  - Multi-service Docker Compose topology (`db`, `migrate`, `api`, `web`) with pinned base images (`postgis/postgis:16-3.4`, `python:3.12-slim-bookworm`, `node:22-alpine3.20`, `nginx:1.30.6-alpine`).
  - Safe, non-root API containerization with unprivileged `waitwatch` runtime user and zero-dependency Python standard library health check.
  - Safe, isolated migration runner (`migrate` service) guaranteeing Alembic migrations execute once to completion before FastAPI serves requests, preventing competing migration processes on restart or scaling.
  - High-performance Nginx SPA runtime with gzip compression, long-term static asset caching, SPA client-side fallback, dedicated container health check, and internal reverse proxy for `/api/` traffic.
  - Integration gap polish: normalized `database_url` conversion from `postgresql://` to `postgresql+asyncpg://`, expanded CORS default origins to support Compose web port 3000, normalized API base URL trailing slashes and empty string relative paths, and documented browser networking constraints.
  - Safe, placeholder-only `.env.example` template without usable default credentials, accompanied by clear startup and security guidance.
  - Comprehensive test suite: 83 Vitest frontend tests across 6 files, and 138 Pytest backend tests across 10 files.
- **Stage 4, Slice 4.6**: Core WebSocket Live Updates:
  - Feed-scoped FastAPI WebSocket endpoint (`/api/v1/feeds/{feed_slug}/ws`) with feed validation, policy violation rejection (code 1008) for unknown or inactive feeds, and ping/pong heartbeats.
  - Zero-broker PostgreSQL `LISTEN/NOTIFY` pub/sub on channel `waitwatch_feed_updates` broadcasting lightweight `FeedUpdateEvent` payloads with UUID `event_id` on snapshot commit; rollback or failed transactions publish zero events.
  - Managed async database listener (`run_db_listener`) with single dedicated connection, exponential reconnection backoff, and graceful shutdown; thread-safe `ConnectionManager` with feed isolation, LRU event deduplication, and dead connection pruning.
  - React live update hook (`useFeedLiveUpdates`) with TanStack Query cache invalidation (`routeMap`, `arrivals`), active-tab visibility lifecycle management, exponential reconnect backoff, and seamless fallback to 30-second steady-state REST polling on disconnect, error, or hidden tabs (pauses redundant background polling while WebSocket is actively connected).
  - Accessible, responsive UI live status indicators (`● Live (WS)` vs `● Live (30s)` fallback vs `⏸ Paused` vs `⚠️ Stale`) across the dashboard, arrivals board, and interactive map view.
  - Protocol upgrade configuration in Vite development server proxy (`ws: true`) and Nginx reverse proxy (`map $http_upgrade $connection_upgrade` and `Upgrade`/`Connection` headers).
  - Comprehensive test suite: 93 Vitest frontend tests across 7 files, and 153 Pytest backend tests across 11 files.

## License

This project is under development. License information will be added in a future update.
