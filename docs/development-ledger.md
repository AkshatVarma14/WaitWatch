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
- **Stage 2, Slice 2.1**: GTFS-Realtime Vehicle-Position Ingestion (Completed below).

---

## Stage 2: GTFS-Realtime Integration

### Slice 2.1: GTFS-Realtime Vehicle-Position Ingestion (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement GTFS-Realtime vehicle-position ingestion using official MobilityData Protocol Buffer bindings (`gtfs_realtime_pb2.FeedMessage`), FeedHeader incrementality validation with explicit `DIFFERENTIAL` mode rejection, coordinate and entity validation, current-state snapshot database persistence with spatial GiST indexing, transactional rollback preservation of previous snapshots, administrative CLI, and comprehensive test suite.

#### Implemented Components
1. **Database Model & Migration** (`apps/api/app/models/vehicle_position.py`, `apps/api/alembic/versions/0003_vehicle_positions.py`):
   - `VehiclePosition` model with feed foreign key (`transit_feeds.id`, cascade delete).
   - Source strings for GTFS identifiers (`trip_id`, `route_id`, `stop_id`) ensuring partial or unscheduled telemetry is accepted without foreign key constraints.
   - Vehicle descriptors (`vehicle_id`, `vehicle_label`, `license_plate`).
   - Movement telemetry (`latitude`, `longitude`, `bearing`, `speed`, `odometer`).
   - PostGIS geography column (`point = Geography(geometry_type="POINT", srid=4326)`) with GiST spatial index.
   - Distinct timestamps: `feed_timestamp` (from `FeedHeader.timestamp`), `vehicle_timestamp` (from `VehiclePosition.timestamp`), and server receipt time `recorded_at`.
   - Forward migration `0003_vehicle_positions` generating clean upgrade and downgrade DDL.
2. **Official Protocol Buffer Parser & Validator** (`apps/api/app/services/realtime/parser.py`):
   - Decodes protobuf messages using official `gtfs_realtime_pb2.FeedMessage`.
   - Validates `FeedHeader` presence, version string, and plausible timestamps.
   - Enforces `FULL_DATASET` incrementality; explicitly rejects `DIFFERENTIAL` incrementality with `UnsupportedIncrementalityError`.
   - Entity validation: rejects blank or duplicate entity IDs.
   - Strict coordinates validation: non-finite check and WGS84 bounds `[-90.0, 90.0]` / `[-180.0, 180.0]`.
   - Validates kinematic fields: bearing `[0.0, 360.0]`, non-negative speed and odometer.
   - Skips non-vehicle entities (trip updates, alerts) and deleted entities cleanly.
3. **Resilient HTTP Downloader** (`apps/api/app/services/realtime/downloader.py`):
   - Streaming HTTP client (`httpx.AsyncClient`) with finite connect/read timeouts (default 20s) and bounded size limits (default 50MB).
   - Automatic credential masking in log messages and URLs via `mask_url_credentials`.
   - Dynamic API key header resolution from `TransitFeed.api_key_env_var` reference.
4. **Current-State Snapshot Ingestion Service** (`apps/api/app/services/realtime/service.py`):
   - `VehiclePositionIngestionService`: Atomically replaces existing vehicle positions for the target `feed_id`.
   - Atomic rollback: preserves previous snapshot on any download, parsing, validation, or database failure.
   - Updates `TransitFeed.last_realtime_poll_at` only after successful database commit.
5. **Administrative CLI** (`apps/api/app/services/realtime/cli.py`):
   - Command: `python -m app.services.realtime.cli poll-vehicles --feed-id <ID> | --slug <SLUG> [--file <PATH>]`.
   - Operator execution without exposing unauthenticated public endpoints.
6. **Comprehensive Realtime Test Suite** (`apps/api/tests/test_realtime_ingestion.py`):
   - 26 unit and integration tests covering:
     - Fully-populated and minimal vehicle positions.
     - Multiple vehicles and absent optional descriptors.
     - Ignored non-vehicle entities and deleted records.
     - Empty, corrupted, and missing-header payloads.
     - Explicit rejection of `DIFFERENTIAL` mode.
     - Duplicate entity IDs, blank IDs, missing positions.
     - Out-of-bounds coordinates (lat, lon, NaN, inf) and invalid bearings/speeds.
     - Downloader credential masking, timeouts, and size limit enforcement.
     - Atomic snapshot replacement and rollback preservation of prior snapshots.
     - Administrative CLI arguments and local file ingestion.

#### Verification Evidence
- **Pytest**: 86 tests passed in 8.99s (`py -3.12 -m pytest tests -v`).
- **Ruff**: Zero lint errors and clean formatting across `app/`, `tests/`, and `alembic/` (49 files checked).
- **Python Compilation**: All backend modules compile cleanly (`py -3.12 -m compileall app tests alembic`).
- **Alembic Offline Validation**:
  - `alembic upgrade head --sql` passed and generated clean DDL.
  - `alembic downgrade 0003_vehicle_positions:0002_optional_agency_id --sql` passed and generated clean drop DDL.
- **Frontend Regression**:
  - `npm.cmd test -- --run`: 2 test files, 6 tests passed in 3.36s.
  - `npm.cmd run build`: production build passed in 2.29s without errors.

#### Changed / Added Files
- `apps/api/pyproject.toml` (added `gtfs-realtime-bindings>=3.0.0` and `protobuf>=5.0.0`)
- `apps/api/app/models/vehicle_position.py` (new `VehiclePosition` snapshot model)
- `apps/api/app/models/feed.py` (added `vehicle_positions` relationship)
- `apps/api/app/models/__init__.py` (exported `VehiclePosition`)
- `apps/api/alembic/versions/0003_vehicle_positions.py` (new forward migration)
- `apps/api/app/services/realtime/__init__.py` (realtime package exports)
- `apps/api/app/services/realtime/exceptions.py` (realtime exception hierarchy)
- `apps/api/app/services/realtime/downloader.py` (safe HTTP downloader)
- `apps/api/app/services/realtime/parser.py` (protobuf decoder and validator)
- `apps/api/app/services/realtime/service.py` (snapshot ingestion service)
- `apps/api/app/services/realtime/cli.py` (administrative CLI)
- `apps/api/tests/test_alembic.py` (updated migration head verification to 0003)
- `apps/api/tests/test_models.py` (added vehicle position model structure test)
- `apps/api/tests/test_realtime_ingestion.py` (26 new comprehensive tests)
- `docs/database/database-design.md` (documented `vehicle_positions` table, migration 0003, and snapshot strategy)
- `docs/architecture/overview.md` (updated GTFS-Realtime service status to Partial)
- `README.md` (updated development status and milestones)
- `docs/development-ledger.md` (this ledger)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - GTFS-Realtime `DIFFERENTIAL` incrementality is unsupported by design; only `FULL_DATASET` is accepted.
  - GTFS-Realtime trip updates and alerts are not yet stored (scheduled for future slices).
  - Background polling daemon / cron scheduler is not yet active (manual/CLI triggering only).
  - Live vehicle positions are stored in the database snapshot table but not yet broadcast over WebSockets or rendered on the frontend map.
