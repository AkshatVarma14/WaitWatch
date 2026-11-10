"""GTFS static feed ingestion orchestration service."""

import logging
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feed import TransitFeed
from app.services.gtfs.archive import extract_gtfs_tables
from app.services.gtfs.downloader import download_gtfs_feed
from app.services.gtfs.exceptions import (
    GTFSDownloadError,
    GTFSIngestionError,
    GTFSPersistenceError,
)
from app.services.gtfs.importer import IngestionStats, persist_feed_data
from app.services.gtfs.parser import parse_gtfs_tables

logger = logging.getLogger(__name__)


class GTFSIngestionService:
    """Orchestrates static GTFS feed download, validation, and persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest_archive(
        self,
        feed_id: int,
        archive_source: bytes | Path | str,
        *,
        batch_size: int = 1000,
    ) -> IngestionStats:
        """Process and persist a GTFS ZIP archive (bytes or file path) for a feed.

        Execution is atomic: any failure during extraction, validation, or persistence
        triggers a complete session rollback, leaving any prior feed data untouched.

        Args:
            feed_id: Database ID of the TransitFeed.
            archive_source: Archive bytes or path to the zip file.
            batch_size: Database insertion batch size.

        Returns:
            IngestionStats: Ingestion metrics on success.

        Raises:
            GTFSIngestionError: If security, validation, or database persistence fails.
        """
        try:
            # 1. Inspect and extract GTFS tables safely in-memory
            logger.info("Extracting GTFS archive tables for feed ID %d", feed_id)
            tables = extract_gtfs_tables(archive_source)

            # 2. Parse and validate GTFS Schedule compliance and relational integrity
            logger.info("Validating and parsing GTFS tables for feed ID %d", feed_id)
            parsed_data = parse_gtfs_tables(tables)

            # 3. Persist into the database inside this transaction
            stats = await persist_feed_data(
                self.session, feed_id, parsed_data, batch_size=batch_size
            )

            # 4. Commit transaction
            await self.session.commit()
            logger.info(
                "Static GTFS import committed successfully for feed ID %d", feed_id
            )
            return stats
        except Exception as exc:
            await self.session.rollback()
            logger.error(
                "Rolled back static GTFS import for feed ID %d due to error: %s",
                feed_id,
                exc,
            )
            if isinstance(exc, GTFSIngestionError):
                raise
            raise GTFSPersistenceError(
                f"Unexpected error during GTFS import: {exc}"
            ) from exc

    async def ingest_remote_feed(
        self,
        feed_id: int,
        *,
        batch_size: int = 1000,
    ) -> IngestionStats:
        """Download configured static feed archive and import atomically.

        Args:
            feed_id: Database ID of the TransitFeed.
            batch_size: Batch size for database persistence.

        Returns:
            IngestionStats: Ingestion metrics on success.

        Raises:
            GTFSIngestionError: If download, validation, or persistence fails.
        """
        stmt = select(TransitFeed).where(TransitFeed.id == feed_id)
        result = await self.session.execute(stmt)
        feed = result.scalar_one_or_none()
        if not feed:
            raise GTFSPersistenceError(f"Transit feed with ID {feed_id} does not exist")

        api_key: str | None = None
        if feed.api_key_env_var:
            api_key = os.getenv(feed.api_key_env_var)
            if not api_key:
                logger.warning(
                    "Feed ID %d specifies api_key_env_var %r, but not set in env",
                    feed_id,
                    feed.api_key_env_var,
                )

        try:
            zip_bytes = await download_gtfs_feed(
                feed.static_gtfs_url,
                api_key=api_key,
            )
        except GTFSDownloadError:
            raise
        except Exception as exc:
            raise GTFSDownloadError(f"Failed to download GTFS feed: {exc}") from exc

        return await self.ingest_archive(feed_id, zip_bytes, batch_size=batch_size)
