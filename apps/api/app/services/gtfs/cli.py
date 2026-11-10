"""Administrative command-line interface for GTFS ingestion."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from sqlalchemy import select

from app.database.session import async_session_factory
from app.models.feed import TransitFeed
from app.services.gtfs.service import GTFSIngestionService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gtfs-cli")


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
        description="WaitWatch GTFS Static Ingestion CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

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
    if args.command == "ingest":
        exit_code = asyncio.run(run_ingest(args))
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