- **Next Authorized Step**:
  - **Stage 3, Slice 3.1**: Historical Vehicle Observation Storage (Completed below).

---

## Stage 3: ETA Prediction & Historical Analysis

### Slice 3.1: Historical Vehicle Observation Storage (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement longitudinal historical vehicle observation storage (`VehicleObservation`), composite uniqueness and idempotency constraints on `(feed_id, entity_id, observed_at)`, deterministic timestamp fallback hierarchy (`vehicle_timestamp` → `feed_timestamp` → server receipt time), atomic dual-persistence transaction (replacing current-state snapshot while appending deduplicated history samples), internal query helper `get_recent_observations(...)` with mandatory `since` time bounding and result limits, forward Alembic migration `0004_vehicle_observations` with spatial GiST indexing, and comprehensive deterministic test suite.

#### Implemented Components
1. **Database Model & Migration** (`apps/api/app/models/vehicle_observation.py`, `apps/api/alembic/versions/0004_vehicle_observations.py`):
   - `VehicleObservation` model with feed foreign key (`transit_feeds.id`, cascade delete).
   - Distinct timestamp fields: `observed_at` (canonical observation time), `vehicle_timestamp` (source vehicle time), `feed_timestamp` (feed header time), and `recorded_at` (server receipt time).
   - Identifiers and movement telemetry: `entity_id`, `vehicle_id`, `vehicle_label`, `license_plate`, `trip_id`, `route_id`, `direction_id`, `stop_id`, `current_stop_sequence`, `current_status`, `latitude`, `longitude`, `point` (PostGIS geography point with GiST index), `bearing`, `odometer`, `speed`, `congestion_level`, `occupancy_status`, `occupancy_percentage`.
   - Composite unique constraint: `UniqueConstraint("feed_id", "entity_id", "observed_at", name="uq_vehicle_observations_feed_entity_observed_at")`.
   - Performance indexes: `ix_vehicle_obs_feed_id`, `ix_vehicle_obs_feed_vehicle_time`, `ix_vehicle_obs_feed_route_time`, `ix_vehicle_obs_feed_observed_at`, and GiST spatial index `ix_vehicle_obs_point`.
   - Relationship `TransitFeed.vehicle_observations` added to `TransitFeed`.
   - Forward migration `0004_vehicle_observations` generating clean upgrade and downgrade DDL.
2. **Atomic Dual-Persistence Ingestion** (`apps/api/app/services/realtime/service.py`):
   - `VehiclePositionIngestionService`: In a single atomic transaction:
     1. Replaces current-state snapshot in `vehicle_positions`.
     2. Extracts candidate historical observations with deterministic fallback: `observed_at = vp.vehicle_timestamp or parsed_feed.feed_timestamp or receipt_time`.
     3. Queries existing `(entity_id, observed_at)` keys for the current batch.
     4. Appends only new observations (deduplicating repeat polls of identical telemetry).
     5. Updates `TransitFeed.last_realtime_poll_at`.
   - Atomic rollback: failure at any step rolls back both snapshot and history changes.
3. **Internal Query Helper** (`apps/api/app/services/realtime/query.py`):
   - `get_recent_observations(session, feed_id, since, ...)`:
     - Mandatory `since: datetime` validation (raises `ValueError` if absent, preventing unbounded queries).
     - Optional `until`, `vehicle_id`, `entity_id`, `route_id`, `trip_id` filters.
     - Enforced `limit` capped at 1,000 rows.
     - Ordered newest-first (`observed_at.desc()`).
4. **Comprehensive Test Suite** (`apps/api/tests/test_vehicle_observations.py`):
   - 9 deterministic unit and integration tests covering:
     - First insert creating both snapshot and history rows.
     - Repeat-poll deduplication with identical timestamps.
     - Subsequent poll with new observation timestamp appending to history while refreshing snapshot.
     - Source timestamp fallback hierarchy (`vehicle_timestamp` absent -> `feed_timestamp`; both absent -> receipt time).
     - Snapshot and history atomic rollback on simulated database failure.
     - Rejection of invalid / DIFFERENTIAL payloads preserving snapshot and history intact.
     - Feed isolation across multiple feeds.
     - Query helper filtering, ordering, time bounds, and limit capping.
     - Mandatory `since` validation in query helper.

#### Verification Evidence
- **Pytest**: 96 tests passed in 9.56s (`py -3.12 -m pytest apps/api/tests -v`).
- **Ruff**: Zero lint errors and clean formatting across `app/`, `tests/`, and `alembic/` (53 files checked).
- **Python Compilation**: All backend modules compile cleanly (`py -3.12 -m compileall app tests alembic`).
- **Alembic Offline Validation**:
  - `alembic upgrade head --sql` passed and generated clean DDL.
  - `alembic downgrade 0004_vehicle_observations:0003_vehicle_positions --sql` passed and generated clean drop DDL.
- **Frontend Regression**:
  - `npm.cmd test -- --run`: 2 test files, 6 tests passed in 3.38s.
  - `npm.cmd run build`: production build passed in 2.34s without errors.

