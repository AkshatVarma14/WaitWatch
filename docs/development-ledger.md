# WaitWatch — Development Ledger

This document tracks verified stage milestones, implementation slices, verification evidence, and next authorized steps.

---

## Stage 0: Project Foundation (Completed & Verified)

- **Date**: 2026-11-10
- **Scope**: Repository initialization, frontend (React + Vite + TypeScript + Tailwind + TanStack Query + Zustand) foundation, backend (FastAPI + Pydantic + SQLAlchemy + Alembic) foundation, CI workflows, and project documentation.
- **Commit**: `0f26fa1a27ec149eecaa218cd1ed11bb88b95118`
- **Branch**: `main`
- **CI Status**: Both `Frontend CI` (Run ID: 42774858305) and `Backend CI` (Run ID: 42774658655) passed on GitHub Actions.
- **Accepted Criteria**: All 15 criteria verified PASS.

---

## Stage 1: GTFS Static Data Ingestion

### Slice 1.1: Database Foundation & Transit Data Models (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Establish the database foundation, async connection lifecycle, and SQLAlchemy models for transit entities with multi-city support and PostGIS geospatial design. Do not implement ZIP ingestion yet.

#### Implemented Components
1. **Database Engine & Lifecycle** (`apps/api/app/database/session.py`):
   - Async engine with pool pre-ping and environment-based configuration.
   - FastAPI `get_session()` dependency with automatic error rollback and cleanup.
   - Non-leaking `check_database_connection()` function providing real database status without exposing credentials.
   - Sanitized database URL masking password for logging.
   - Safe SQLite compilation rule for GeoAlchemy2 `Geography` to enable zero-dependency unit tests.
2. **Transit Domain Models** (`apps/api/app/models/`):
   - `TransitFeed`: Multi-city configuration, feed URLs, environment variable key reference, operational status, tracking toggle, and timestamps.
   - `Agency`: Transit agency mapped to feed, original GTFS `agency_id`, timezone, contact information, and uniqueness scoped to `(feed_id, agency_id)`.
   - `Route`: Transit route mapped to agency and feed, route type, colors, and uniqueness scoped to `(feed_id, route_id)`.
   - `Stop`: Transit stop with coordinates, parent station hierarchy, and PostGIS `Geography(POINT, 4326)` with GiST index.
   - `Trip`: Individual journey along a route with service ID, direction, block, shape ID, and accessibility flags.
   - `StopTime`: Scheduled arrival and departure times (preserving GTFS time semantics) with trip sequence and stop relationships.
   - `Calendar`: Weekly service pattern (Mon-Sun booleans, date range).
   - `CalendarDate`: Service exception dates and types (added/removed).
3. **Alembic Migration** (`apps/api/alembic/versions/0001_initial_transit_models.py`):
   - Reproducible initial migration creating all 8 tables, indexes, constraints, foreign keys, and explicit PostGIS extension setup.
   - Fully reversible downgrade dropping tables in correct dependency order.
   - Configured `env.py` to bind to application settings and load model metadata.
4. **Comprehensive Test Suite** (`apps/api/tests/`):
   - 18 tests across `test_models.py`, `test_database.py`, `test_alembic.py`, and `test_api.py`.
   - All tests run without requiring a live PostgreSQL instance or network credentials.
   - Verified that missing database returns `database: "unavailable"` without error.

#### Verification Evidence
- **Pytest**: 18 tests passed in 5.34s (`py -3.12 -m pytest tests -v`).
- **Ruff**: Zero errors across `app/`, `tests/`, and `alembic/`.
- **Python Compilation**: All modules in `app/`, `tests/`, and `alembic/` compile cleanly with Python 3.12.
- **Alembic Offline Validation**:
  - `alembic upgrade head --sql` passed and generated clean DDL.
  - `alembic downgrade 0001_initial_transit_models:base --sql` passed and generated clean drop DDL.
- **Frontend Regression**:
  - `npm test`: 2 test files, 6 tests passed in 2.57s.
  - `npm run build`: built in 1.62s without errors.

