# 🚌 WaitWatch

**Real-time public transit tracking**

## Problem Statement

Public transit riders often lack accurate, real-time information about vehicle locations and arrival times. Existing apps may not cover all cities or provide reliable predictions. Riders are left guessing whether their bus is around the corner or still twenty minutes away.

WaitWatch aims to solve this by ingesting standardized GTFS and GTFS-Realtime data, displaying live vehicle positions on an interactive map, and providing estimated arrival times based on real-time tracking and historical delay patterns.

## Features (Planned)

> All features listed below are **planned** and not yet implemented. The project is currently in the foundation stage.

- 📍 **Route and stop exploration** — Browse transit routes and stops on an interactive map
- 📅 **Static schedule display** — View trip schedules sourced from GTFS data
- 🚌 **Live vehicle tracking** — See real-time vehicle positions via GTFS-Realtime feeds
- ⏱️ **ETA predictions** — Get estimated arrival times using live vehicle positions and historical delay data
- 🌍 **Multi-city support** — Configure different transit feeds to track multiple cities

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

### Database (Optional Docker Setup)

If you don't have a local PostgreSQL/PostGIS installation:

```bash
docker compose up -d
```

This starts a PostGIS-enabled PostgreSQL container with the configuration from your `.env` file.

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
| Stage 4 | UI polish and deployment | 🟡 In Progress (Slice 4.1 Complete) |

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

## License

This project is under development. License information will be added in a future update.