#### Changed / Added Files
- `apps/api/app/models/vehicle_observation.py` (new `VehicleObservation` model)
- `apps/api/app/models/feed.py` (added `vehicle_observations` relationship)
- `apps/api/app/models/__init__.py` (exported `VehicleObservation`)
- `apps/api/alembic/versions/0004_vehicle_observations.py` (new forward migration)
- `apps/api/app/services/realtime/query.py` (internal query helper `get_recent_observations`)
- `apps/api/app/services/realtime/__init__.py` (exported query helper)
- `apps/api/app/services/realtime/service.py` (atomic snapshot + deduplicated history persistence)
- `apps/api/tests/test_alembic.py` (updated migration head verification to 0004)
- `apps/api/tests/test_models.py` (added vehicle observation model structure test)
- `apps/api/tests/test_vehicle_observations.py` (9 new comprehensive tests)
- `docs/database/database-design.md` (documented `vehicle_observations` table, migration 0004, and idempotency strategy)
- `docs/architecture/overview.md` (updated historical observations and ETA service status)
- `README.md` (updated development status and milestones)
- `docs/development-ledger.md` (this ledger)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Historical observations are accumulated via GTFS-RT polling; retention policy / partition pruning is not yet implemented.
  - No public REST API endpoints expose historical observations directly (internal query helper only for ETA service).
  - Background polling daemon / cron scheduler is not yet active (manual/CLI triggering only).
- **Next Authorized Step**:
  - **Stage 3, Slice 3.2**: Stop Arrival Predictions & ETA Engine (Completed below).

---

### Slice 3.2: Stop Arrival Predictions & ETA Engine (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement read-only, feed-scoped stop arrival prediction API (`GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`), evaluating live vehicle snapshots, GTFS static schedules, calendar service activity and exceptions, agency timezones, extended-hour (>24:00) service times, downstream stop sequence filtering, realtime telemetry freshness windows (<= 300s), and deterministic historical median delay adjustments with schedule-only fallback.

#### Implemented Components
1. **Prediction Schema** (`apps/api/app/schemas/transit.py`, `apps/api/app/schemas/__init__.py`):
   - Defined `StopArrivalPrediction` schema with typed fields: `feed_slug`, `feed_id`, `stop_id`, `trip_id`, `route_id`, `route_short_name`, `trip_headsign`, `vehicle_id`, `stop_sequence`, `scheduled_arrival_time`, `estimated_arrival_time`, `delay_seconds`, `prediction_source`, and `source_observation_time`.
2. **Prediction Service** (`apps/api/app/services/prediction/service.py`, `apps/api/app/services/prediction/__init__.py`):
   - `ArrivalPredictionService`:
     - Resolves feed/stop agency timezone safely with UTC fallback.
     - `get_active_service_ids`: Evaluates GTFS `calendars` and `calendar_dates` exceptions (`exception_type=1` added, `exception_type=2` removed) on target service date.
     - `parse_gtfs_time_to_seconds`: Handles extended GTFS service hours (> 24:00, e.g. `25:15:00` for overnight trips) mapping to the next calendar day.
     - Freshness window: Rejects vehicle telemetry older than 300 seconds (5 minutes) or future-skewed beyond 60 seconds.
     - Downstream filtering: Only evaluates active trips where target stop sequence is downstream of the vehicle's `current_stop_sequence` (`target_seq >= curr_seq`). Gracefully skips vehicles without trip or sequence evidence.
     - Deterministic delay adjustment: Queries recent historical `STOPPED_AT` observations for the same trip/vehicle at earlier scheduled stops, computing:
       $$\Delta t_i = T_{\text{obs}}(P_i) - T_{\text{sched}}(P_i)$$
       $$\text{delay\_seconds} = \text{median}(\{\Delta t_i\}) \quad (\text{when samples} \ge 1)$$
       $$T_{\text{est}} = T_{\text{sched}} + \text{delay\_seconds} \quad (\text{labeled } \texttt{HISTORY\_ADJUSTED})$$
     - Schedule fallback: When history has insufficient `STOPPED_AT` observations, returns $T_{\text{est}} = T_{\text{sched}}$ with $\text{delay\_seconds} = 0$ (labeled $\texttt{SCHEDULE\_ONLY}$).
     - Result ordering & limits: Orders deterministically by `estimated_arrival_time.asc()`, then `trip_id`, and caps by `limit`.
3. **Arrivals REST Endpoint** (`apps/api/app/api/transit.py`):
   - `GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals` (also mounted at `/feeds/{feed_slug}/stops/{stop_id}/arrivals`).
   - Supports looking up feed by slug or numeric ID (`_get_feed_by_slug`).
   - Validates existence of feed and stop (returns 404 on missing entities).
   - Sanitized 503 error handling on database service unavailability.
   - Response wrapped in standard `ItemEnvelope[list[StopArrivalPrediction]]`.
4. **Comprehensive Test Suite** (`apps/api/tests/test_stop_arrivals.py`):
   - 9 deterministic unit and integration tests covering:
     1. Active service calendar evaluation and exceptions (`exception_type=1` added, `exception_type=2` removed).
     2. Extended service day hours (>24:00) mapping accurately to next day.
     3. Downstream stop sequence filtering.
     4. Stale and missing telemetry skipping.
     5. History median adjustment and schedule-only fallback.
     6. Feed isolation across distinct feeds.
     7. Bounded ordering by estimated arrival time and limit capping.
     8. Invalid feed/stop identifiers (404) and database outages (503).
     9. GTFS time parser helper unit tests.

#### Verification Evidence
- **Pytest**: 105 tests passed in 11.77s (`py -3.12 -m pytest apps/api/tests -v`).
- **Ruff**: Zero lint errors and clean formatting across all 56 files in `app/`, `tests/`, and `alembic/`.
- **Python Compilation**: All backend modules compile cleanly (`py -3.12 -m compileall app tests alembic`).
- **Alembic Offline Validation**: `alembic upgrade head --sql` validated clean static DDL.
- **Frontend Regression**:
  - `npm.cmd test -- --run`: 2 test files, 6 tests passed in 3.36s.
  - `npm.cmd run build`: production build passed in 2.31s without errors.

#### Changed / Added Files
- `apps/api/pyproject.toml` (added `tzdata>=2024.1` for cross-platform IANA timezone support)
- `apps/api/app/schemas/transit.py` (added `StopArrivalPrediction` schema)
- `apps/api/app/schemas/__init__.py` (exported `StopArrivalPrediction`)
- `apps/api/app/services/prediction/service.py` (arrival prediction service)
- `apps/api/app/services/prediction/__init__.py` (exported prediction service)
- `apps/api/app/api/transit.py` (added `GET /feeds/{feed_slug}/stops/{stop_id}/arrivals`)
- `apps/api/tests/test_stop_arrivals.py` (9 new comprehensive tests)
- `docs/architecture/overview.md` (updated ETA service and REST API documentation)
- `README.md` (updated Stage 3 status to complete)
- `docs/development-ledger.md` (this ledger)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - ETAs assume linear delay propagation from prior stops; traffic signal timing, route shapes, and segment-level speed distributions are not modeled.
  - Live arrival predictions are accessed via HTTP pull; real-time push over WebSockets is not yet active.
  - Trip updates / cancellations from GTFS-RT `TripUpdate` feeds are not yet ingested (planned for future expansion).
