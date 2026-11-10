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

### 1. GTFS Static Ingestion Service — `Planned`

Downloads GTFS static feeds (ZIP archives containing CSV files), parses them according to the GTFS specification, and populates the database with routes, stops, trips, stop times, calendar entries, and route shapes. Runs on-demand or on a configurable schedule to keep data current.

### 2. GTFS-Realtime Service — `Planned`

Polls GTFS-Realtime feeds at regular intervals (e.g., every 15–30 seconds) for vehicle position updates and trip update messages. Parses the Protocol Buffer responses and stores current vehicle positions in the database. Triggers WebSocket broadcasts to connected clients.

### 3. ETA Prediction Service — `Planned`

Calculates estimated arrival times at stops using:
- Current live vehicle position and speed
- Scheduled stop times from GTFS static data
- Historical delay patterns for the same route/time-of-day/day-of-week

Produces ETA updates that are broadcast via WebSocket to subscribed clients.

### 4. REST API — `Partial`

Currently implemented:
- Health check / root endpoint

Planned endpoints:
- `GET /routes` — list all routes with optional filtering
- `GET /routes/{id}` — route details with shape geometry
- `GET /stops` — list stops, with geospatial proximity search
- `GET /stops/{id}` — stop details with upcoming arrivals
- `GET /trips/{id}` — trip details with stop times
- `GET /vehicles` — current vehicle positions
- `GET /eta/{stop_id}` — predicted arrival times for a stop

### 5. WebSocket Server — `Planned`

Provides real-time updates to connected clients:
- Vehicle position broadcasts (all vehicles or filtered by route)
- ETA updates for subscribed stops
- Service alerts and disruption notifications

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

## Technology Rationale

| Technology | Rationale |
|-----------|-----------|
| **PostGIS** | Enables efficient geospatial queries — finding nearby stops within a radius, calculating distances between vehicles and stops, and storing/querying route shape geometries. Essential for a location-centric transit application. |
| **FastAPI** | High-performance async Python framework with native WebSocket support. Automatic OpenAPI documentation generation. Strong Pydantic integration for request/response validation. Excellent async support for I/O-bound database and network operations. |
| **TanStack Query** | Manages server state on the frontend with automatic caching, background refetching, stale-while-revalidate patterns, and request deduplication. Eliminates boilerplate for data fetching and keeps the UI responsive. |
| **Zustand** | Lightweight client state management for UI concerns (selected route, map viewport, user preferences). Minimal boilerplate compared to Redux. Does not replace TanStack Query for server state — each tool handles its appropriate domain. |
| **SQLAlchemy + Alembic** | Mature ORM with GeoAlchemy2 for PostGIS column types and spatial queries. Alembic provides reliable database migration management tied to the SQLAlchemy model definitions. |
| **Vite** | Fast development server with hot module replacement. Near-instant startup compared to Webpack. Native TypeScript and JSX support. |

## Current Status

**Stage 0 (Project Foundation) and Stage 1, Slice 1.1 (Database Foundation & Transit Models) are implemented**:

- Repository structure and monorepo layout
- Frontend scaffolding (React + Vite + TypeScript + Tailwind CSS + TanStack Query + Zustand)
- Backend scaffolding (FastAPI + Pydantic + SQLAlchemy async + Alembic)
- Database connection lifecycle with credential sanitization and real non-leaking health checks
- 8 transit-domain SQLAlchemy models with multi-city support and PostGIS geospatial types
- Initial Alembic migration (`0001_initial_transit_models`) with explicit PostGIS extension setup
- Unit test suites for frontend (Vitest) and backend (Pytest, 18 tests)
- CI/CD pipeline configuration with automated GitHub Actions

The GTFS static ingestion pipeline, real-time tracking, map UI, and ETA prediction are **planned for subsequent stages/slices**.
