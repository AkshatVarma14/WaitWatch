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
| Stage 1 | GTFS static data ingestion | 🔄 In Progress (Slice 1.1 Complete) |
| Stage 2 | GTFS-Realtime integration | ⬜ Not started |
| Stage 3 | ETA prediction | ⬜ Not started |
| Stage 4 | UI polish and deployment | ⬜ Not started |

### Completed Milestones
- **Stage 0**: Full foundation with React/TS/Tailwind frontend, FastAPI backend, CI workflows, and documentation.
- **Stage 1, Slice 1.1**: Database foundation, PostgreSQL/PostGIS connection handling, transit data models (`TransitFeed`, `Agency`, `Route`, `Stop`, `Trip`, `StopTime`, `Calendar`, `CalendarDate`), and initial Alembic migration (`0001_initial_transit_models`).

## License

This project is under development. License information will be added in a future update.