- **Next Authorized Step**:
  - **Stage 4, Slice 4.1**: Feed-Aware Transit Explorer & Live Arrivals (Completed below).

---

## Stage 4: UI Polish & Explorer Experience

### Slice 4.1: Feed-Aware Transit Explorer & Live Arrivals (Completed & Verified)

- **Date**: 2026-11-10
- **Goal**: Implement the first full-featured web experience on top of the transit query and arrival prediction APIs: keyboard-accessible feed selector, feed-scoped stop search, live arrivals board with delay pills and source badges, agency timezone disclosures, feed isolation in state management, and full loading/empty/error recovery.

#### Implemented Components
1. **Public UI Feed Metadata Enrichment** (`apps/api/app/schemas/transit.py`, `apps/api/tests/test_transit_api.py`):
   - Enriched `FeedSummaryResponse` with `id: int` and `last_realtime_poll_at: datetime | None`.
   - Verified that `GET /api/v1/feeds` never leaks credentials, private URLs (`static_gtfs_url`), or API keys.
2. **Frontend Architecture & Environment** (`apps/web/.env.example`, `apps/web/src/types/transit.ts`):
   - Established `VITE_API_URL` convention defaulting safely to `http://localhost:8000`.
   - Defined TypeScript models: `FeedSummary`, `StopSummary`, `StopArrivalPrediction`, `ItemEnvelope`, and `PaginatedResponse`.
3. **API Client Layer** (`apps/web/src/lib/api.ts`):
   - `fetchFeeds`: Retrieves list of configured feeds and public status from `/api/v1/feeds`.
   - `fetchStops`: Queries stops with search string `q` and pagination from `/api/v1/feeds/{feed_slug}/stops`.
   - `fetchArrivals`: Queries estimated arrival predictions from `/api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`.
   - Comprehensive error extraction parsing backend JSON `detail` messages for user display.
4. **Time & Delay Formatters** (`apps/web/src/lib/formatters.ts`):
   - `formatTime`: Converts ISO 8601 timestamps to readable 12-hour times with agency timezone (`timeZone`) support and graceful local-browser fallback.
   - `formatDelay`: Categorizes delays (`>60s` -> `+X min late`, `<-60s` -> `X min early`, within $\pm 60$s -> `On time`) with high-contrast color badges.
   - `formatPredictionSource`: Distinguishes `HISTORY_ADJUSTED` ("Live + History") from `SCHEDULE_ONLY` ("Schedule") with explanatory tooltips.
   - `formatObservationAge`: Humanizes vehicle telemetry timestamps (e.g. `25s ago`, `5m ago`).
5. **Feed-Isolated State Management** (`apps/web/src/stores/appStore.ts`):
   - Zustand store tracking `selectedFeedSlug`, `selectedStop`, and backward-compatible `selectedCity`.
   - **Feed Isolation**: Setting or switching `selectedFeedSlug` automatically resets `selectedStop` to `null`, preventing stale stops or arrivals from one feed persisting in another.
6. **Accessible UI Components & Dashboard** (`apps/web/src/components/`, `apps/web/src/pages/Dashboard.tsx`):
   - `FeedSelector`: Accessible `<select>` combobox with loading indicator, error retry button, feed status pill, and live tracking status pill.
   - `StopSearch`: Labeled search input with debounced query, clear button, accessible result list with wheelchair badges, and empty/error states.
   - `ArrivalsBoard`: Stop-level board with route badge, headsign, scheduled vs estimated times, delay badge, prediction source badge, telemetry age, agency timezone note, and manual refresh button.
   - `Dashboard`: Clean two-column responsive grid layout adapting to mobile viewports with semantic HTML landmarks (`<header>`, `<main>`, `<section>`, `<footer>`).
7. **Comprehensive Unit & Integration Test Suites**:
   - `apps/web/src/__tests__/appStore.test.ts` (6 tests: initial state, feed setting, stop selection, feed isolation, reset, backward compatibility).
   - `apps/web/src/__tests__/formatters.test.ts` (14 tests: time formatting, timezone support, fallback, delay classification, source badges, observation age).
   - `apps/web/src/__tests__/api.test.ts` (7 tests: fetchApi 200, error extraction, feeds, stops, arrivals, health).
   - `apps/web/src/__tests__/TransitExplorer.test.tsx` (14 tests: feed selection, stop search, arrivals board, manual refresh, empty/error states, feed isolation end-to-end).
   - `apps/web/src/__tests__/Dashboard.test.tsx` (5 tests: landmarks, headings, sections, badges).

#### Verification Evidence
- **Frontend Vitest**: 46 tests passed across 5 test suites in 3.32s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 1.69s (`npm.cmd run build`).
- **Backend Pytest**: 105 tests passed in 10.27s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint errors and clean formatting across 56 files (`py -3.12 -m ruff check app tests`, `py -3.12 -m ruff format --check app tests`).
- **Backend Compilation**: Clean bytecode compilation with Python 3.12 (`py -3.12 -m compileall app tests`).

#### Changed / Added Files
- `apps/api/app/schemas/transit.py` (added `id` and `last_realtime_poll_at` to `FeedSummaryResponse`)
- `apps/api/tests/test_transit_api.py` (verified public UI feed metadata and sensitive field omission)
- `apps/web/.env.example` (new environment configuration template for Vite)
- `apps/web/src/types/transit.ts` (new TypeScript transit domain interfaces)
- `apps/web/src/lib/api.ts` (transit API client methods and error handling)
- `apps/web/src/lib/formatters.ts` (time, delay, source, and observation age formatters)
- `apps/web/src/stores/appStore.ts` (feed isolation state store)
- `apps/web/src/components/feedSelector.tsx` (feed selector component)
- `apps/web/src/components/stopSearch.tsx` (feed-scoped stop search component)
- `apps/web/src/components/arrivalsBoard.tsx` (live arrivals board component)
- `apps/web/src/pages/Dashboard.tsx` (responsive transit explorer layout)
- `apps/web/src/__tests__/appStore.test.ts` (updated store tests)
- `apps/web/src/__tests__/formatters.test.ts` (formatter tests)
- `apps/web/src/__tests__/api.test.ts` (API client tests)
- `apps/web/src/__tests__/TransitExplorer.test.tsx` (component and feed isolation tests)
- `apps/web/src/__tests__/Dashboard.test.tsx` (dashboard integration tests)
- `README.md` (updated Stage 4 status and milestones)
- `docs/architecture/overview.md` (documented Transit Explorer web frontend architecture)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Interactive map view (rendering stop markers, route shapes, and vehicle markers) is not yet active (Stage 4, Slice 4.2).
  - Stop arrivals are currently refreshed via manual button or on initial load; automated polling or WebSocket push is not yet enabled.
