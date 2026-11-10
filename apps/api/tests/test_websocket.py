"""Tests for feed-scoped WebSocket endpoints and live update notification pub/sub."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database.session import Base, get_session
from app.main import app
from app.models.feed import TransitFeed
from app.services.realtime.db_listener import run_db_listener
from app.services.realtime.events import (
    FeedUpdateEvent,
    clear_pending_feed_events,
    dispatch_pending_feed_events,
    publish_feed_update,
)
from app.services.realtime.websocket_manager import ConnectionManager, ws_manager


@pytest.fixture
async def ws_test_db():
    """Create an isolated in-memory async SQLite engine with test transit feeds."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_maker() as session:
        feed1 = TransitFeed(
            city_name="Metro City",
            slug="metro-city",
            static_gtfs_url="https://example.com/metro.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        feed2 = TransitFeed(
            city_name="Uptown",
            slug="uptown-bus",
            static_gtfs_url="https://example.com/uptown.zip",
            feed_status="active",
            is_live_tracking_enabled=True,
        )
        session.add_all([feed1, feed2])
        await session.commit()

    async def override_get_session():
        async with session_maker() as s:
            try:
                yield s
            except Exception:
                await s.rollback()
                raise
            finally:
                await s.close()

    app.dependency_overrides[get_session] = override_get_session
    yield session_maker
    app.dependency_overrides.pop(get_session, None)
    await ws_manager.close_all()
    await engine.dispose()


