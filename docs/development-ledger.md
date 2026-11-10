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
  - **Stage 4, Slice 4.5**: Docker Compose Production Scaffolding & End-to-End Application Polish (Completed below).

---

### 2026-11-10 — Stage 4, Slice 4.5: Docker Compose Stack & Application Polish

#### Overview
Implemented the production-oriented Docker Compose stack (`docker-compose.yml`), container assets, and integration gap polish across the WaitWatch platform. Created pinned, secure container definitions for the PostgreSQL/PostGIS 16 database, FastAPI backend, and React/Nginx frontend. Designed an explicit, race-free database migration startup path (`migrate` service) that executes `alembic upgrade head` to completion before the API service begins accepting traffic, preventing concurrent migration conflicts during restarts or multi-replica scaling. Configured Docker healthchecks across all services using real native endpoints (`pg_isready`, Python standard library `GET /api/health`, and Nginx `/health`). Polished end-to-end integration gaps by normalizing `DATABASE_URL` schemes (`postgresql://` → `postgresql+asyncpg://`), expanding default API CORS origins for Compose web port 3000, normalizing API base URL trailing slashes and empty string relative paths for Nginx reverse-proxying, and providing a safe, placeholder-only `.env.example` template without usable default credentials.

#### Key Deliverables & Design Decisions
1. **Multi-Service Docker Compose Stack** (`docker-compose.yml`):
   - **Database (`db`)**: Pinned `postgis/postgis:16-3.4` with persistent volume `waitwatch-pgdata` and `pg_isready` healthcheck.
   - **Migration Runner (`migrate`)**: Dedicated one-shot service running `["alembic", "upgrade", "head"]` with `restart: "no"`. Depends on `db: { condition: service_healthy }`. Guarantees schema migrations apply exactly once before application startup, preserving restart behavior without running competing migration processes.
   - **API Backend (`api`)**: Pinned `python:3.12-slim-bookworm` container image (`waitwatch-api:0.1.0`) running Uvicorn on port 8000. Depends on `migrate: { condition: service_completed_successfully }` and `db: { condition: service_healthy }`.
   - **Web Frontend (`web`)**: Pinned `node:22-alpine3.20` + `nginx:1.30.6-alpine` multi-stage container (`waitwatch-web:0.1.0`) published on port 3000 (`${WEB_PORT:-3000}:80`). Depends on `api: { condition: service_healthy }`.
2. **Hardened FastAPI Containerization** (`apps/api/Dockerfile`, `apps/api/.dockerignore`):
   - Uses `python:3.12-slim-bookworm` with security updates and minimal packages.
   - Created unprivileged runtime user and group `waitwatch` (UID/GID 1001).
   - Zero-dependency healthcheck: executes `python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"` to verify server status and database connectivity without external curl/wget dependencies.
3. **Optimized Nginx React SPA Containerization** (`apps/web/Dockerfile`, `apps/web/nginx.conf`, `apps/web/.dockerignore`):
   - Multi-stage build with `node:22-alpine3.20` builder running `npm ci` and `npm run build`, followed by lightweight `nginx:1.30.6-alpine` runtime.
   - Nginx configured with gzip compression, long-term immutable caching for `/assets/`, SPA client-side fallback (`try_files $uri $uri/ /index.html`), dedicated unlogged healthcheck (`/health`), and internal reverse proxying for `/api/` traffic to `http://api:8000/api/`.
4. **Integration Gap Polish & Browser Networking**:
   - **Database URL Normalization** (`apps/api/app/core/config.py`): Pydantic `@field_validator("database_url", mode="before")` automatically converts `postgresql://` to `postgresql+asyncpg://`, supporting standard external connection strings without runtime driver errors.
   - **CORS Configuration** (`apps/api/app/core/config.py`): Extended default `cors_origins` to include `http://localhost:3000` and `http://127.0.0.1:3000` so browser traffic accessing the Compose web frontend can call the API without CORS rejections. Filtered empty entries in `cors_origin_list`.
   - **API Client Base URL Normalization** (`apps/web/src/lib/api.ts`): Stripped trailing slashes and preserved empty string `""` so reverse-proxied relative calls cleanly route to `/api/...`.
   - **Browser Networking Documentation**: Explicitly documented why browser code must not target Docker-internal DNS (`http://api:8000`) and provided correct host-accessible and proxied alternatives.
5. **Secure Environment Configuration Template** (`.env.example`):
   - Safe placeholders only (`replace_with_a_secure_password`, `your_delhi_transit_api_key_here`).
   - No usable default credentials committed to version control.
   - Clear explanations of required settings, Compose startup steps, and honest production disclaimers regarding secrets management, TLS termination, and managed databases.
6. **Comprehensive Unit & Integration Test Suites**:
   - Backend Pytest (138 tests total across 10 files): added 2 new tests in `test_database.py` verifying database URL normalization (`postgresql://` → `postgresql+asyncpg://`) and CORS origin string parsing/whitespace filtering.
   - Frontend Vitest (83 tests total across 6 files): added test in `api.test.ts` verifying `API_BASE_URL` normalization and request path generation.
   - Compose Structure Validation: verified with custom YAML parser assertions for service topology, image pinning, healthchecks, and dependency graph.