- **Next Authorized Step**:
  - **Stage 4, Slice 4.2**: Interactive Map Component & Route Visualization.

### 2026-11-10 — Stage 4, Slice 4.2: Interactive Map & Route Visualization

#### Overview
Implemented the interactive route and vehicle map visualization for the WaitWatch transit platform. Built an interactive, feed-scoped map with Leaflet that displays a selected route, its ordered passenger stops, and current vehicle positions. To ensure accurate geometry representation, implemented the database model, schema, and parser/importer for GTFS `shapes.txt` with PostGIS geography point indexing, and established an explicit rule and UI behavior to never fabricate route lines from stops when GTFS shapes are unavailable. Configured customizable tile URLs via `VITE_MAP_TILE_URL` with visible OpenStreetMap attribution and documented third-party tile usage policies.

#### Key Deliverables & Design Decisions
1. **GTFS Shapes Database Model & Migration** (`apps/api/app/models/shape.py`, `apps/api/alembic/versions/0005_shapes.py`):
   - `Shape` model containing `id`, `feed_id`, `shape_id`, `shape_pt_lat`, `shape_pt_lon`, `shape_pt_sequence`, `shape_dist_traveled`, PostGIS `point` (`geography(POINT, 4326)`), timestamps, unique constraint `uq_shapes_feed_shape_seq (feed_id, shape_id, shape_pt_sequence)`, and spatial GiST index.
   - Forward migration `0005_shapes` with clean offline upgrade and downgrade SQL generation.
2. **GTFS Schedule Shapes Parser & Importer** (`apps/api/app/services/gtfs/parser.py`, `importer.py`):
   - Parsed and validated `shapes.txt` records with coordinate bounds checking (`[-90, 90]`, `[-180, 180]`), sequence validation, duplicate sequence rejection, and optional distance traveled parsing. Handled absent `shapes.txt` gracefully as an optional GTFS Schedule component.
   - Batch insertion into `shapes` table with feed-scoped deletion for atomic, idempotent feed replacement.
3. **Route Map REST API Endpoint** (`apps/api/app/api/transit.py`, `apps/api/app/schemas/transit.py`):
   - Added `GET /api/v1/feeds/{feed_slug}/routes/{route_id}/map` returning route metadata, ordered shape point sequences, ordered stops served by the route, and fresh live vehicles.
   - **No Fabricated Shapes**: Routes without shapes return `shapes: []` without synthetic stop-to-stop lines.
   - **Fresh Vehicle Telemetry**: Excludes stale vehicles with telemetry older than 300 seconds (`func.coalesce(vehicle_timestamp, feed_timestamp, recorded_at)`).
   - Feed isolation and public metadata only: internal credentials and URLs are omitted.
4. **Interactive Map Component (`MapView`)** (`apps/web/src/components/mapView.tsx`):
   - Leaflet map rendering true shape polylines in route colors (`#3b82f6` default), circular stop markers with tooltips and click-to-select, and bearing-rotated vehicle markers.
   - When shapes are absent, displays an explicit status pill (`⚠️ Route shape unavailable — showing stops only`) rather than drawing synthetic lines.
   - Dynamic viewport auto-fit using `map.fitBounds` across all route features, window resize listener, and loading/error states with retry.
   - Tile provider configurable via `VITE_MAP_TILE_URL` defaulting to standard OpenStreetMap tiles, with mandatory, visible attribution (`&copy; OpenStreetMap contributors`).
5. **Route Selector & Map Details Panel** (`apps/web/src/components/routeSelector.tsx`, `apps/web/src/components/mapDetailsPanel.tsx`):
   - `RouteSelector`: Dropdown combobox for choosing routes within the selected feed with route type/color badges and loading/error states.
   - `MapDetailsPanel`: Dual-tab inspector displaying ordered stops and live vehicle telemetry cards (speed in km/h, bearing in degrees, coordinates, transit status, observation age).
6. **Feed and Route Isolation** (`apps/web/src/stores/appStore.ts`):
   - Zustand store resets `selectedRouteId`, `selectedStop`, and `selectedVehicleId` when the feed changes. Changing route resets `selectedVehicleId`.
7. **Comprehensive Unit & Integration Test Suites**:
   - Backend tests (114 tests total): tested shape model constraints, migration downgrade/upgrade, parser validation, idempotent importer, route map API success, missing shape handling, fresh vs stale vehicle filtering, and cross-feed isolation.
   - Frontend tests (65 tests total): tested store route/vehicle actions, api client `fetchRoutes` and `fetchRouteMap`, `RouteSelector`, `MapView` (with shapes, missing shape alert, live vehicle badges, tile attribution), `MapDetailsPanel` (tabs, stop selection, vehicle telemetry inspector), and end-to-end feed switching isolation.

#### Tile Usage Policy & Production Note
The default tile layer uses OpenStreetMap's standard tile service (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`). In accordance with the OpenStreetMap Tile Usage Policy:
- OSM standard tile servers are intended for development, testing, and limited low-volume personal use; heavy or production traffic should point `VITE_MAP_TILE_URL` to a dedicated vector/raster tile service (such as Protomaps, Mapbox, Stadia Maps, or self-hosted tile servers).
- Attribution (`&copy; OpenStreetMap contributors`) is visibly preserved on all screen sizes in accordance with the ODbL license.