#### Changed Files
- `apps/api/app/core/config.py` (added `sanitized_database_url` and timeout)
- `apps/api/app/database/session.py` (added real health check, SQLite fallback, session lifecycle)
- `apps/api/app/api/health.py` (integrated real database connectivity check)
- `apps/api/app/main.py` (safe sanitized DB URL logging during startup)
- `apps/api/app/models/feed.py` (new `TransitFeed` model)
- `apps/api/app/models/agency.py` (new `Agency` model)
- `apps/api/app/models/route.py` (new `Route` model)
- `apps/api/app/models/stop.py` (new `Stop` model with PostGIS Geography)
- `apps/api/app/models/trip.py` (new `Trip` model)
- `apps/api/app/models/stop_time.py` (new `StopTime` model)
- `apps/api/app/models/calendar.py` (new `Calendar` and `CalendarDate` models)
- `apps/api/app/models/__init__.py` (exported all models and Base)
- `apps/api/alembic.ini` (configured `path_separator = os`)
- `apps/api/alembic/env.py` (integrated model metadata and application settings)
- `apps/api/alembic/versions/0001_initial_transit_models.py` (initial migration)
- `apps/api/tests/test_models.py` (model structure and relationship tests)
- `apps/api/tests/test_database.py` (session lifecycle, sanitization, SQLite tests)
- `apps/api/tests/test_alembic.py` (Alembic configuration and discovery tests)
- `docs/database/database-design.md` (database architecture and schema specifications)
- `docs/architecture/overview.md` (updated implementation status)
- `README.md` (updated development status)
- `docs/development-ledger.md` (this ledger)

#### Next Authorized Step
- **Stage 1, Slice 1.2**: GTFS Static Ingestion Pipeline (Completed below).

---

### Slice 1.2: Static GTFS Ingestion Pipeline (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement the GTFS static ingestion pipeline: safe archive inspection, resilient streaming download, CSV parsing with full GTFS Schedule compliance, feed-scoped transactional persistence, forward migration for optional `agency_id`, and administrative CLI.

#### Implemented Components
1. **Forward Alembic Migration** (`apps/api/alembic/versions/0002_optional_agency_id.py`):
   - Modifies `agencies.agency_id` to `nullable=True` to support single-agency GTFS Schedule feeds where `agency_id` is omitted per official specification.
   - Tested full forward upgrade and reverse downgrade static SQL generation.
2. **Safe Archive Inspector** (`apps/api/app/services/gtfs/archive.py`):
   - In-memory ZIP inspection preventing disk exhaustion and security hazards.
   - Threshold checks: max archive size (100MB), max uncompressed size (500MB), max entry count (100).
   - Decompression bomb protection with strict compression ratio threshold (100:1).
   - Directory traversal protection (rejection of `..`, absolute paths, leading slashes, null bytes).
   - Encryption rejection (rejects password-protected / encrypted zip entries).
   - In-memory extraction with UTF-8 BOM auto-stripping.
3. **Resilient Streaming Downloader** (`apps/api/app/services/gtfs/downloader.py`):
   - Streaming HTTP download via `httpx.AsyncClient` enforcing chunk-level byte size bounds and finite connect/read timeouts.
   - Redaction of user credentials and sensitive query parameters (`key`, `api_key`, `token`, `secret`) in log output and error messages.
   - Support for optional API key authentication headers referenced by feed configuration.
4. **GTFS Schedule Parser & Validator** (`apps/api/app/services/gtfs/parser.py`):
   - Strict GTFS Schedule specification adherence.
   - Support for valid single-agency feeds omitting `agency_id`, automatically resolving route references.
   - Multi-agency feed validation requiring matching `agency_id` cross-references.
   - Full preservation of post-midnight service-day times (e.g. `24:15:00`, `25:35:00`) normalized to standard 8-character `HH:MM:SS`.
   - Comprehensive schedule support: valid with `calendar.txt`, `calendar_dates.txt` only, or both.
   - Strict validation: coordinate bounds (`[-90, 90]`, `[-180, 180]`), primary key uniqueness, foreign key cross-file referential integrity (routes, stops, parent stations, trips, stop times).
5. **Feed-Scoped Atomic Persistence** (`apps/api/app/services/gtfs/importer.py`):
   - Feed isolation: all operations strictly scoped to `feed_id`.
   - Idempotent replacement: clears existing records for the feed in reverse foreign key order (`stop_times` → `trips` → `routes` → `stops` → `calendar_dates` → `calendars` → `agencies`).
   - Inserts new records in foreign key order, establishing synthetic database primary keys.
   - Platform/parent-station hierarchy resolution.
   - High-volume batch persistence for `stop_times` in bounded chunks of 1,000 rows.
   - Updates `TransitFeed.last_static_import_at` and sets `feed_status = 'active'`.
