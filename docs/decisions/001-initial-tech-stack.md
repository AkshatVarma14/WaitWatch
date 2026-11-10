# ADR 001: Initial Technology Stack

## Status

**Accepted**

## Date

2026-11-10

## Context

WaitWatch is a real-time public transit tracking application that needs to be built within a five-day development constraint. The stack must support:

- Geospatial data storage and querying (transit routes, stop locations, vehicle positions)
- Real-time data processing (GTFS-Realtime vehicle position feeds)
- WebSocket communication for live updates to the browser
- Interactive map rendering with transit overlays
- Rapid development with strong type safety

The team has experience with both TypeScript and Python ecosystems.

## Decision

### Frontend

- **React** with **TypeScript** — Component-based UI with compile-time type safety
- **Vite** — Fast build tool with near-instant HMR for rapid development
- **Tailwind CSS** — Utility-first CSS for rapid UI development without writing custom stylesheets
- **TanStack Query** — Server state management with built-in caching, refetching, and request deduplication
- **Zustand** — Lightweight client state for UI preferences and selections

### Backend

- **FastAPI** (Python) — Async-first web framework with native WebSocket support and automatic OpenAPI documentation
- **Pydantic** — Request/response validation with automatic serialization
- **SQLAlchemy** — Mature ORM with async support and GeoAlchemy2 for PostGIS integration
- **Alembic** — Database migration management tied to SQLAlchemy models

### Database

- **PostgreSQL** — Reliable relational database for structured transit data
- **PostGIS** — Geospatial extension for efficient location-based queries (nearby stops, distance calculations, geometry storage)

### Testing

- **Vitest** — Frontend testing, natively integrated with Vite
- **Pytest** — Backend testing with async support and fixture management

### CI/CD

- **GitHub Actions** — Automated test runs and deployment pipelines

## Rationale

- **PostGIS over application-level geo calculations**: Transit data is inherently geospatial. PostGIS provides optimized spatial indexes, distance functions, and geometry operations at the database level, which is significantly more efficient than calculating distances in application code.

- **FastAPI over Django/Flask**: FastAPI's native async support is critical for WebSocket connections and concurrent GTFS-RT feed polling. Built-in OpenAPI documentation accelerates frontend development. Performance is superior for I/O-bound workloads.

- **TanStack Query + Zustand over Redux**: Separating server state (TanStack Query) from client state (Zustand) reduces boilerplate and complexity. TanStack Query handles caching and synchronization automatically. Zustand is minimal for the small amount of client-only state needed.

- **Vite over Webpack/CRA**: Vite's fast startup and HMR are essential for the tight development timeline. Native TypeScript support without additional configuration.

- **Python backend over Node.js**: Python has mature GTFS parsing libraries and strong data processing capabilities. FastAPI's async performance is competitive with Node.js for I/O-bound workloads.

## Consequences

- **Team must be proficient in both TypeScript and Python** — the frontend and backend use different languages
- **PostgreSQL with PostGIS is required** — a simple SQLite database cannot substitute due to geospatial requirements
- **Two test runners** must be maintained (Vitest for frontend, Pytest for backend)
- **Docker is recommended** for local development to simplify PostGIS setup
- The chosen stack is well-documented and widely used, reducing risk of encountering obscure issues during the five-day build