def test_websocket_unknown_feed_rejected(ws_test_db):
    """Test that connecting to a non-existent feed slug is safely rejected."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/feeds/non-existent-feed/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "error"
        assert "not found" in data["message"].lower()


def test_websocket_valid_feed_connected_and_ping(ws_test_db):
    """Test connecting to a valid feed receives connected message and pong on ping."""
    client = TestClient(app)
    with client.websocket_connect("/api/v1/feeds/metro-city/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connected"
        assert data["feed_slug"] == "metro-city"
        assert "feed_id" in data
        assert "timestamp" in data

        # Test heartbeat
        websocket.send_text("ping")
        resp = websocket.receive_text()
        assert resp == "pong"


@pytest.mark.asyncio
async def test_websocket_feed_isolation_and_fanout():
    """Test that WebSocket clients receive broadcasts only for their subscribed feed."""
    manager = ConnectionManager(max_connections_per_feed=5)

    class MockWebSocket:
        def __init__(self, name: str):
            self.name = name
            from starlette.websockets import WebSocketState

            self.client_state = WebSocketState.CONNECTED
            self.sent_messages: list[dict] = []
            self.closed = False
            self.close_code = None

        async def send_json(self, data: dict):
            self.sent_messages.append(data)

        async def close(self, code: int = 1000, reason: str = ""):
            from starlette.websockets import WebSocketState

            self.closed = True
            self.close_code = code
            self.client_state = WebSocketState.DISCONNECTED

    ws_metro1 = MockWebSocket("metro1")
    ws_metro2 = MockWebSocket("metro2")
    ws_uptown = MockWebSocket("uptown")

    assert await manager.connect("metro-city", ws_metro1) is True
    assert await manager.connect("metro-city", ws_metro2) is True
    assert await manager.connect("uptown-bus", ws_uptown) is True

    assert manager.active_connection_count("metro-city") == 2
    assert manager.active_connection_count("uptown-bus") == 1
    assert manager.active_connection_count() == 3

    # Broadcast update to metro-city
    event = FeedUpdateEvent(
        feed_id=1,
        feed_slug="metro-city",
        update_type="vehicles",
        timestamp=datetime.now(UTC).isoformat(),
        vehicle_count=12,
    )
    delivered = await manager.broadcast_to_feed("metro-city", event.model_dump())
    assert delivered == 2

    assert len(ws_metro1.sent_messages) == 1
    assert ws_metro1.sent_messages[0]["feed_slug"] == "metro-city"
    assert ws_metro1.sent_messages[0]["vehicle_count"] == 12

    assert len(ws_metro2.sent_messages) == 1
    assert ws_metro2.sent_messages[0]["feed_slug"] == "metro-city"

    # ws_uptown must have received 0 messages
    assert len(ws_uptown.sent_messages) == 0

    # Test disconnection
    await manager.disconnect("metro-city", ws_metro1)
    assert manager.active_connection_count("metro-city") == 1
    assert manager.active_connection_count() == 2

    # Test close_all
    await manager.close_all()
    assert ws_metro2.closed is True
    assert ws_uptown.closed is True
    assert manager.active_connection_count() == 0


@pytest.mark.asyncio
async def test_websocket_capacity_limit():
    """Verify that connection limits per feed are enforced."""
    manager = ConnectionManager(max_connections_per_feed=2)

    class MockWebSocket:
        def __init__(self):
            from starlette.websockets import WebSocketState

            self.client_state = WebSocketState.CONNECTED

    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    assert await manager.connect("metro-city", ws1) is True
    assert await manager.connect("metro-city", ws2) is True
    # Third connection should exceed limit
    assert await manager.connect("metro-city", ws3) is False
    assert manager.active_connection_count("metro-city") == 2


@pytest.mark.asyncio
async def test_failed_ingestion_publishes_no_events(ws_test_db):
    """Ensure that on database failure, zero notifications are dispatched."""
    session_maker = ws_test_db
    custom_manager = ConnectionManager()

    async with session_maker() as session:
        event = FeedUpdateEvent(
            feed_id=1,
            feed_slug="metro-city",
            update_type="vehicles",
            timestamp=datetime.now(UTC).isoformat(),
            vehicle_count=5,
        )
        await publish_feed_update(session, event)
        assert len(session.info.get("_pending_feed_events", [])) == 1

        # Simulate transaction failure & rollback
        clear_pending_feed_events(session)
        await session.rollback()

        # Staged events should now be empty
        dispatched = await dispatch_pending_feed_events(session, custom_manager)
        assert dispatched == []
        assert custom_manager.active_connection_count() == 0


@pytest.mark.asyncio
async def test_successful_ingestion_publishes_event(ws_test_db):
    """Ensure successful commit stages and dispatches feed update event."""
    session_maker = ws_test_db
    custom_manager = ConnectionManager()

    async with session_maker() as session:
        event = FeedUpdateEvent(
            feed_id=1,
            feed_slug="metro-city",
            update_type="vehicles",
            timestamp=datetime.now(UTC).isoformat(),
            vehicle_count=15,
        )
        await publish_feed_update(session, event)
        await session.commit()

        dispatched = await dispatch_pending_feed_events(session, custom_manager)
        assert len(dispatched) == 1
        assert dispatched[0].feed_slug == "metro-city"
        assert dispatched[0].vehicle_count == 15


@pytest.mark.asyncio
async def test_websocket_manager_handle_malformed_payload():
    """Verify that malformed or non-JSON payloads are handled without raising."""
    manager = ConnectionManager()
    # Invalid JSON
    await manager.handle_db_notification("invalid {json")
    # Valid JSON but missing required fields
    await manager.handle_db_notification('{"random": "payload"}')
    # Valid structure
    valid_event = FeedUpdateEvent(
        feed_id=1,
        feed_slug="test-feed",
        update_type="trip_updates",
        timestamp=datetime.now(UTC).isoformat(),
        trip_update_count=8,
    )
    await manager.handle_db_notification(valid_event.model_dump_json())


@pytest.mark.asyncio
async def test_db_listener_non_postgres_skips_cleanly(monkeypatch):
    """Verify that run_db_listener exits cleanly when database is not PostgreSQL."""
    monkeypatch.setattr(
        "app.services.realtime.db_listener.settings.database_url",
        "sqlite+aiosqlite:///:memory:",
    )
    manager = ConnectionManager()
    stop_event = asyncio.Event()
    # On SQLite, should return cleanly immediately without connecting
    await run_db_listener(manager, stop_event)


@pytest.mark.asyncio
async def test_db_listener_stop_event_cancels_cleanly(monkeypatch):
    """Verify that run_db_listener cleanly terminates when stop_event is set."""
    monkeypatch.setattr(
        "app.services.realtime.db_listener.settings.database_url",
        "postgresql+asyncpg://user:pass@localhost:5432/db",
    )
    manager = ConnectionManager()
    stop_event = asyncio.Event()
    stop_event.set()  # Already set before run

    await run_db_listener(manager, stop_event)