#### Verification Evidence
- **Backend Pytest**: 138 passed in 15.85s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero errors, 62 files formatted cleanly (`py -3.12 -m ruff check app tests alembic`, `py -3.12 -m ruff format --check app tests alembic`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall app tests alembic`).
- **Frontend Vitest**: 83 passed across 6 test suites in 7.06s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 3.86s (`npm.cmd run build`).
- **Docker Compose Configuration (Static Validation)**: Syntax, image pinning, volume persistence, dependency conditions, and healthchecks verified via static AST/YAML validation (`scratch/validate_compose.py`). Note: Docker runtime is not installed on this local Windows machine; no live `docker compose config`, `docker build`, or container smoke run was executed.

#### Changed / Added Files
- `docker-compose.yml` (multi-service stack: `db`, `migrate`, `api`, `web`, and `waitwatch-pgdata` volume)
- `.env.example` (secure environment template with placeholders and startup documentation)
- `.dockerignore` (repository root Docker build ignore rules)
- `apps/api/Dockerfile` (pinned Python 3.12 slim runtime with non-root user and healthcheck)
- `apps/api/.dockerignore` (API Docker build ignore rules)
- `apps/api/app/core/config.py` (database URL normalization and Compose CORS origins)
- `apps/api/tests/test_database.py` (tests for URL normalization and CORS list parsing)
- `apps/web/Dockerfile` (multi-stage Node build and Nginx runtime)
- `apps/web/nginx.conf` (Nginx SPA configuration with API reverse proxy and healthcheck)
- `apps/web/.dockerignore` (Web Docker build ignore rules)
- `apps/web/src/lib/api.ts` (API base URL normalization and empty string handling)
- `apps/web/src/__tests__/api.test.ts` (test for API base URL normalization)
- `README.md` (updated Docker Compose full stack guide, milestones, and test counts)
- `docs/architecture/overview.md` (documented container topology, lifecycle, and production scope)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Live vehicle positions and stop arrivals update via 30-second client polling; push-based WebSocket streaming is scheduled for future real-time enhancement.
  - Docker daemon is not installed on this development machine; Compose verification was limited to static YAML/schema structure analysis without live container execution or smoke runs.
  - Production secrets, SSL/TLS termination, and managed database hosting are external to this single-host Compose scaffold.
- **Next Roadmap Step**:
  - **Stage 5 / Future Enhancements**: WebSocket live vehicle and ETA streaming, turn-by-turn route planning, or multi-city production deployment.

---

### 2026-11-10 — Stage 4.5 Correction: Update Vulnerable Nginx Pin

#### Overview
Security review identified that `apps/web/Dockerfile` pinned `nginx:1.27.2-alpine`, which is subject to security advisories including CVE-2026-28755 (vulnerable in 1.27.2–1.29.6) and resolved in the stable 1.30.6 release. Updated the runtime base image tag in `apps/web/Dockerfile` to the official stable fixed release `nginx:1.30.6-alpine`, keeping the Node builder unchanged. Updated documentation and architecture references to reflect the new Nginx version, and clarified that Compose verification on this machine is strictly static validation as Docker is not installed locally.

#### Key Deliverables & Changes
1. **Dockerfile Base Image Correction** (`apps/web/Dockerfile`):
   - Updated runtime stage from `nginx:1.27.2-alpine` to `nginx:1.30.6-alpine`.
   - Node builder stage remains pinned at `node:22-alpine3.20`.
2. **Documentation & Version References** (`README.md`, `docs/architecture/overview.md`, `docs/development-ledger.md`):
   - Updated all references and ASCII architecture diagrams from Nginx 1.27.2 to Nginx 1.30.6.
   - Clarified Compose verification notes: the custom validator (`scratch/validate_compose.py`) is static AST/YAML validation only; because Docker is not installed on this machine, no live `docker compose config`, `docker build`, or container smoke runs were executed.

#### Verification Evidence
- **Frontend Vitest**: 83 passed across 6 test suites (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite (`npm.cmd run build`).
- **Backend Pytest**: 138 passed from Stage 4.5 (backend files untouched in this correction).
- **Static Compose Validation**: Structural assertions pass cleanly via `scratch/validate_compose.py`.
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

---

### 2026-11-10 — Stage 4, Slice 4.6: Core WebSocket Live Updates

#### Overview
Implemented the real-time WebSocket live updates architecture, closing the documented core objective gap from `PROJECT_INSTRUCTIONS.md`. Designed and implemented a lightweight, zero-broker publish/subscribe system using PostgreSQL native `LISTEN/NOTIFY` (`waitwatch_feed_updates` channel) combined with FastAPI WebSockets. Real-time vehicle positions and trip updates snapshot ingestion services atomically stage `pg_notify` within open database transactions, guaranteeing that notifications are emitted if and only if snapshot commits succeed (rollback or failed transactions publish zero events). A single managed background listener (`run_db_listener`) runs per API process via FastAPI lifespan, reconnecting with exponential backoff on disconnects without interrupting REST API service. On the client tier, a dedicated React hook (`useFeedLiveUpdates`) manages feed-scoped WebSocket subscriptions, handles ping/pong heartbeats, and invalidates matching TanStack Query caches (`["routeMap", feedSlug]` and `["arrivals", feedSlug]`) on event receipt for immediate UI synchronization. Redundant 30-second steady-state polling is paused when WebSockets are actively connected, with automatic, seamless fallback to polling on disconnect, error, or hidden tabs.

#### Key Deliverables & Design Decisions
1. **Zero-Broker PostgreSQL LISTEN/NOTIFY Event Publication** (`apps/api/app/services/realtime/events.py`):
   - Defined `FeedUpdateEvent` schema (`type="feed_update"`, `feed_id`, `feed_slug`, `update_type`, `timestamp`, `vehicle_count`, `trip_update_count`). Never includes credentials, tokens, or raw transit data.
   - `publish_feed_update`: On PostgreSQL, executes `SELECT pg_notify(:channel, :payload)` inside the active transaction. Also stages events in `session.info["_pending_feed_events"]` for in-process post-commit delivery (enabling zero-broker operation in SQLite tests).
   - `dispatch_pending_feed_events`: Invoked strictly after successful `session.commit()` to deliver in-process events.
   - `clear_pending_feed_events`: Invoked on exception or rollback to guarantee zero events are published on transaction failure.
2. **Dedicated Async Database Listener** (`apps/api/app/services/realtime/db_listener.py`):
   - Runs a single dedicated `asyncpg` connection per API process subscribed to channel `waitwatch_feed_updates`.
   - Automatic reconnection with exponential backoff (1s to 30s) on connection loss without impacting REST API availability.
   - Cleanly skips and logs when database dialect is non-PostgreSQL (e.g. SQLite unit tests).
3. **Thread-Safe WebSocket Connection Manager** (`apps/api/app/services/realtime/websocket_manager.py`):
   - `ConnectionManager` isolates client sets per `feed_slug`.
   - Enforces per-feed connection capacity bounds (`max_connections_per_feed=500`).
   - `broadcast_to_feed`: Concurrently fans out notifications to subscribed clients, pruning dead/closed sockets automatically.
   - `handle_db_notification`: Safely validates incoming JSON payloads against `FeedUpdateEvent` before fanout.
   - `close_all`: Gracefully closes all open connections on server shutdown.
4. **Feed-Scoped WebSocket Endpoint** (`apps/api/app/api/websocket.py`):
   - Endpoint `/api/v1/feeds/{feed_slug}/ws` (and root alias `/api/feeds/{feed_slug}/ws`).
   - Validates `feed_slug` against database; safely rejects non-existent feeds with WebSocket close code 1008 (Policy Violation) and clear error message.
   - Welcomes connected clients with initial connection acknowledgment.
   - Responds to client `ping` messages with `pong` heartbeats.
5. **Ingestion Services Integration** (`service.py` & `trip_update_service.py`):
   - `VehiclePositionIngestionService`: Stages `FeedUpdateEvent(update_type="vehicles")` within transaction; dispatches after commit.
   - `TripUpdateIngestionService`: Stages `FeedUpdateEvent(update_type="trip_updates")` within transaction; dispatches after commit.
6. **Frontend WebSocket Client & TanStack Query Hook** (`apps/web/src/lib/useFeedLiveUpdates.ts`):
   - Connects to feed-scoped WebSocket endpoint when a feed is selected and tab is visible.
   - Suspends connection and sets status to `"paused"` when document is hidden to conserve bandwidth and battery.
   - On `feed_update` event: updates `lastLiveUpdateAt` and invalidates `["routeMap", feedSlug]` and `["arrivals", feedSlug]`.
   - On disconnect or error: sets status to `"fallback"` and schedules reconnect with exponential backoff (1s, 2s, 4s, up to 30s). Refetches data immediately on reconnect.
   - Does not retry on code 1008 (policy violation / unknown feed).
   - Periodic 30s `ping` heartbeat to maintain socket liveliness.
7. **Frontend State & Polling Coordination** (`apps/web/src/`):
   - `appStore.ts`: Tracks `liveStatus: LiveConnectionStatus` (`"connected" | "connecting" | "disconnected" | "fallback" | "paused"`).
   - `arrivalsBoard.tsx` & `mapView.tsx`: `refetchInterval` returns `false` when `liveStatus === "connected"`, eliminating redundant 30s background queries. Automatically falls back to 30s polling when disconnected or in error.
   - Accessible status indicators: `● Live (WS)` when connected vs `● Live (30s)` on polling fallback vs `⏸ Paused` when hidden vs `⚠️ Stale` on error with cached data.
   - `Dashboard.tsx`: Header live indicator badge reflecting real-time connection state.
8. **Proxy Configurations** (`apps/web/vite.config.ts`, `apps/web/nginx.conf`):
   - Vite dev proxy configured with `ws: true` for `/api`.
   - Nginx configured with `map $http_upgrade $connection_upgrade` and `Upgrade`/`Connection` headers with 3600s timeouts.
9. **Comprehensive Backend & Frontend Test Suites**:
   - Backend Pytest: 9 new tests in `test_websocket.py` covering unknown feed rejection (code 1008), successful connection & ping/pong, feed isolation & multi-client fanout, capacity limits, transaction rollback suppression, successful commit dispatch, malformed payload resilience, non-postgres listener skipping, and listener cancellation.
   - Frontend Vitest: 9 new tests across `api.test.ts` and `useFeedLiveUpdates.test.tsx` covering URL derivation, feed path encoding, connection lifecycle, query invalidation, feed isolation, heartbeat pings, fallback on disconnect, and non-retry on code 1008.

#### Verification Evidence
- **Backend Pytest**: 147 passed in 11.71s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint errors, 67 files formatted cleanly (`py -3.12 -m ruff check apps/api; py -3.12 -m ruff format --check apps/api`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall apps/api`).
- **Frontend Vitest**: 92 passed across 7 test suites in 4.47s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 2.37s (`npm.cmd run build`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed / Added Files
- `apps/api/app/services/realtime/events.py` (event schema, PostgreSQL notify staging, post-commit dispatch)
- `apps/api/app/services/realtime/websocket_manager.py` (connection manager, feed isolation, dead socket pruning)
- `apps/api/app/services/realtime/db_listener.py` (managed PostgreSQL LISTEN task with reconnection backoff)
- `apps/api/app/api/websocket.py` (FastAPI feed-scoped WebSocket endpoint)
- `apps/api/app/api/router.py` (registered WebSocket router)
- `apps/api/app/services/realtime/service.py` (event staging and dispatch on vehicle ingestion commit)
- `apps/api/app/services/realtime/trip_update_service.py` (event staging and dispatch on trip update commit)
- `apps/api/app/main.py` (lifespan listener startup and graceful connection cleanup)
- `apps/api/tests/test_websocket.py` (9 comprehensive integration and unit tests)
- `apps/web/src/types/transit.ts` (added `FeedUpdateEvent` and `LiveConnectionStatus`)
- `apps/web/src/lib/api.ts` (WebSocket base URL derivation and feed URL formatting)
- `apps/web/src/stores/appStore.ts` (tracked live connection status and last update timestamp)
- `apps/web/src/lib/useFeedLiveUpdates.ts` (WebSocket hook with query invalidation and fallback)
- `apps/web/src/components/arrivalsBoard.tsx` (WebSocket-aware refetch interval and status badge)
- `apps/web/src/components/mapView.tsx` (WebSocket-aware refetch interval and status badge)
- `apps/web/src/pages/Dashboard.tsx` (wired live update hook and header status pill)
- `apps/web/vite.config.ts` (proxy configuration with `ws: true`)
- `apps/web/nginx.conf` (Nginx WebSocket upgrade headers and connection map)
- `apps/web/src/__tests__/api.test.ts` (WebSocket URL derivation tests)
- `apps/web/src/__tests__/useFeedLiveUpdates.test.tsx` (7 WebSocket hook unit tests)
- `README.md` (updated Stage 4 status table, Slice 4.6 milestone summary, and test counts)
- `docs/architecture/overview.md` (documented WebSocket architecture and updated status)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Turn-by-turn route planning and multi-modal trip planning remain future roadmap items.
  - Multi-city production hosting and managed cloud deployment are not yet configured.
- **Next Roadmap Step**:
  - Core project objectives (Stages 0–4 including WebSocket live updates) are fully satisfied and verified. Future scope may include turn-by-turn trip planning, user favorites, or cloud infrastructure.

### 2026-11-10 — Stage 4, Slice 4.6: Independent Audit & Quality Polish

#### Overview
Conducted an independent code review and correctness audit of the Stage 4.6 WebSocket live updates implementation. Confirmed and resolved two specific edge cases: enforcing inactive-feed rejection against `TransitFeed.feed_status`, and implementing event deduplication to ensure exactly-once client broadcast across PostgreSQL `LISTEN/NOTIFY` and in-process commit dispatches. Re-verified secret omission in logs and payloads, rollback atomicity, feed fanout isolation, client reconnect backoff, and reverse proxy upgrade configurations.

#### Key Findings & Corrections
1. **Inactive Feed Rejection** (`apps/api/app/api/websocket.py`):
   - Audited the `TransitFeed` model (`feed_status: Mapped[str]` with `"active"`, `"inactive"`, `"maintenance"`, `"error"` values).
   - The initial WebSocket endpoint verified feed existence but did not check `feed_status`.
   - Updated `feed_live_updates_ws` to reject inactive feeds (`feed.feed_status != "active"`) with code 1008 ("Feed is not active") and descriptive error JSON payload, stopping client reconnect loops cleanly.
   - Added Pytest unit test `test_websocket_inactive_feed_rejected` in `apps/api/tests/test_websocket.py`.
2. **Duplicate Event Deduplication & Idempotent Broadcast** (`events.py`, `websocket_manager.py`, `useFeedLiveUpdates.ts`):
   - Audited the event publication flow: when ingestion runs within the API process on PostgreSQL, `publish_feed_update` stages `pg_notify` and `session.commit()` triggers PostgreSQL NOTIFY to `run_db_listener`, while the caller also invokes `dispatch_pending_feed_events`.
   - Added a unique `event_id: str` (UUID4 hex) to `FeedUpdateEvent` schema (`events.py` and `transit.ts`).
   - Implemented thread-safe in-memory LRU deduplication in `ConnectionManager` (`apps/api/app/services/realtime/websocket_manager.py`). If an event with the same `event_id` (or fallback key) was already broadcast in the recent cache window (1,000 entries), duplicate arrivals from PostgreSQL NOTIFY or local dispatch are dropped cleanly.
   - Added client-side defense-in-depth deduplication in `useFeedLiveUpdates.ts` via `lastProcessedEventRef` to ignore duplicate frames and avoid redundant TanStack Query cache invalidations.
   - Added Pytest unit test `test_websocket_event_deduplication` and Vitest unit test in `useFeedLiveUpdates.test.tsx`.
3. **Rollback & Error Isolation Audit**:
   - Confirmed `clear_pending_feed_events` clears staged events on transaction failure or rollback in both vehicle position and trip update ingestion services.
   - Confirmed zero credentials, transit API keys, private URLs, or raw protobuf/JSON feed payloads exist in `FeedUpdateEvent` models, WebSocket frames, or server logs.
4. **Fanout & Proxy Verification**:
   - Re-verified strict feed isolation in `ConnectionManager._connections` and dead connection cleanup.
   - Re-verified Vite dev proxy (`ws: true`) and Nginx reverse proxy configuration (`map $http_upgrade $connection_upgrade` with `Upgrade`/`Connection` headers).

#### Verification Evidence
- **Backend Pytest**: 149 passed in 11.54s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors (`py -3.12 -m ruff check .; py -3.12 -m ruff format --check .`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall app tests`).
- **Frontend Vitest**: 93 passed across 7 test suites in 4.97s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 2.40s (`npm.cmd run build`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed / Added Files
- `apps/api/app/api/websocket.py` (enforced inactive feed rejection with code 1008)
- `apps/api/app/services/realtime/events.py` (added `event_id` field with UUID4 default)
- `apps/api/app/services/realtime/websocket_manager.py` (added thread-safe LRU event deduplication)
- `apps/api/tests/test_websocket.py` (added tests for inactive feed rejection and event deduplication)
- `apps/web/src/types/transit.ts` (added `event_id` to `FeedUpdateEvent`)
- `apps/web/src/lib/useFeedLiveUpdates.ts` (added client-side event deduplication)
- `apps/web/src/__tests__/useFeedLiveUpdates.test.tsx` (added client-side deduplication test)
- `README.md` (updated feature summary and test counts)
- `docs/architecture/overview.md` (documented inactive feed rejection and event deduplication)
- `docs/development-ledger.md` (this audit entry)

### 2026-11-10 — Stage 4, Slice 4.6: Review Corrections & Log Security Polish

#### Overview
Addressed three targeted code review findings on the Stage 4.6 implementation:
1. Hardened logging in `ConnectionManager.handle_db_notification` to emit only the safe exception type (`error_type=...`), ensuring validation errors and malformed inputs never leak rejected payload values or URLs into logs.
2. Upgraded `_deduplicate_event` to true bounded LRU cache semantics by moving duplicate hits to the most-recently-used end of the `OrderedDict`. Derived the deduplication key from raw decoded payload data prior to Pydantic model validation, making the deterministic composite fallback key reachable for legacy payloads without `event_id`.
3. Updated `README.md` feature summary to clearly separate implemented functionality (Slices 1.1–4.6) from future roadmap items without overstating scope.

#### Key Deliverables & Test Verification
1. **Log Sanitization on Malformed Payloads** (`apps/api/app/services/realtime/websocket_manager.py`):
   - Replaced logging of raw exception objects `%s` with `error_type=%s` (`type(exc).__name__`), preventing Pydantic validation error strings from printing rejected input values.
   - Added Pytest caplog test `test_websocket_manager_malformed_payload_does_not_log_sensitive_values` proving sentinel tokens, passwords, and private URLs in malformed JSON or invalid schema payloads are never emitted in logs.
2. **True LRU Cache Semantics & Reachable Dedup Fallback** (`websocket_manager.py`):
   - Updated `_deduplicate_event` to execute `self._recent_events.move_to_end(event_key)` on duplicate hits, ensuring genuine Least Recently Used eviction.
   - Added Pytest test `test_websocket_manager_lru_recency_and_eviction` verifying recency preservation and eviction order when capacity is reached.
   - Evaluated raw payload `data.get("event_id")` before `FeedUpdateEvent.model_validate(data)`, falling back to `{slug}:{update_type}:{timestamp}` if absent.
   - Added Pytest test `test_websocket_manager_legacy_payload_fallback_deduplication` proving legacy messages lacking `event_id` are cleanly deduplicated.
3. **Documentation Alignment** (`README.md`):
   - Replaced "Features (Planned) - All features listed below are planned and not yet implemented" with separate "Implemented Functionality" and "Future Roadmap" sections.
   - Updated total test suite counts: 152 Pytest backend tests and 93 Vitest frontend tests.

#### Verification Evidence
- **Backend Pytest**: 152 passed in 12.18s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors (`py -3.12 -m ruff check .; py -3.12 -m ruff format --check .`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall app tests`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed / Added Files
- `apps/api/app/services/realtime/websocket_manager.py` (safe error logging, true LRU move_to_end, pre-validation dedup key extraction)
- `apps/api/tests/test_websocket.py` (added caplog log security test, LRU recency/eviction test, and legacy fallback dedup test)
- `README.md` (updated feature section to reflect implemented vs roadmap scope, updated test counts)
- `docs/development-ledger.md` (this ledger entry)

### 2026-11-10 — Stage 4, Slice 4.6: Duplicate-Drop Log Safety Polish

#### Overview
Addressed a targeted log-safety review on the duplicate-event suppression path in `ConnectionManager.handle_db_notification`. The debug log statement previously interpolated `dedup_key` and `data.get("feed_slug")` (values derived from raw notification payloads prior to model validation). Replaced this with a constant debug message that emits zero raw or unvalidated notification fields.

#### Key Deliverables & Test Verification
1. **Constant Debug Message on Duplicate Drop** (`apps/api/app/services/realtime/websocket_manager.py`):
   - Replaced `logger.debug("Dropping duplicate feed update event '%s' for feed '%s'", dedup_key, data.get("feed_slug"))` with constant `logger.debug("Dropping duplicate feed update notification")`.
   - Prevents any sentinel tokens, URLs, or malicious strings in raw `event_id` or `feed_slug` payload fields from appearing in debug logs.
2. **Focused Caplog Regression Test** (`apps/api/tests/test_websocket.py`):
   - Added `test_websocket_manager_duplicate_drop_does_not_log_sensitive_values` with `caplog.at_level(logging.DEBUG)`.
   - Injected synthetic sentinel values in `event_id` (`sensitive-event-id-key-456`) and `feed_slug` (`secret-feed-token-xyz789`).
   - Verified that when the duplicate event is dropped, the constant message is emitted and neither sentinel value appears anywhere in the captured log text.

#### Verification Evidence
- **Backend Pytest**: 153 passed in 13.02s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors (`py -3.12 -m ruff check .; py -3.12 -m ruff format --check .`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall app tests`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed Files
- `apps/api/app/services/realtime/websocket_manager.py` (constant debug message on duplicate drop)
- `apps/api/tests/test_websocket.py` (added caplog regression test for duplicate drop logging)
- `README.md` (updated test suite count)
- `docs/development-ledger.md` (this ledger entry)

---

### 2026-11-10 — Stage 5, Slice 5.1: Direct Route Stop-to-Stop Trip Planner

#### Overview
Implemented the direct route stop-to-stop trip planner, fulfilling the first vertical slice of the Stage 5 trip planning milestone. Designed and delivered a fast, feed-scoped query path that finds scheduled and live direct transit journeys between any two stops on the same route or trip without requiring complex multi-transfer graph algorithms (RAPTOR/CSA). Integrated active GTFS calendar service evaluation (including `calendar_dates` exception overrides), departure time filtering with GTFS overnight/extended hours support (>24:00), and GTFS-Realtime `TripUpdate` delay enrichment to compute real-time adjusted departure/arrival times and delay badges. Built an accessible, responsive React frontend component (`TripPlanner`) with stop selectors, swap control (`⇄`), departure time input, TanStack Query integration, itinerary cards with route color badges, duration and intermediate stop counts, and interactive route map focus.

#### Key Deliverables & Design Decisions
1. **Direct Trip Plan Schemas** (`apps/api/app/schemas/transit.py`):
   - `StopPlanDetailResponse`: Stop metadata (`stop_id`, `name`, `latitude`, `longitude`, `stop_sequence`), scheduled time (`HH:MM:SS`), real-time adjusted estimated time (`HH:MM:SS`), and optional delay seconds.
   - `TripItineraryResponse`: Direct route journey option (`route_id`, `route_short_name`, `route_long_name`, `route_color`, `text_color`, `route_type`, `trip_id`, `trip_headsign`, `direction_id`), origin and destination stop details, trip duration in minutes, intermediate stops count, and delay status (`REALTIME_DELAYED`, `REALTIME_EARLY`, `REALTIME_ON_TIME`, `SCHEDULED`).
   - `TripPlanResponse`: Feed-scoped plan envelope (`feed_slug`, `origin_stop_id`, `destination_stop_id`, `target_date`, `target_time`, `itineraries`).
2. **Direct Trip Planning Endpoint & ANSI SQL Query** (`apps/api/app/api/transit.py`):
   - Endpoint: `GET /api/v1/feeds/{feed_slug}/plan`. Validates feed existence, ensures origin and destination stops are distinct (returning HTTP 400 otherwise), and verifies both stops exist within the target feed (returning HTTP 404 otherwise).
   - Single-query ANSI SQL join of `StopTime` aliased twice on `Trip.id` (`st_origin` and `st_dest`), joined with `Route`, `origin_stop`, and `dest_stop`, enforcing `st_origin.stop_sequence < st_dest.stop_sequence`. This naturally excludes trips traveling in the opposite direction.
   - Calendar evaluation: resolves active service IDs for target date (day-of-week matching against `Calendar` plus `CalendarDate` exception overrides). When feeds lack calendar records, safely falls back to allowing all scheduled trips.
   - Departure time filtering: filters `st_origin.departure_time >= target_time`, handling GTFS extended hours (`>24:00`).
   - Sanitized HTTP 503 database unavailability error handling without credential leakage.
3. **GTFS-Realtime Delay Enrichment** (`transit.py`):
   - Batch-queries recent `TripUpdate` records for all matching `trip_id`s in a single query.
   - Associates delay seconds and computes real-time adjusted arrival/departure times (`_add_delay_to_time`).
   - Assigns passenger-facing real-time status badges (`REALTIME_DELAYED`, `REALTIME_EARLY`, `REALTIME_ON_TIME`, or `SCHEDULED`).
4. **Web Client Integration** (`apps/web/src/types/transit.ts`, `apps/web/src/lib/api.ts`):
   - Exported TypeScript interfaces: `StopPlanDetail`, `TripPlanRealtimeStatus`, `TripItinerary`, and `TripPlanResponse`.
   - Added client function `planTrip(feedSlug, originStopId, destinationStopId, time?, date?, limit?)` encoding query parameters properly.
5. **Interactive Trip Planner UI** (`apps/web/src/components/tripPlanner.tsx`, `apps/web/src/pages/Dashboard.tsx`):
   - Stop dropdowns populated dynamically from feed stops with `isLoading` disabled states.
   - Stop swap button (`⇄`) allowing instantaneous flipping of origin and destination stops.
   - Departure time input with "Reset to Now" button.
   - Validation alerts when origin and destination stops are identical.
   - Loading spinner, retryable error alert, and clean empty state ("No Direct Trips Found").
   - Itinerary cards with route badges styled in agency route colors, headsigns, departure and arrival times, real-time status badges, duration, intermediate stop counts ("Non-stop" vs "X stops"), and "View Route on Map →" button that triggers map focus on the route.
   - Integrated tab navigation on `Dashboard.tsx` (`🚏 Stop Explorer & Arrivals` vs `🧭 Direct Trip Planner`).
6. **Comprehensive Backend & Frontend Test Suites**:
   - Backend Pytest (12 tests in `test_trip_plan.py`): Unknown feed (404), identical stops (400), unknown origin/destination stops (404), direct trip matching & duration/stop counts, reverse direction exclusion, departure time filtering, real-time delay integration, calendar active service filtering, unconfigured calendar fallback, limit parameter, and 503 database error handling.
   - Frontend Vitest (9 tests in `tripPlanner.test.tsx`, 1 test in `api.test.ts`, 1 test in `Dashboard.test.tsx`): URL parameter formatting, no-feed prompt, stop dropdown population, stop swap, identical stops alert, itinerary rendering with real-time badges and intermediate stop counts, route selection map trigger, empty state, error alert and retry, and departure time input/reset.

#### Verification Evidence
- **Backend Pytest**: 165 passed across 12 test suites in 14.98s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors, 69 files formatted cleanly (`py -3.12 -m ruff check apps/api; py -3.12 -m ruff format --check apps/api`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall apps/api/app apps/api/tests`).
- **Frontend Vitest**: 104 passed across 8 test suites in 4.90s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Frontend Production Build**: Built cleanly with Vite in 2.78s (`npm.cmd run build`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed / Added Files
- `apps/api/app/schemas/transit.py` (added `StopPlanDetailResponse`, `TripItineraryResponse`, `TripPlanResponse`)
- `apps/api/app/api/transit.py` (added `_get_active_service_ids_for_date`, time helpers, and `GET /feeds/{feed_slug}/plan` endpoint)
- `apps/api/tests/test_trip_plan.py` (12 comprehensive trip planning integration tests)
- `apps/web/src/types/transit.ts` (added trip plan TypeScript types)
- `apps/web/src/lib/api.ts` (added `planTrip` API client method)
- `apps/web/src/components/tripPlanner.tsx` (accessible direct trip planner component with itinerary cards)
- `apps/web/src/pages/Dashboard.tsx` (added tab navigation and wired `TripPlanner`)
- `apps/web/src/__tests__/tripPlanner.test.tsx` (9 comprehensive trip planner component tests)
- `apps/web/src/__tests__/api.test.ts` (unit test for `planTrip` URL parameter formatting)
- `apps/web/src/__tests__/Dashboard.test.tsx` (test for tab switching)
- `README.md` (updated feature matrix, milestones, and test counts)
- `docs/architecture/overview.md` (documented trip planner API and query design)
- `docs/development-ledger.md` (this ledger entry)

#### Current Limitations & Next Roadmap Steps
- **Limitations**:
  - Trip planning is direct stop-to-stop on the same vehicle/trip; multi-transfer itineraries (transferring between routes or modes) remain a future enhancement (e.g. CSA / RAPTOR graph search).
  - Production hosting and cloud deployment remain external to local Compose scaffolding.
- **Next Roadmap Steps**:
  - Multi-transfer trip planning algorithm evaluation or user bookmarks/favorites.

---

### 2026-11-10 — Stage 5, Slice 5.1 Correction: Agency Timezone for Default Trip Planning Instant

#### Overview
Addressed a correctness finding in `apps/api/app/api/transit.py` where omitted `date` and `time` parameters previously defaulted from `datetime.now(UTC)`. Per the GTFS Schedule Reference, transit schedules operate in the agency's local service timezone (`agency.agency_timezone`). Deriving defaults in UTC risked querying against the wrong local service day or daytime window for non-UTC agencies (e.g. 02:30 UTC is 21:30 local on the preceding calendar day in US Eastern).

#### Key Deliverables & Design Decisions
1. **Feed Local Timezone Resolution** (`apps/api/app/api/transit.py`):
   - Reused existing safe timezone resolver `resolve_feed_timezone` from `app.services.prediction`.
   - Queries the stored IANA agency timezone (`Agency.timezone`) for the target feed.
   - Evaluates `origin_stop.timezone` precedence (in accordance with GTFS specification where stop timezone overrides agency timezone when defined), falling back to `Agency.timezone`, and ultimately falling back safely to `UTC` without raising unhandled exceptions or requiring new dependencies or database migrations.
2. **Unified Local Instant Derivation**:
   - Helper function `_get_current_utc()` captures a single current UTC instant (`datetime.now(UTC)`).
   - Converts the UTC instant to the resolved local timezone (`local_now = now_utc.astimezone(feed_tz)`).
   - Derives both default `target_date` (`local_now.date()`) and default `target_time` (`local_now.strftime("%H:%M:%S")`) from that identical local instant, preventing day-boundary discrepancies.
   - Preserves explicitly supplied query parameters: explicit `date` overrides default date; explicit `time` overrides default time (with support for GTFS extended hours e.g. `25:30:00` and `HH:MM` zero-padding).
3. **Deterministic Backend Regression Coverage** (`apps/api/tests/test_trip_plan.py`):
   - `test_plan_trip_default_date_time_uses_agency_timezone`: Fixes UTC instant to `2026-11-10 02:30:00 UTC` and proves `America/New_York` (UTC-5) agency resolves to local date `2026-11-09` and time `21:30:00`.
   - `test_plan_trip_explicit_date_time_overrides_agency_timezone`: Verifies explicit dates/times completely override local defaults, including partial overrides (date-only, time-only) and GTFS extended hours (`25:30:00`).
   - `test_plan_trip_stop_timezone_overrides_agency_timezone`: Verifies `origin_stop.timezone` overrides agency timezone when configured.
   - `test_plan_trip_invalid_timezone_safely_falls_back_to_utc`: Verifies corrupted or unresolvable timezones fall back safely to UTC without throwing errors.

#### Verification Evidence
- **Backend Pytest**: 169 passed across 12 test suites in 16.97s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors, 69 files formatted cleanly (`py -3.12 -m ruff check apps/api; py -3.12 -m ruff format --check apps/api`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall apps/api/app apps/api/tests`).
- **Frontend Vitest**: 104 passed across 8 test suites in 5.87s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run typecheck`).
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed Files
- `apps/api/app/api/transit.py` (feed/stop timezone resolution and unified local default date/time derivation)
- `apps/api/tests/test_trip_plan.py` (added 4 deterministic timezone regression tests)
- `README.md` (updated milestone notes and test suite counts)
- `docs/architecture/overview.md` (documented timezone resolution logic)
- `docs/development-ledger.md` (this ledger entry)

---

### 2026-11-10 — Project Deployability & Testability Checkpoint

#### Overview
Conducted a comprehensive, code-level deployability and testability readiness audit of the WaitWatch repository against a concrete operational checklist: configuration and secrets handling, migration integrity, container health and readiness checks, application lifecycle (startup/shutdown), CORS and environment isolation, reproducible local setup, test/lint/typecheck/build gates, CI workflow coverage, and operational constraints. Hardened `.github/workflows/backend.yml` to mirror all local quality gates by adding `ruff format --check` and `python -m compileall`. Confirmed that all 169 backend Pytest tests, all 104 frontend Vitest tests, TypeScript compilation, and production Vite asset builds pass cleanly.

#### Readiness Checklist Audit Summary
1. **Configuration & Secrets Handling**:
   - Pydantic Settings in `apps/api/app/core/config.py` loads environment variables with URL normalization (`postgresql://` to `postgresql+asyncpg://`) and credential masking via `sanitized_database_url`.
   - `.env.example` provides a non-functional, template-only configuration with explicit production guidance. Zero secrets, credentials, or private tokens exist in git history or working tree.
2. **Database Migrations**:
   - Alembic migration chain comprises 6 sequential, fully reversible revisions (`0001_initial_transit_models` through `0006_trip_updates`).
   - Verified offline static SQL generation via `alembic upgrade head --sql`.
   - Docker Compose uses an isolated one-shot migration runner (`waitwatch-migrate`) with `condition: service_completed_successfully` before API startup.
3. **Health & Readiness Endpoints**:
   - Backend exposes `/api/health` and `/api/v1/health` with non-leaking real database connectivity testing via `SELECT 1` with timeout protection.
   - Frontend Nginx exposes `/health` returning HTTP 200 text status.
   - Docker Compose and Dockerfile healthchecks verify services natively (`pg_isready` for Postgres, Python stdlib `urllib` for API without curl dependencies, and alpine `wget` for web).
4. **Application Lifecycle & Clean Shutdown**:
   - FastAPI lifespan in `main.py` initializes database listener and handles graceful shutdown: sets stop event, cancels listener task with timeout, closes all WebSocket connections (`close_all()`), and disposes engine pool.
5. **CORS & Environment Setup**:
   - Standard CORS default origins cover web ports (3000, 5173 on localhost and 127.0.0.1) and allow environment expansion.
   - Frontend Vite environment variables (`VITE_API_URL`, `VITE_MAP_TILE_URL`, `VITE_POLLING_INTERVAL_SEC`) are supported via build arguments and runtime defaults.
6. **CI Gate Hardening** (`.github/workflows/backend.yml`):
   - Aligned GitHub Actions Backend CI with local quality gates: added `ruff format --check app/ tests/` and `python -m compileall app/ tests/` alongside existing `ruff check` and pytest.
7. **Operational Limitations & Remaining Runtime Validation**:
   - Docker daemon is not installed on this local development host; container image builds, multi-container networking, and live Compose runs remain runtime validation tasks for container-enabled environments.
   - External transit feed polling remains in offline/mock mode; live upstream transit API ingestion is disabled by policy.

#### Verification Evidence
- **Backend Pytest**: 169 passed across 12 test suites in 14.44s (`cd apps/api && py -3.12 -m pytest`).
- **Backend Ruff**: Zero lint or formatting errors (`py -3.12 -m ruff check apps/api; py -3.12 -m ruff format --check apps/api`).
- **Backend Compilation**: Clean compilation across all files (`py -3.12 -m compileall apps/api/app apps/api/tests`).
- **Frontend Vitest**: 104 passed across 8 test suites in 5.45s (`cd apps/web && npm.cmd test -- --run`).
- **Frontend ESLint & Typecheck**: Clean with 0 warnings or errors (`npm.cmd run lint`, `npm.cmd run type-check`).
- **Frontend Production Build**: Built cleanly with Vite in 2.65s (`npm.cmd run build`).
- **Alembic Offline SQL Generation**: Generated clean PostgreSQL DDL through `0006_trip_updates`.
- **Git Diff & Whitespace**: Zero whitespace errors (`git diff --check`).
- **Secret Scan**: Clean, zero secrets detected.

#### Changed Files
- `.github/workflows/backend.yml` (enforced ruff format and compileall in CI)
- `docs/development-ledger.md` (this readiness checkpoint entry)
