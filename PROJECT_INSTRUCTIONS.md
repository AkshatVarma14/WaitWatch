# WaitWatch — Project Instructions

## Project Overview

**WaitWatch** is a web-first real-time public transit tracking application.

### The Problem

Public transit riders frequently lack real-time visibility into where vehicles actually are and when they will arrive. Existing solutions may not cover all cities, may rely solely on static schedules, or fail to provide reliable arrival predictions. Riders are left waiting at stops without knowing if their bus is two minutes away or twenty.

### The Solution

WaitWatch ingests standardized transit data (GTFS and GTFS-Realtime), displays routes and stops on an interactive map, shows live vehicle positions, and calculates estimated arrival times using a combination of real-time vehicle positions and historical delay patterns.

## Functional Objectives

1. **Ingest and serve GTFS static data** — Parse GTFS feeds to populate the database with routes, stops, trips, stop times, calendar entries, and route shapes
2. **Ingest GTFS-Realtime feeds** — Poll GTFS-RT feeds for live vehicle positions and trip updates, storing them for display and analysis
3. **Display transit routes and stops on an interactive map** — Render route shapes, stop locations, and relevant transit information in a map-based UI
4. **Show live vehicle positions** — Display real-time vehicle locations on the map, updated via WebSocket
5. **Calculate and display ETA predictions** — Estimate arrival times at stops using live vehicle positions, schedule data, and historical delay patterns
6. **Support multiple cities** — Allow configuration of different GTFS/GTFS-RT feed URLs to support transit agencies across multiple cities

## System Architecture

```
┌─────────────────┐     REST / WebSocket     ┌─────────────────┐     SQL      ┌──────────────────┐
│   React SPA     │ ◄──────────────────────► │  FastAPI Server  │ ◄──────────► │ PostgreSQL/PostGIS│
│  (Vite + TS)    │                          │  (Python)        │              │                  │
└─────────────────┘                          └────────┬─────────┘              └──────────────────┘
                                                      │
                                             ┌────────┴─────────┐
                                             │  Background      │
                                             │  Services        │
                                             │  • GTFS Ingest   │
                                             │  • RT Polling    │
                                             │  • ETA Engine    │
                                             └──────────────────┘
```

- **React SPA** — The user-facing frontend communicates with the backend via REST API for data queries and WebSocket for real-time updates
- **FastAPI Server** — Serves the REST API, manages WebSocket connections, and orchestrates background services
- **PostgreSQL/PostGIS** — Stores all transit data with geospatial indexing for efficient location-based queries
- **Background Services** — GTFS ingestion runs on-demand or on schedule; GTFS-RT polling runs continuously; ETA prediction runs on incoming position updates

## Approved Technology Decisions

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Frontend Framework | React + TypeScript | Component-based UI with strong type safety |
| Build Tool | Vite | Fast development builds and HMR |
| CSS | Tailwind CSS | Utility-first styling, rapid UI development |
| Server State | TanStack Query | Automatic caching, refetching, and request deduplication for API data |
| Client State | Zustand | Lightweight store for UI preferences, selected routes, and local state |
| Backend Framework | FastAPI | High-performance async Python framework with native WebSocket support and automatic OpenAPI docs |
| Validation | Pydantic | Data validation and serialization for API contracts |
| ORM | SQLAlchemy | Mature Python ORM with PostGIS support via GeoAlchemy2 |
| Migrations | Alembic | Database schema version control integrated with SQLAlchemy |
| Database | PostgreSQL + PostGIS | Reliable relational database with geospatial query capabilities |
| Frontend Tests | Vitest | Fast test runner, native Vite integration |
| Backend Tests | Pytest | Standard Python testing with async support |
| CI/CD | GitHub Actions | Automated testing and deployment pipelines |

## Development Stages

### Stage 0: Project Initialization and Foundation

- Repository setup with monorepo structure
- Frontend scaffolding (React + Vite + TypeScript + Tailwind)
- Backend scaffolding (FastAPI project structure)
- CI/CD pipeline configuration
- Documentation foundation
- Environment configuration templates

### Stage 1: GTFS Static Data