6. **Orchestrator Service & Administrative CLI** (`apps/api/app/services/gtfs/service.py`, `apps/api/app/services/gtfs/cli.py`):
   - `GTFSIngestionService`: Coordinates extraction, parsing, and database transactions with atomic rollback on any failure.
   - CLI entrypoint (`python -m app.services.gtfs.cli ingest --feed-id <ID> [--file <PATH>] [--batch-size 1000]`) avoiding unauthenticated public endpoints.
7. **Comprehensive Ingestion Test Suite** (`apps/api/tests/test_gtfs_ingestion.py`):
   - 24 new unit and integration tests covering:
     - Archive safety (valid extraction, corrupt archives, size bounds, traversal, bombs, encryption).
     - Downloader streaming, timeout, HTTP error, credential masking.
     - GTFS parsing rules (single agency, multi agency, times >= 24h, calendar dates only, coordinates, duplicates, broken FKs).
     - Transactional persistence and idempotent replacement using async in-memory SQLite.
     - Atomic rollback verification preserving prior data on error.
     - CLI argument handling and execution.

#### Verification Evidence
- **Pytest**: 42 tests passed in 5.79s (`py -3.12 -m pytest tests -v`).
- **Ruff**: Zero errors across `app/`, `tests/`, and `alembic/`.
- **Python Compilation**: All modules in `app/`, `tests/`, and `alembic/` compile cleanly with Python 3.12.
- **Alembic Offline Validation**:
  - `alembic upgrade head --sql` passed and generated clean DDL including `0002_optional_agency_id`.
  - `alembic downgrade 0002_optional_agency_id:0001_initial_transit_models --sql` passed and restored `NOT NULL`.
- **Frontend Regression**:
  - `npm.cmd test -- --run`: 2 test files, 6 tests passed in 4.03s.
  - `npm.cmd run typecheck`: clean with zero errors.
  - `npm.cmd run build`: production build passed in 2.16s without errors.

#### Changed / Added Files
- `apps/api/app/models/agency.py` (updated `agency_id` to nullable)
- `apps/api/app/database/session.py` (added SQLite fallback compilation for `ST_GeogFromText` and `ST_AsBinary`)
- `apps/api/alembic/versions/0002_optional_agency_id.py` (new migration for optional agency_id)
- `apps/api/app/services/gtfs/__init__.py` (package exports)
- `apps/api/app/services/gtfs/exceptions.py` (ingestion exception hierarchy)
- `apps/api/app/services/gtfs/archive.py` (safe in-memory ZIP inspection and extraction)
- `apps/api/app/services/gtfs/downloader.py` (streaming HTTP download and credential masking)
- `apps/api/app/services/gtfs/parser.py` (GTFS Schedule validation and CSV parsing)
- `apps/api/app/services/gtfs/importer.py` (feed-scoped batch database persistence)
- `apps/api/app/services/gtfs/service.py` (ingestion orchestration service)
- `apps/api/app/services/gtfs/cli.py` (administrative CLI command)
- `apps/api/pyproject.toml` (added `httpx` to dependencies and `aiosqlite` to dev)
- `apps/api/tests/test_gtfs_ingestion.py` (24 new comprehensive tests)
- `apps/api/tests/test_alembic.py` (updated migration head verification to 0002)
- `apps/api/tests/test_models.py` (updated agency_id nullable assertion)
- `docs/database/database-design.md` (documented migration 0002 and ingestion batching strategy)
- `docs/architecture/overview.md` (updated GTFS Static Ingestion Service status to Implemented)
- `README.md` (updated development status and milestones)
- `docs/development-ledger.md` (this ledger)

#### Next Authorized Step
- **Stage 1, Slice 1.3**: Transit Query API & Route/Stop Exploration Endpoints (Completed below).

---

### Slice 1.3: Transit Query API and Route/Stop Exploration (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement read-only FastAPI endpoints for exploring static transit data scoped to a `TransitFeed` slug (`/api/v1/feeds/{feed_slug}/...` and backwards-compatible `/api/feeds/{feed_slug}/...`), exposing GTFS string IDs, bounded pagination envelopes, PostGIS geospatial proximity exploration, feed isolation, and non-leaking database error handling.

