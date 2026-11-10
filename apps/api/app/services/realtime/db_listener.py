"""WaitWatch API — PostgreSQL LISTEN/NOTIFY database listener."""

import asyncio
import logging
from typing import TYPE_CHECKING

import asyncpg

from app.core.config import settings
from app.services.realtime.events import CHANNEL_NAME

if TYPE_CHECKING:
    from app.services.realtime.websocket_manager import ConnectionManager

logger = logging.getLogger(__name__)


async def run_db_listener(
    manager: "ConnectionManager", stop_event: asyncio.Event
) -> None:
    """Managed background task that listens for PostgreSQL feed update notifications.

    Runs a single dedicated asyncpg connection with automatic reconnection.
    Fails gracefully without interrupting the REST API if PostgreSQL is unavailable.
    Cleanly exits and cleans up resources when `stop_event` is set.
    """
    url = settings.database_url
    if not (url.startswith("postgresql://") or url.startswith("postgresql+asyncpg://")):
        logger.info(
            "Non-PostgreSQL database dialect in use (%s); "
            "PostgreSQL LISTEN/NOTIFY listener disabled.",
            settings.sanitized_database_url,
        )
        return

    # Normalize driver prefix for asyncpg direct connection
    clean_url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    reconnect_delay = 1.0

    while not stop_event.is_set():
        conn: asyncpg.Connection | None = None
        try:
            logger.info(
                "Connecting PostgreSQL LISTEN subscriber on channel '%s' (%s)",
                CHANNEL_NAME,
                settings.sanitized_database_url,
            )
            conn = await asyncpg.connect(clean_url, timeout=5.0)
            reconnect_delay = 1.0

            def _on_notification(
                connection: asyncpg.Connection,
                pid: int,
                channel: str,
                payload: str,
            ) -> None:
                # Dispatch notification handling as an async task
                asyncio.create_task(manager.handle_db_notification(payload))

            await conn.add_listener(CHANNEL_NAME, _on_notification)
            logger.info(
                "PostgreSQL LISTEN active on channel '%s'",
                CHANNEL_NAME,
            )

            # Keep connection alive with periodic check until stop_event or disconnect
            while not stop_event.is_set():
                await asyncio.sleep(10.0)
                if not stop_event.is_set():
                    # Heartbeat query to detect silent network drops
                    await conn.execute("SELECT 1")

        except asyncio.CancelledError:
            break
        except Exception as exc:
            if not stop_event.is_set():
                logger.warning(
                    "PostgreSQL notification listener disconnected (%s: %s). "
                    "Reconnecting in %.1fs...",
                    type(exc).__name__,
                    exc,
                    reconnect_delay,
                )
                try:
                    await asyncio.sleep(reconnect_delay)
                except asyncio.CancelledError:
                    break
                reconnect_delay = min(reconnect_delay * 2, 30.0)
        finally:
            if conn is not None:
                try:
                    await conn.close(timeout=2.0)
                except Exception:
                    pass

    logger.info("PostgreSQL notification listener stopped.")