#### Verification Evidence
- **Frontend Vitest**: 65 tests passed across 5 test suites in 4.04s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 2.55s (`npm.cmd run build`).
- **Backend Pytest**: 114 tests passed in 10.71s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint errors and clean formatting across 52 files (`py -3.12 -m ruff check app tests`, `py -3.12 -m ruff format --check app tests`).
- **Backend Compilation**: Clean bytecode compilation with Python 3.12 (`py -3.12 -m compileall app tests alembic`).
- **Alembic Migrations**: Offline SQL upgrade and downgrade verified without error (`0005_shapes`).

#### Changed / Added Files
- `apps/api/app/models/shape.py` (new `Shape` model with PostGIS geography point)
- `apps/api/app/models/feed.py` (added `shapes` relationship to `TransitFeed`)
- `apps/api/app/models/__init__.py` (exported `Shape`)
- `apps/api/alembic/versions/0005_shapes.py` (new migration for `shapes` table)
- `apps/api/app/services/gtfs/parser.py` (shapes.txt parser with sequence and coordinate checks)
- `apps/api/app/services/gtfs/importer.py` (atomic batch persistence for shapes)
- `apps/api/app/schemas/transit.py` (new route map schemas: `RouteMapResponse`, `RouteShapeResponse`, etc.)
- `apps/api/app/schemas/__init__.py` (exported route map schemas)
- `apps/api/app/api/transit.py` (route map endpoint implementation)
- `apps/api/tests/test_alembic.py` (migration chain assertions for `0005_shapes`)
- `apps/api/tests/test_models.py` (tests for `Shape` model)
- `apps/api/tests/test_gtfs_ingestion.py` (parser and importer tests for shapes)
- `apps/api/tests/test_transit_api.py` (integration tests for route map endpoint)
- `apps/web/package.json` & `package-lock.json` (installed `leaflet` and `@types/leaflet`)
- `apps/web/.env.example` (documented `VITE_MAP_TILE_URL` and OSM usage policy)
- `apps/web/src/types/transit.ts` (added route map, shapes, and vehicle types)
- `apps/web/src/lib/api.ts` (added `fetchRoutes` and `fetchRouteMap`)
- `apps/web/src/stores/appStore.ts` (route, stop, vehicle state and feed isolation)
- `apps/web/src/components/routeSelector.tsx` (new route selector combobox)
- `apps/web/src/components/mapView.tsx` (new Leaflet map component)
- `apps/web/src/components/mapDetailsPanel.tsx` (new stop & live vehicle details inspector)
- `apps/web/src/pages/Dashboard.tsx` (integrated map, route selector, and details panel)
- `apps/web/src/__tests__/appStore.test.ts` (updated store tests)
- `apps/web/src/__tests__/api.test.ts` (updated API client tests)
- `apps/web/src/__tests__/Dashboard.test.tsx` (updated dashboard landmark tests)
- `apps/web/src/__tests__/TransitExplorer.test.tsx` (expanded component & feed isolation tests)
- `README.md` (updated Stage 4 milestones and status)
- `docs/architecture/overview.md` (updated architecture overview with map visualization)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Live vehicles and stop arrivals are currently refreshed on component mount, route selection change, or manual button click; automated background polling or WebSocket push is not yet enabled.
  - Map tiles rely on standard raster tile services; vector map styling is not yet integrated.
- **Next Authorized Step**:
  - **Stage 4, Slice 4.3**: Realtime Polling & Live Map Refresh (or GTFS-RT TripUpdates Ingestion).

### 2026-11-10 — Stage 4, Slice 4.3: Realtime Polling & Live Map Refresh

#### Overview
Implemented client-side real-time periodic polling and live data refresh across the Transit Explorer web application. Chose the modest client polling architecture to deliver immediate passenger utility without introducing new server workers, schedulers, or streaming infrastructure. Applied a conservative 30-second default polling interval (`DEFAULT_POLLING_INTERVAL_MS = 30_000`, configurable via `VITE_POLLING_INTERVAL_SEC`), strictly active only when a relevant feed/stop or feed/route is selected and the browser tab is visible. Integrated browser document visibility tracking (`useDocumentVisibility`, `usePollingVisibilityRefresh`) to pause polling while hidden and refresh immediately upon visibility return. Hardened error resilience to preserve previous successful arrival predictions and route vehicle markers on transient network failures, displaying non-blocking stale warning banners, exact last-updated timestamps, "⚠️ Stale" status indicators, and manual refresh controls. Preserved map performance by polling JSON transit data only, avoiding automated tile re-fetches.

#### Key Deliverables & Design Decisions
1. **Configurable Polling Configuration & Visibility Management** (`apps/web/src/lib/polling.ts`, `apps/web/.env.example`):
   - Defined `DEFAULT_POLLING_INTERVAL_MS = 30_000` (30 seconds), configurable via optional `VITE_POLLING_INTERVAL_SEC` environment variable (bounded between 10s and 300s).
   - Documented the chosen 30-second interval: provides responsive ETA updates and live vehicle movement while keeping network requests and CPU overhead conservative.
   - Built `useDocumentVisibility()` custom hook using the HTML5 Page Visibility API (`visibilitychange` event) with clean event listener cleanup on unmount.
   - Built `usePollingVisibilityRefresh(enabled, refetch, isVisible)` to automatically detect transitions from hidden back to visible and trigger a single synchronization refresh.
2. **Stop Arrivals Polling & Stale Error Resilience** (`apps/web/src/components/arrivalsBoard.tsx`):
   - Configured TanStack Query `refetchInterval` returning `pollingInterval` (30s) only when both `selectedFeedSlug && selectedStop` are present and the page is visible (`isVisible`).
   - Disabled background polling (`refetchIntervalInBackground: false`).
   - Integrated `formatLastUpdated` timestamp formatter (`apps/web/src/lib/formatters.ts`) to display exact clock time of the last successful update.
   - Preserves previous arrivals data on transient background refresh failure (`hasError && arrivals.length > 0`) while displaying a non-blocking warning alert, last updated timestamp, and "⚠️ Stale" status pill.
   - Displays accessible live status indicator: `● Live (30s)` with pulsing indicator when fresh, `⏸ Paused` when tab is hidden, or `⚠️ Stale` when refresh failed.
   - Manual "Refresh" button with loading spinner, disabled during in-flight fetches (`isFetching`) to prevent request racing or duplication.