#### Implemented Components
1. **Pydantic Response Schemas & Envelopes** (`apps/api/app/schemas/transit.py`):
   - `PaginationMeta`: Bounded pagination metadata (`total`, `page`, `page_size`, `total_pages`, `has_next`, `has_prev`).
   - `PaginatedResponse[T]` & `ItemEnvelope[T]`: Standard data wrapping envelopes.
   - `RouteResponse` & `RouteDetailResponse`: Exposing GTFS `route_id`, names, type, colors, and nested operating agency details.
   - `StopResponse` & `StopDetailResponse`: Exposing GTFS `stop_id`, code, coordinates, location/accessibility attributes, and resolved `parent_station_id` (GTFS string identifier).
   - `NearbyStopResponse`: Inherits from `StopResponse` with computed `distance_meters`.
   - `FeedSummaryResponse` & `FeedDetailResponse`: City, slug, feed URLs, and operational status.
2. **Read-Only Transit Query Endpoints** (`apps/api/app/api/transit.py`):
   - `GET /feeds`: List configured feeds with summary status.
   - `GET /feeds/{feed_slug}`: Specific feed metadata.
   - `GET /feeds/{feed_slug}/routes`: List & search routes with optional `q` text search across short/long name, `route_type` integer filter, `agency_id` filter, and bounded pagination (default 20, max 100). Uses `joinedload(Route.agency)` for performance.
   - `GET /feeds/{feed_slug}/routes/{route_id}`: Detail view for a route by its GTFS string ID.
   - `GET /feeds/{feed_slug}/stops`: List & search stops with `q` text search across name, code, or stop ID, and bounded pagination. Uses `joinedload(Stop.parent_station)`.
   - `GET /feeds/{feed_slug}/stops/nearby`: Geospatial proximity search with WGS84 coordinates (`latitude`, `longitude`), `radius_meters` (max 50,000m), and `limit` (max 100). Declared before `{stop_id}` to avoid routing conflict. Uses PostGIS `ST_DWithin` and `ST_Distance` on PostgreSQL, with an automatic bounding box + haversine distance fallback on SQLite.
   - `GET /feeds/{feed_slug}/stops/{stop_id}`: Detail view for a stop by its GTFS string ID.
   - Registered under `/v1` prefix and unprefixed for backwards compatibility in `apps/api/app/api/router.py`.
3. **Database Unavailable Sanitization** (`apps/api/app/main.py`):
   - Global exception handlers for `OperationalError` and `DBAPIError` mapping to HTTP 503 `{"detail": "Database service is temporarily unavailable"}` without exposing internal database credentials or connection strings in logs or response bodies.
4. **Comprehensive API Test Suite** (`apps/api/tests/test_transit_api.py`):
   - 17 new tests covering feed listing/detail/404, route listing/detail/isolation/filters, stop listing/detail/isolation, nearby stops with distance sorting, coordinate validation bounds, database 503 error handling, and backwards-compatible routing.

#### Verification Evidence
- **Pytest**: 59 tests passed in 7.28s (`py -3.12 -m pytest tests -v`).
- **Ruff**: Zero lint errors and clean formatting across `app/`, `tests/`, and `alembic/` (`py -3.12 -m ruff check app tests alembic` and `py -3.12 -m ruff format --check app tests alembic`).
- **Python Compilation**: All backend modules compile cleanly (`py -3.12 -m compileall app tests alembic`).
- **Alembic Offline Validation**: `alembic upgrade head --sql` passed and generated clean DDL.
- **Frontend Regression**:
  - `npm.cmd test -- --run`: 2 test files, 6 tests passed in 3.32s.
  - `npm.cmd run build`: production build passed in 2.42s without errors.

#### Changed / Added Files
- `apps/api/app/schemas/transit.py` (new Pydantic schemas and envelopes)
- `apps/api/app/schemas/__init__.py` (re-exported transit schemas)
- `apps/api/app/api/transit.py` (new router with feed, route, stop, and nearby endpoints)
- `apps/api/app/api/router.py` (registered transit router under `/v1` and unprefixed)
- `apps/api/app/main.py` (added database error sanitization exception handlers)
- `apps/api/tests/test_transit_api.py` (17 new endpoint integration tests)
- `docs/architecture/overview.md` (updated REST API status)
- `README.md` (updated development status and milestones)
- `docs/development-ledger.md` (this ledger)

#### Next Authorized Step
- **Stage 1 Conclusion / Stage 2 Preparation**: Await authorization for the next stage or slice in accordance with project instructions.
