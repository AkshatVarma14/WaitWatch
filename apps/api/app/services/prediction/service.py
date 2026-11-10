"""Arrival time prediction service using GTFS schedules, live snapshots, and history.

Mathematical Formulation & Limits:
1. Scheduled Arrival:
   T_sched = service_midnight + timedelta(seconds=parse_gtfs_time_to_seconds(time))
2. Telemetry Freshness:
   Effective vehicle timestamp: T_obs = vehicle_ts or feed_ts or recorded_at.
   T_obs must satisfy: -60s <= (reference_time - T_obs) <= max_realtime_age_seconds.
3. Downstream Eligibility:
   Vehicle is eligible for target stop if:
   - Trip service_id is active on service date (calendar + calendar_dates).
   - Target stop sequence >= vehicle.current_stop_sequence.
   - Vehicles missing trip_id or current_stop_sequence are skipped.
4. Historical Delay Adjustment:
   For prior stops on this trip with STOPPED_AT observations at scheduled stops:
     delta_t_i = obs.observed_at - T_sched(stop_i)
   When sample count >= MIN_SAMPLE_THRESHOLD (default 1):
     median_delay = int(median({delta_t_i}))
     T_est = T_sched + timedelta(seconds=median_delay)
     delay_seconds = median_delay
     prediction_source = "HISTORY_ADJUSTED"
   Otherwise:
     T_est = T_sched
     delay_seconds = 0
     prediction_source = "SCHEDULE_ONLY"
5. Limits:
   Assumes uniform delay propagation without traffic signal, segment-level speed,
   or shape geometry modeling. No delay is invented when samples are absent.
"""

import logging
import statistics
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agency import Agency
from app.models.calendar import Calendar, CalendarDate
from app.models.feed import TransitFeed
from app.models.stop import Stop
from app.models.stop_time import StopTime
from app.models.trip import Trip
from app.models.vehicle_observation import VehicleObservation
from app.models.vehicle_position import VehiclePosition
from app.schemas.transit import StopArrivalPrediction

logger = logging.getLogger(__name__)

DEFAULT_MAX_REALTIME_AGE_SECONDS = 300  # 5 minutes per GTFS-RT guidance
DEFAULT_HISTORY_LOOKBACK_MINUTES = 60  # 1 hour lookback for same-trip history
MIN_SAMPLE_THRESHOLD = 1  # Minimum historical STOPPED_AT samples for delay adjustment


def to_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to UTC for consistent cross-database assertions."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def parse_gtfs_time_to_seconds(time_str: str) -> int:
    """Parse GTFS HH:MM:SS format to total seconds from start of service day.

    Supports extended GTFS service day hours (e.g. 25:30:00 for 1:30 AM next day).
    """
    parts = time_str.strip().split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid GTFS time format: '{time_str}'")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2]) if len(parts) > 2 else 0
    return hours * 3600 + minutes * 60 + seconds


def resolve_feed_timezone(agency_tz_str: str | None, stop_tz_str: str | None) -> tzinfo:
    """Resolve agency/stop timezone safely with UTC fallback."""
    for tz_candidate in (stop_tz_str, agency_tz_str):
        if not tz_candidate:
            continue
        cleaned = tz_candidate.strip()
        if cleaned.upper() in ("UTC", "GMT", "ETC/UTC"):
            return UTC
        try:
            return ZoneInfo(cleaned)
        except (ZoneInfoNotFoundError, ValueError, Exception):
            continue
    return UTC


async def get_active_service_ids(
    session: AsyncSession,
    feed_id: int,
    target_date: date,
) -> set[str]:
    """Determine all active service_ids for a feed on a target calendar date.

    Follows GTFS specification:
    1. Exceptions in calendar_dates take precedence:
       - exception_type 1: service added
       - exception_type 2: service removed
    2. For services not in calendar_dates:
       - check weekly schedule in calendars (start_date <= target_date <= end_date)
         and matching day of week.
    """
    # 1. Fetch calendar_dates exceptions for target_date
    cd_stmt = select(CalendarDate.service_id, CalendarDate.exception_type).where(
        CalendarDate.feed_id == feed_id,
        CalendarDate.date == target_date,
    )
    cd_rows = (await session.execute(cd_stmt)).all()
    added_services = {row[0] for row in cd_rows if row[1] == 1}
    removed_services = {row[0] for row in cd_rows if row[1] == 2}

    # 2. Day of week column mapping
    weekday_cols = [
        Calendar.monday,
        Calendar.tuesday,
        Calendar.wednesday,
        Calendar.thursday,
        Calendar.friday,
        Calendar.saturday,
        Calendar.sunday,
    ]
    target_day_col = weekday_cols[target_date.weekday()]

    cal_stmt = select(Calendar.service_id).where(
        Calendar.feed_id == feed_id,
        Calendar.start_date <= target_date,
        Calendar.end_date >= target_date,
        target_day_col.is_(True),
    )
    cal_rows = (await session.execute(cal_stmt)).all()
    base_services = {row[0] for row in cal_rows}

    return (base_services - removed_services) | added_services