3. **Route Map & Live Vehicle Polling** (`apps/web/src/components/mapView.tsx`, `apps/web/src/components/mapDetailsPanel.tsx`):
   - Configured TanStack Query `refetchInterval` for `["routeMap", selectedFeedSlug, selectedRouteId]`.
   - Polling scoped strictly to active `selectedFeedSlug && selectedRouteId`; ceases immediately when a route or feed is cleared.
   - **No Automated Tile Requests**: Polls only the route map JSON endpoint; Leaflet vector polylines, stop circles, and vehicle div icons update in-place without touching tile layers.
   - **Stable Viewport**: `map.fitBounds` is called strictly on initial route selection or route change (`lastFittedRouteRef`), preventing jarring viewport jumps during background vehicle updates.
   - Transient failure preservation: preserves the map canvas and vehicle markers on background failure, showing a warning banner and `⚠️ Stale` badge.
   - Both `MapView` and `MapDetailsPanel` share the exact same cached query, deduplicating network calls completely.
4. **Comprehensive Unit & Integration Test Suites**:
   - `apps/web/src/__tests__/polling.test.ts` (6 tests: default interval, environment configuration, document visibility changes, event listener cleanup, visibility return refresh, disabled polling check).
   - `apps/web/src/__tests__/formatters.test.ts` (17 tests: extended with `formatLastUpdated` tests for null, 0, timestamps, and timezone support).
   - `apps/web/src/__tests__/TransitExplorer.test.tsx` (33 tests: tested live polling indicators and timestamps, fake timer periodic refresh at 30s intervals for arrivals and map data, transient error preservation retaining data and showing warnings, document visibility pause while hidden and immediate resume on return, selection change/unmount cleanup).

#### Verification Evidence
- **Frontend Vitest**: 81 tests passed across 6 test suites in 4.53s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 2.38s (`npm.cmd run build`).
- **Backend Pytest**: 114 tests passing from Stage 4.2 (backend files were not modified in this slice).

#### Changed / Added Files
- `apps/web/src/lib/polling.ts` (new polling configuration and visibility hooks)
- `apps/web/src/lib/formatters.ts` (added `formatLastUpdated` timestamp formatter)
- `apps/web/.env.example` (documented `VITE_POLLING_INTERVAL_SEC`)
- `apps/web/src/components/arrivalsBoard.tsx` (polling, visibility integration, stale error preservation, live indicators)
- `apps/web/src/components/mapView.tsx` (route/vehicle polling, stable fitBounds, stale preservation, live indicators)
- `apps/web/src/components/mapDetailsPanel.tsx` (synchronized route map polling query options)
- `apps/web/src/__tests__/polling.test.ts` (new unit tests for polling and visibility hooks)
- `apps/web/src/__tests__/formatters.test.ts` (added tests for `formatLastUpdated`)
- `apps/web/src/__tests__/TransitExplorer.test.tsx` (added 7 new tests for periodic polling, visibility pause/resume, stale preservation)
- `README.md` (updated Stage 4 milestones and status)
- `docs/architecture/overview.md` (updated architecture status with real-time polling)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Browser-based client polling queries the existing read-only REST endpoints; vehicle positions and stop arrivals only update when backend feeds or GTFS-RT pollers ingest new telemetry.
  - Push-based streaming (WebSockets or Server-Sent Events) is not yet implemented.
- **Next Authorized Step**:
  - **Stage 4, Slice 4.4**: GTFS-Realtime TripUpdates Ingestion (Completed below).

---

### 2026-11-10 — Stage 4, Slice 4.4: GTFS-Realtime TripUpdates Ingestion

#### Overview
Implemented the GTFS-Realtime TripUpdates ingestion pipeline, database persistence, and ETA prediction engine integration. Reused the existing MobilityData Protocol Buffer runtime (`gtfs_realtime_pb2.FeedMessage`) and resilient streaming downloader to decode and validate `TripUpdate` entities without introducing new external dependencies or separate worker processes. Designed an atomic feed-scoped current-state snapshot table (`trip_updates`) governed by forward migration `0006_trip_updates`, replacing feed snapshots idempotently and updating feed poll timestamps. Integrated TripUpdates directly into `ArrivalPredictionService` (`GET /api/v1/feeds/{feed_slug}/stops/{stop_id}/arrivals`), evaluating the high-fidelity `TRIP_UPDATE` prediction source ahead of client-side dead reckoning or static schedules, strictly enforcing the GTFS-Realtime standard precedence of absolute event times (`arrival.time`) over relative delays (`arrival.delay`), supporting departure event fallbacks, and suppressing canceled trips (`CANCELED`) and skipped stops (`SKIPPED`). Updated the frontend Transit Explorer to render distinct "Live TripUpdate" emerald status badges alongside scheduled vs estimated arrival times, delay badges, and observation ages.

#### Key Deliverables & Design Decisions
1. **GTFS-RT TripUpdate Database Model & Migration** (`apps/api/app/models/trip_update.py`, `apps/api/alembic/versions/0006_trip_updates.py`):
   - Created `TripUpdate` model storing feed-scoped trip updates and constituent stop-time predictions: `entity_id`, `trip_id`, `route_id`, `direction_id`, `start_time`, `start_date`, `schedule_relationship`, `vehicle_id`, `stop_sequence`, `stop_id`, arrival and departure event times, delays, uncertainties, `stop_schedule_relationship`, `trip_delay`, and telemetry timestamps.
   - Added indexes on `feed_id`, `(feed_id, trip_id)`, `(feed_id, stop_id)`, `(feed_id, entity_id)`, and `(feed_id, trip_id, stop_id)` with `ondelete="CASCADE"` foreign key to `transit_feeds.id`.
   - Forward migration `0006_trip_updates` with verified static SQL generation for upgrade and downgrade.
   - Added `trip_updates` relationship to `TransitFeed` model with cascade delete and passive deletes.
2. **Defensive Protocol Buffer Parsing** (`apps/api/app/services/realtime/parser.py`):
   - Built `parse_trip_updates(payload: bytes) -> ParsedTripUpdatesFeed` using `gtfs_realtime_pb2.FeedMessage`.
   - Validated `FeedHeader`: requires valid version, enforces bounds on header timestamps, and rejects `DIFFERENTIAL` incrementality with `UnsupportedIncrementalityError` (only `FULL_DATASET` supported).
   - Validated `FeedEntity`: requires entity identifier, rejects duplicate entity IDs, and skips non-trip entities or deleted entities cleanly.
   - Validated `TripUpdate`: requires `trip_id`, validates timestamp bounds (< 2100 epoch seconds), parses arrival/departure events with delay and absolute POSIX times, and captures trip-level cancellations and general trip delays even when stop updates are omitted.