- PostgreSQL/PostGIS database schema for GTFS entities (routes, stops, trips, stop_times, calendar, shapes)
- GTFS feed download and parsing pipeline
- Database ingestion from parsed GTFS data
- REST API endpoints: routes, stops, schedules, trips
- Alembic migration setup
- Unit and integration tests for ingestion and API

### Stage 2: GTFS-Realtime Integration

- GTFS-Realtime protobuf feed parsing
- Vehicle position ingestion and storage
- Trip update processing
- Live vehicle tracking REST endpoint
- WebSocket server setup for real-time position broadcasts
- Frontend map integration for vehicle display

### Stage 3: ETA Prediction

- Historical delay data collection and storage
- Arrival time estimation algorithm using live positions and historical patterns
- ETA API endpoint
- WebSocket broadcast of ETA updates
- Frontend ETA display components

### Stage 4: UI Polish and Deployment

- Map visualization improvements (route shapes, stop markers, vehicle icons)
- Multi-city support through configurable feed selection
- Responsive design and mobile-friendly layout
- Error handling and loading states
- Deployment configuration (Docker Compose, environment setup)
- Final documentation updates

## Five-Day Time Constraint

This project is designed to be built in approximately five days, with roughly one stage per day:

| Day | Stage | Focus |
|-----|-------|-------|
| 1 | Stage 0 | Foundation and scaffolding |
| 2 | Stage 1 | GTFS static data pipeline |
| 3 | Stage 2 | Real-time vehicle tracking |
| 4 | Stage 3 | ETA predictions |
| 5 | Stage 4 | Polish and deployment |

**Key principle: Prioritize working functionality over polish.** A feature that works end-to-end with basic UI is more valuable than a perfectly styled component with no backend.

## Scope and Prioritization

### In Scope (Five-Day Build)

- Web application (browser-based)
- GTFS and GTFS-Realtime data processing
- Interactive map with routes, stops, and vehicles
- ETA predictions
- Single or multi-city support via configuration
- Docker-based local development

### Out of Scope (Future Phases)

- Native mobile application (React Native or similar)
- User accounts and authentication
- Push notifications
- Offline support
- Trip planning / routing
- Fare information

### Prioritization

1. **Working code over perfect code** — get it functional first
2. **Core transit tracking** over nice-to-have features
3. **Web-first** — mobile expansion planned for future phases
4. **Test coverage for critical paths** — don't test every CSS class

## Implementation Standards

- **TypeScript strict mode** — compiler enforces type safety, no `any`
- **Python type hints** — all functions fully annotated
- **Pydantic validation** — all API request and response models use Pydantic
- **Async database operations** — use SQLAlchemy async engine and sessions
- **Environment-based configuration** — all secrets and connection strings via environment variables
- **Consistent error responses** — standardized error format across all API endpoints

## Testing Standards

- **All API endpoints** must have at least one test covering the happy path
- **Critical frontend logic** (data transformations, state management) must be tested
- **CI must pass** — the GitHub Actions pipeline runs all tests on every push
- **Test with realistic data** — use sample GTFS data in test fixtures, not empty mocks

## Stage Approval

Each stage must be verified against its acceptance criteria before proceeding to the next:

1. All planned functionality for the stage is implemented
2. Tests are written and passing
3. CI pipeline is green
4. Documentation is updated to reflect changes
5. No critical bugs or regressions

**Do not begin the next stage until the current stage is approved.**

## Documentation

Keep the following documentation updated as implementation progresses:

- `README.md` — project overview, setup instructions, current status
- `docs/architecture/overview.md` — system architecture and component descriptions
- `docs/decisions/` — architectural decision records for significant choices
- API documentation is auto-generated by FastAPI's OpenAPI integration

## Web-First Approach

The initial product is a **web application** accessed through a browser. The architecture is designed with future mobile expansion in mind:

- REST API is client-agnostic — a mobile app can use the same endpoints
- WebSocket protocol is standard — mobile clients can subscribe to the same feeds
- Business logic lives in the backend — mobile clients would be a thin UI layer

Mobile expansion (React Native or similar) is planned for future phases **beyond the five-day constraint** and is explicitly out of scope for the initial build.
