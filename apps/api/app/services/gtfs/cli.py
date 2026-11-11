"""Administrative command-line interface for GTFS ingestion."""

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.session import async_session_factory
from app.models.feed import TransitFeed
from app.services.gtfs.downloader import SENSITIVE_PARAM_NAMES
from app.services.gtfs.service import GTFSIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gtfs-cli")


def _is_safe_http_url(value: str) -> bool:
    """Validate an HTTP URL without credentials embedded in the URL itself."""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        return not any(
            key.lower() in SENSITIVE_PARAM_NAMES
            for key, _value in parse_qsl(parsed.query, keep_blank_values=True)
        )
    except ValueError:
        return False


async def run_register_feed(args: argparse.Namespace) -> int:
    """Register one transit feed for later static or realtime ingestion."""
    slug = args.slug.strip()
    city_name = args.city_name.strip()
    static_url = args.static_url.strip()
    realtime_vehicle_url = args.vehicle_positions_url.strip() or None
    realtime_trip_updates_url = args.trip_updates_url.strip() or None
    realtime_alerts_url = args.alerts_url.strip() or None
    api_key_env_var = args.api_key_env_var.strip() or None

    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 64:
        logger.error("Feed slug must be lowercase letters, numbers, and hyphens")
        return 1
    if not city_name or len(city_name) > 100:
        logger.error("City name is required and must be at most 100 characters")
        return 1
    if len(static_url) > 2048 or not _is_safe_http_url(static_url):
        logger.error("Static GTFS source must be a safe absolute HTTP(S) URL")
        return 1

    realtime_urls = (
        realtime_vehicle_url,
        realtime_trip_updates_url,
        realtime_alerts_url,
    )
    if any(
        url and (len(url) > 2048 or not _is_safe_http_url(url)) for url in realtime_urls
    ):
        logger.error("Realtime sources must be safe absolute HTTP(S) URLs")
        return 1
    if args.enable_live_tracking and not any(
        (realtime_vehicle_url, realtime_trip_updates_url)
    ):
        logger.error("Live tracking requires a vehicle-positions or trip-updates URL")
        return 1
    if api_key_env_var and (
        len(api_key_env_var) > 100
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env_var)
    ):
        logger.error("API key setting must be an environment-variable name")
        return 1

    async with async_session_factory() as session:
        existing_stmt = select(TransitFeed.id).where(TransitFeed.slug == slug)
        existing_id = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing_id is not None:
            logger.error("Feed slug is already registered; no changes were made")
            return 1

        feed = TransitFeed(
            city_name=city_name,
            slug=slug,
            static_gtfs_url=static_url,
            realtime_vehicle_positions_url=realtime_vehicle_url,
            realtime_trip_updates_url=realtime_trip_updates_url,
            realtime_alerts_url=realtime_alerts_url,
            api_key_env_var=api_key_env_var,
            is_live_tracking_enabled=args.enable_live_tracking,
        )
        session.add(feed)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.error("Feed slug is already registered; no changes were made")
            return 1
        except Exception as exc:
            await session.rollback()
            logger.error("Feed registration failed (error_type=%s)", type(exc).__name__)
            return 1

        logger.info(
            "Registered transit feed id=%d slug=%s live_tracking=%s",
            feed.id,
            feed.slug,
            feed.is_live_tracking_enabled,
        )
        return 0


async def run_ingest(args: argparse.Namespace) -> int:
    """Execute GTFS static ingestion from CLI arguments."""
    async with async_session_factory() as session:
        feed_id = args.feed_id

        if feed_id is None and args.slug:
            stmt = select(TransitFeed.id).where(TransitFeed.slug == args.slug)
            result = await session.execute(stmt)
            feed_id = result.scalar_one_or_none()
            if feed_id is None:
                logger.error("No transit feed found with slug %r", args.slug)
                return 1

        if feed_id is None:
            logger.error("Must specify either --feed-id or --slug")
            return 1

        service = GTFSIngestionService(session)

        try:
            if args.file:
                archive_path = Path(args.file)
                if not archive_path.is_file():
                    logger.error("Archive file not found: %s", archive_path)
                    return 1
                logger.info("Importing from local archive: %s", archive_path)
                stats = await service.ingest_archive(
                    feed_id=feed_id,
                    archive_source=archive_path,
                    batch_size=args.batch_size,
                )
            else:
                logger.info("Importing from remote URL for feed ID %d", feed_id)
                stats = await service.ingest_remote_feed(
                    feed_id=feed_id,
                    batch_size=args.batch_size,
                )

            logger.info("=" * 60)
            logger.info("Ingestion completed successfully!")
            logger.info("  Feed ID:        %d", stats.feed_id)
            logger.info("  Agencies:       %d", stats.agencies_count)
            logger.info("  Routes:         %d", stats.routes_count)
            logger.info("  Stops:          %d", stats.stops_count)
            logger.info("  Calendars:      %d", stats.calendars_count)
            logger.info("  Calendar Dates: %d", stats.calendar_dates_count)
            logger.info("  Trips:          %d", stats.trips_count)
            logger.info("  Stop Times:     %d", stats.stop_times_count)
            logger.info("  Imported At:    %s", stats.imported_at.isoformat())
            logger.info("=" * 60)
            return 0
        except Exception as exc:
            logger.error("Ingestion failed: %s", exc)
            return 1


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="gtfs-cli",
        description="WaitWatch GTFS feed registration and static ingestion CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_parser = subparsers.add_parser(
        "register",
        help="Register a feed without exposing feed-management over the public API",
    )
    register_parser.add_argument("--slug", required=True, help="Lowercase feed slug")
    register_parser.add_argument("--city-name", required=True, help="Display city name")
    register_parser.add_argument(
        "--static-url", required=True, help="Authorized static GTFS source URL"
    )
    register_parser.add_argument(
        "--vehicle-positions-url", default="", help="Optional GTFS-RT vehicle URL"
    )
    register_parser.add_argument(
        "--trip-updates-url", default="", help="Optional GTFS-RT trip-updates URL"
    )
    register_parser.add_argument(
        "--alerts-url", default="", help="Optional GTFS-RT alerts URL"
    )
    register_parser.add_argument(
        "--api-key-env-var",
        default="",
        help="Name of the environment variable holding a provider key; never the key",
    )
    register_parser.add_argument(
        "--enable-live-tracking",
        action="store_true",
        help="Enable live tracking when an authorized realtime source is configured",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Ingest a static GTFS feed")
    ingest_parser.add_argument("--feed-id", type=int, help="Internal transit feed ID")
    ingest_parser.add_argument("--slug", type=str, help="Feed slug / city identifier")
    ingest_parser.add_argument(
        "--file", type=str, help="Optional path to local GTFS zip archive"
    )
    ingest_parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Batch chunk size for database inserts (default 1000)",
    )

    args = parser.parse_args()
    if args.command == "register":
        exit_code = asyncio.run(run_register_feed(args))
        sys.exit(exit_code)
    if args.command == "ingest":
        exit_code = asyncio.run(run_ingest(args))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