class ArrivalPredictionService:
    """Predicts arrival times at stops using live vehicle telemetry and GTFS."""

    def __init__(
        self,
        max_realtime_age_seconds: int = DEFAULT_MAX_REALTIME_AGE_SECONDS,
        history_lookback_minutes: int = DEFAULT_HISTORY_LOOKBACK_MINUTES,
        min_sample_threshold: int = MIN_SAMPLE_THRESHOLD,
    ) -> None:
        self.max_realtime_age_seconds = max_realtime_age_seconds
        self.history_lookback_minutes = history_lookback_minutes
        self.min_sample_threshold = min_sample_threshold

    async def predict_arrivals_for_stop(
        self,
        session: AsyncSession,
        feed: TransitFeed,
        stop_id: str,
        limit: int = 10,
        reference_time: datetime | None = None,
    ) -> list[StopArrivalPrediction]:
        """Predict upcoming vehicle arrivals for a target stop in a feed."""
        # 1. Target stop lookup
        target_stop_stmt = select(Stop).where(
            Stop.feed_id == feed.id,
            Stop.stop_id == stop_id,
        )
        target_stop = (await session.execute(target_stop_stmt)).scalar_one_or_none()
        if not target_stop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stop '{stop_id}' not found in feed '{feed.slug}'",
            )

        # 2. Timezone resolution
        agency_stmt = select(Agency.timezone).where(Agency.feed_id == feed.id).limit(1)
        agency_tz_str = (await session.execute(agency_stmt)).scalar_one_or_none()
        agency_tz = resolve_feed_timezone(agency_tz_str, target_stop.timezone)

        # 3. Reference evaluation time
        now_utc = to_utc(reference_time) if reference_time else datetime.now(UTC)
        if now_utc is None:
            now_utc = datetime.now(UTC)
        local_now = now_utc.astimezone(agency_tz)
        current_date = local_now.date()

        candidate_dates = [current_date]
        if local_now.hour < 6:
            candidate_dates.append(current_date - timedelta(days=1))

        active_services_by_date: dict[date, set[str]] = {}
        for d in candidate_dates:
            active_services_by_date[d] = await get_active_service_ids(
                session, feed.id, d
            )

        # 4. Fetch live vehicle positions for this feed
        vp_stmt = select(VehiclePosition).where(
            VehiclePosition.feed_id == feed.id,
            VehiclePosition.trip_id.isnot(None),
            VehiclePosition.current_stop_sequence.isnot(None),
        )
        all_vps = (await session.execute(vp_stmt)).scalars().all()

        # 5. Filter fresh vehicle snapshots
        fresh_vps: list[tuple[VehiclePosition, datetime]] = []
        for vp in all_vps:
            raw_ts = vp.vehicle_timestamp or vp.feed_timestamp or vp.recorded_at
            if raw_ts is None:
                continue
            obs_time = to_utc(raw_ts)
            if obs_time is None:
                continue
            age_seconds = (now_utc - obs_time).total_seconds()
            if age_seconds < -60.0 or age_seconds > self.max_realtime_age_seconds:
                # Stale telemetry or clock skewed into future beyond tolerance
                continue
            fresh_vps.append((vp, obs_time))

        if not fresh_vps:
            return []

        # 6. Eagerly load matching static trips with routes and stop times
        candidate_trip_ids = list({vp.trip_id for vp, _ in fresh_vps if vp.trip_id})
        trip_stmt = (
            select(Trip)
            .options(
                selectinload(Trip.route),
                selectinload(Trip.stop_times).selectinload(StopTime.stop),
            )
            .where(
                Trip.feed_id == feed.id,
                Trip.trip_id.in_(candidate_trip_ids),
            )
        )
        trips = (await session.execute(trip_stmt)).scalars().all()
        trips_by_id = {t.trip_id: t for t in trips}

        # 7. Evaluate arrival prediction for each live vehicle
        predictions_by_trip: dict[str, StopArrivalPrediction] = {}
        for vp, obs_time in fresh_vps:
            if not vp.trip_id:
                continue
            trip = trips_by_id.get(vp.trip_id)
            if not trip:
                continue

            # Determine service date and active service
            service_date: date | None = None
            if vp.start_date:
                try:
                    trip_date = datetime.strptime(vp.start_date, "%Y%m%d").date()
                except ValueError:
                    trip_date = None

                if trip_date:
                    if trip_date not in active_services_by_date:
                        active_services_by_date[
                            trip_date
                        ] = await get_active_service_ids(session, feed.id, trip_date)
                    if trip.service_id in active_services_by_date[trip_date]:
                        service_date = trip_date

            if service_date is None:
                # Fallback to candidate dates
                active_date = next(
                    (
                        d
                        for d in candidate_dates
                        if trip.service_id in active_services_by_date.get(d, set())
                    ),
                    None,
                )
                if active_date:
                    service_date = active_date

            if service_date is None:
                # Inactive service for this trip
                continue

            # Find target stop in trip's stop_times
            target_st = next(
                (st for st in trip.stop_times if st.stop_id == target_stop.id),
                None,
            )
            if not target_st:
                # Target stop is not on this trip
                continue

            target_seq = target_st.stop_sequence
            curr_seq = vp.current_stop_sequence
            if curr_seq is None or curr_seq > target_seq:
                # Target stop is not downstream of vehicle position
                continue

            # Compute scheduled arrival time
            try:
                arr_seconds = parse_gtfs_time_to_seconds(target_st.arrival_time)
            except ValueError:
                continue

            service_midnight = datetime(
                service_date.year,
                service_date.month,
                service_date.day,
                0,
                0,
                0,
                tzinfo=agency_tz,
            )
            sched_local = service_midnight + timedelta(seconds=arr_seconds)
            scheduled_arrival_utc = sched_local.astimezone(UTC)

            # Query historical observations for same trip / vehicle
            since_history = now_utc - timedelta(minutes=self.history_lookback_minutes)
            obs_conditions = [VehicleObservation.trip_id == trip.trip_id]
            if vp.vehicle_id:
                obs_conditions.append(VehicleObservation.vehicle_id == vp.vehicle_id)

            hist_stmt = (
                select(VehicleObservation)
                .where(
                    VehicleObservation.feed_id == feed.id,
                    VehicleObservation.observed_at >= since_history,
                    or_(*obs_conditions),
                )
                .order_by(VehicleObservation.observed_at.desc())
                .limit(100)
            )
            hist_rows = (await session.execute(hist_stmt)).scalars().all()

            # Map earlier scheduled stops on this trip
            earlier_stops_by_id: dict[str, str] = {}
            earlier_stops_by_seq: dict[int, str] = {}
            for st in trip.stop_times:
                if st.stop_sequence < target_seq:
                    if st.stop:
                        earlier_stops_by_id[st.stop.stop_id] = st.arrival_time
                    earlier_stops_by_seq[st.stop_sequence] = st.arrival_time

            # Calculate delays from STOPPED_AT observations at known scheduled stops
            delays_by_stop: dict[str, int] = {}
            for h in hist_rows:
                if h.current_status != 1:  # Only STOPPED_AT
                    continue
                h_time = to_utc(h.observed_at)
                if h_time is None:
                    continue

                matched_arr_str = None
                matched_key = None
                if h.stop_id and h.stop_id in earlier_stops_by_id:
                    matched_arr_str = earlier_stops_by_id[h.stop_id]
                    matched_key = h.stop_id
                elif (
                    h.current_stop_sequence
                    and h.current_stop_sequence in earlier_stops_by_seq
                ):
                    matched_arr_str = earlier_stops_by_seq[h.current_stop_sequence]
                    matched_key = f"seq_{h.current_stop_sequence}"

                if (
                    matched_arr_str
                    and matched_key
                    and matched_key not in delays_by_stop
                ):
                    try:
                        s_secs = parse_gtfs_time_to_seconds(matched_arr_str)
                    except ValueError:
                        continue
                    s_local = service_midnight + timedelta(seconds=s_secs)
                    s_utc = s_local.astimezone(UTC)
                    delay_sec = int((h_time - s_utc).total_seconds())
                    delays_by_stop[matched_key] = delay_sec

            delays = list(delays_by_stop.values())
            if len(delays) >= self.min_sample_threshold:
                median_delay = int(statistics.median(delays))
                delay_seconds = median_delay
                estimated_arrival_utc = scheduled_arrival_utc + timedelta(
                    seconds=median_delay
                )
                prediction_source = "HISTORY_ADJUSTED"
            else:
                delay_seconds = 0
                estimated_arrival_utc = scheduled_arrival_utc
                prediction_source = "SCHEDULE_ONLY"

            pred = StopArrivalPrediction(
                feed_slug=feed.slug,
                feed_id=feed.id,
                stop_id=target_stop.stop_id,
                trip_id=trip.trip_id,
                route_id=trip.route.route_id,
                route_short_name=trip.route.short_name,
                trip_headsign=trip.trip_headsign,
                vehicle_id=vp.vehicle_id,
                stop_sequence=target_st.stop_sequence,
                scheduled_arrival_time=scheduled_arrival_utc,
                estimated_arrival_time=estimated_arrival_utc,
                delay_seconds=delay_seconds,
                prediction_source=prediction_source,
                source_observation_time=obs_time,
            )

            # Deduplicate by trip_id, keeping the latest telemetry
            existing = predictions_by_trip.get(trip.trip_id)
            if existing is None or (
                obs_time > (existing.source_observation_time or obs_time)
            ):
                predictions_by_trip[trip.trip_id] = pred

        predictions = list(predictions_by_trip.values())
        predictions.sort(
            key=lambda p: (
                p.estimated_arrival_time,
                p.trip_id,
                p.vehicle_id or "",
            )
        )
        return predictions[:limit]