3. **Atomic Ingestion Service & Unified CLI Poller** (`apps/api/app/services/realtime/trip_update_service.py`, `apps/api/app/services/realtime/cli.py`):
   - Implemented `TripUpdateIngestionService.ingest_for_feed(...)`: downloads via `download_realtime_feed` using feed-configured API key environment variables without logging or exposing credentials.
   - Graceful skip: returns 0 without raising an error when a feed has no `realtime_trip_updates_url` configured.
   - Atomic replacement: deletes previous feed snapshot rows and bulk-inserts new ones in a single database transaction, rolling back on error and raising `RealtimePersistenceError`.
   - Integrated into existing `realtime-cli poll-vehicles` lifecycle: executing `poll-vehicles` runs vehicle positions first, then automatically ingests configured TripUpdates for the same feed.
   - Offline safety: local `--file` mode operates purely offline on the supplied vehicle protobuf file and performs zero outbound network calls.
   - Transaction error isolation: vehicle positions and deduplicated observations commit first; if TripUpdates download/parsing fails, the error is isolated, logged as a warning, and previous trip update snapshot state is preserved without losing vehicle positions.
   - Retained `poll-trip-updates` as an operator fallback subcommand sharing `TripUpdateIngestionService`.
4. **ETA Prediction Engine Integration** (`apps/api/app/services/prediction/service.py`, `apps/api/app/schemas/transit.py`):
   - Updated `ArrivalPredictionService.predict_arrivals_for_stop`: queries fresh `TripUpdate` records alongside `VehiclePosition` records within the 300s freshness window.
   - Precedence: when a trip has a matching `TripUpdate` for the target stop, uses prediction source `"TRIP_UPDATE"` directly from agency dispatch. Absolute event times (`time`) take strict precedence over relative delays (`delay`).
   - Exception handling: suppresses canceled trips (`schedule_relationship == CANCELED`) and skipped stops (`stop_schedule_relationship == SKIPPED`).
   - Coexistence and fallback: trips without TripUpdates fall back transparently to vehicle position historical delay adjustments (`HISTORY_ADJUSTED`) or scheduled timetable times (`SCHEDULE_ONLY`).
5. **Frontend UI Integration** (`apps/web/src/types/transit.ts`, `apps/web/src/lib/formatters.ts`, `apps/web/src/components/arrivalsBoard.tsx`):
   - Added `"TRIP_UPDATE"` to `PredictionSource` type.
   - Formatted `"TRIP_UPDATE"` with a distinct "Live TripUpdate" emerald badge (`bg-emerald-900/60 text-emerald-300 border border-emerald-700/60`) and passenger-facing tooltip description.
   - Rendered in `ArrivalsBoard` with scheduled time, estimated time, delay badges, and observation age.
6. **Comprehensive Unit & Integration Test Suites**:
   - Backend Pytest (136 tests total across 10 files): 21 tests in `test_trip_updates.py` covering protobuf parsing, error cases, missing header, differential rejection, duplicate entities, ingestion idempotency, feed isolation, combined `poll-vehicles` invocation of both ingest paths, skipping when unconfigured, offline `--file` mode safety, error isolation preserving vehicle observations on trip update failure, standalone CLI polling, stop arrival predictions with precedence and cancellation suppression, and stale telemetry handling; updated `test_models.py` and `test_alembic.py`.
   - Frontend Vitest (82 tests total across 6 files): tested `"TRIP_UPDATE"` formatting and live arrival card rendering in `TransitExplorer.test.tsx` and `formatters.test.ts`.

#### Verification Evidence
- **Backend Pytest**: 136 passed in 14.8s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero errors, 62 files formatted cleanly (`py -3.12 -m ruff check app tests alembic`, `py -3.12 -m ruff format --check app tests alembic`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall app tests alembic`).
- **Alembic Migrations**: Static SQL upgrade and downgrade verified without error (`0006_trip_updates`).
- **Frontend Vitest**: 82 passed across 6 test suites in 6.14s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 3.50s (`npm.cmd run build`).

#### Changed / Added Files
- `apps/api/app/models/trip_update.py` (new `TripUpdate` snapshot model)
- `apps/api/app/models/feed.py` (added `trip_updates` relationship to `TransitFeed`)
- `apps/api/app/models/__init__.py` (exported `TripUpdate`)
- `apps/api/alembic/versions/0006_trip_updates.py` (forward migration for `trip_updates` table)
- `apps/api/app/services/realtime/parser.py` (`parse_trip_updates` parser and dataclasses)
- `apps/api/app/services/realtime/trip_update_service.py` (`TripUpdateIngestionService` implementation)
- `apps/api/app/services/realtime/cli.py` (added `poll-trip-updates` CLI subcommand)
- `apps/api/app/services/realtime/__init__.py` (exported service and parser dataclasses)
- `apps/api/app/services/prediction/service.py` (integrated `TRIP_UPDATE` into arrival predictions)
- `apps/api/app/schemas/transit.py` (updated `StopArrivalPrediction.prediction_source` description)
- `apps/api/tests/test_alembic.py` (asserted `0006_trip_updates` revision)
- `apps/api/tests/test_models.py` (asserted `TripUpdate` table and model structure)
- `apps/api/tests/test_trip_updates.py` (17 unit and integration tests for TripUpdates)
- `apps/web/src/types/transit.ts` (added `TRIP_UPDATE` to `PredictionSource`)
- `apps/web/src/lib/formatters.ts` (added `TRIP_UPDATE` badge and styling)
- `apps/web/src/__tests__/formatters.test.ts` (added tests for `TRIP_UPDATE`)
- `apps/web/src/__tests__/TransitExplorer.test.tsx` (added tests for `TRIP_UPDATE` arrival card)
- `README.md` (updated Stage 4 milestones and test counts)
- `docs/architecture/overview.md` (updated architecture status with TripUpdates)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Live TripUpdates and vehicle positions are ingested on-demand or via scheduled pollers; push-based WebSocket broadcasting to client frontends is scheduled for later roadmap polish.
- **Next Authorized Step**:
  - **Stage 4, Slice 4.5**: Docker Compose Production Scaffolding & End-to-End Application Polish (or WebSocket Live Push).
