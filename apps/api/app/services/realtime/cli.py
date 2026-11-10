"""Administrative command-line interface for GTFS-Realtime vehicle position polling."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.feed import TransitFeed
from app.services.realtime.service import VehiclePositionIngestionService
from app.services.realtime.trip_update_service import TripUpdateIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("realtime-cli")


async def run_poll_vehicles(args: argparse.Namespace) -> int:
    """Execute realtime polling for vehicle positions and configured trip updates."""
    async with async_session_factory() as session:
        feed = None
        if args.feed_id is not None:
            stmt = select(TransitFeed).where(TransitFeed.id == args.feed_id)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()
        elif args.slug:
            stmt = select(TransitFeed).where(TransitFeed.slug == args.slug)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()
        else:
            logger.error("Must specify either --feed-id or --slug")
            return 1

        if not feed:
            logger.error(
                "Feed not found (feed_id=%s, slug=%s)", args.feed_id, args.slug
            )
            return 1

        # Local file mode: strictly offline, ingests only the provided file
        if args.file:
            path = Path(args.file)
            if not path.is_file():
                logger.error("Protobuf payload file not found: %s", path)
                return 1
            logger.info("Reading protobuf payload from file: %s", path)
            raw_bytes = path.read_bytes()

            service = VehiclePositionIngestionService()
            try:
                count = await service.ingest_for_feed(
                    session, feed, raw_bytes=raw_bytes
                )
                logger.info("=" * 60)
                logger.info("GTFS-Realtime offline vehicle position import successful!")
                logger.info("  Feed:              %s (%s)", feed.city_name, feed.slug)
                logger.info("  Vehicles Ingested: %d", count)
                logger.info("  Last Poll At:      %s", feed.last_realtime_poll_at)
                logger.info("=" * 60)
                return 0
            except Exception as exc:
                logger.error("Offline vehicle position import failed: %s", exc)
                return 1

        # Online poll cycle: fetch vehicle positions and configured trip updates
        vp_service = VehiclePositionIngestionService()
        try:
            vp_count = await vp_service.ingest_for_feed(session, feed)
        except Exception as exc:
            logger.error(
                "Vehicle position poll failed for feed '%s': %s", feed.slug, exc
            )
            return 1

        # If feed has realtime_trip_updates_url, ingest trip updates in same cycle
        tu_count: int | None = None
        tu_error: str | None = None
        if feed.realtime_trip_updates_url:
            tu_service = TripUpdateIngestionService()
            try:
                tu_count = await tu_service.ingest_for_feed(session, feed)
            except Exception as exc:
                tu_error = str(exc)
                logger.warning(
                    "Trip update ingestion failed for feed '%s': %s "
                    "(vehicle observations preserved)",
                    feed.slug,
                    exc,
                )

        logger.info("=" * 60)
        logger.info("GTFS-Realtime poll cycle successful!")
        logger.info("  Feed:              %s (%s)", feed.city_name, feed.slug)
        logger.info("  Vehicles Ingested: %d", vp_count)
        if feed.realtime_trip_updates_url:
            if tu_error is not None:
                logger.info(
                    "  Trip Updates:      failed (%s, vehicle data preserved)",
                    tu_error,
                )
            else:
                logger.info("  Trip Updates:      %d ingested", tu_count or 0)
        else:
            logger.info(
                "  Trip Updates:      skipped (no realtime_trip_updates_url configured)"
            )
        logger.info("  Last Poll At:      %s", feed.last_realtime_poll_at)
        logger.info("=" * 60)
        return 0


async def run_poll_trip_updates(args: argparse.Namespace) -> int:
    """Execute trip updates polling from CLI arguments."""
    async with async_session_factory() as session:
        feed = None
        if args.feed_id is not None:
            stmt = select(TransitFeed).where(TransitFeed.id == args.feed_id)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()
        elif args.slug:
            stmt = select(TransitFeed).where(TransitFeed.slug == args.slug)
            result = await session.execute(stmt)
            feed = result.scalar_one_or_none()
        else:
            logger.error("Must specify either --feed-id or --slug")
            return 1

        if not feed:
            logger.error(
                "Feed not found (feed_id=%s, slug=%s)", args.feed_id, args.slug
            )
            return 1

        raw_bytes: bytes | None = None
        if args.file:
            path = Path(args.file)
            if not path.is_file():
                logger.error("Protobuf payload file not found: %s", path)
                return 1
            logger.info("Reading protobuf payload from file: %s", path)
            raw_bytes = path.read_bytes()

        service = TripUpdateIngestionService()
        try:
            count = await service.ingest_for_feed(session, feed, raw_bytes=raw_bytes)
            logger.info("=" * 60)
            logger.info("GTFS-Realtime trip update poll successful!")
            logger.info("  Feed:                  %s (%s)", feed.city_name, feed.slug)
            logger.info("  Trip Updates Ingested: %d", count)
            logger.info("  Last Poll At:          %s", feed.last_realtime_poll_at)
            logger.info("=" * 60)
            return 0
        except Exception as exc:
            logger.error("Trip update poll failed: %s", exc)
            return 1


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="realtime-cli",
        description="WaitWatch GTFS-Realtime Polling CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    poll_parser = subparsers.add_parser(
        "poll-vehicles",
        help="Poll vehicle positions and configured trip updates for a feed",
    )
    poll_parser.add_argument("--feed-id", type=int, help="Internal transit feed ID")
    poll_parser.add_argument("--slug", type=str, help="Feed slug / city identifier")
    poll_parser.add_argument(
        "--file",
        type=str,
        help="Optional path to local serialized vehicle positions FeedMessage file",
    )

    tu_parser = subparsers.add_parser(
        "poll-trip-updates",
        help="Fallback operator poller for trip updates only",
    )
    tu_parser.add_argument("--feed-id", type=int, help="Internal transit feed ID")
    tu_parser.add_argument("--slug", type=str, help="Feed slug / city identifier")
    tu_parser.add_argument(
        "--file",
        type=str,
        help="Optional path to local serialized protobuf FeedMessage file",
    )

    args = parser.parse_args()

    if args.command == "poll-vehicles":
        exit_code = asyncio.run(run_poll_vehicles(args))
        sys.exit(exit_code)
    elif args.command == "poll-trip-updates":
        exit_code = asyncio.run(run_poll_trip_updates(args))
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
