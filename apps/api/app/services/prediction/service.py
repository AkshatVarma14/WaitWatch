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
from app.models.trip_update import TripUpdate
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

        # 4. Fetch live vehicle positions and trip updates for this feed
        vp_stmt = select(VehiclePosition).where(
            VehiclePosition.feed_id == feed.id,
            VehiclePosition.trip_id.isnot(None),
            VehiclePosition.current_stop_sequence.isnot(None),
        )
        all_vps = (await session.execute(vp_stmt)).scalars().all()

        tu_stmt = select(TripUpdate).where(TripUpdate.feed_id == feed.id)
        all_tus = (await session.execute(tu_stmt)).scalars().all()

        # 5. Filter fresh vehicle snapshots and trip updates
        fresh_vps: list[tuple[VehiclePosition, datetime]] = []
        vps_by_trip: dict[str, tuple[VehiclePosition, datetime]] = {}
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
            if vp.trip_id:
                existing_vp = vps_by_trip.get(vp.trip_id)
                if existing_vp is None or obs_time > existing_vp[1]:
                    vps_by_trip[vp.trip_id] = (vp, obs_time)

        fresh_tus: list[TripUpdate] = []
        trip_updates_by_trip: dict[str, list[TripUpdate]] = {}
        canceled_trip_ids: set[str] = set()
        for tu in all_tus:
            raw_ts = tu.update_timestamp or tu.feed_timestamp or tu.recorded_at
            if raw_ts is None:
                continue
            obs_time = to_utc(raw_ts)
            if obs_time is None:
                continue
            age_seconds = (now_utc - obs_time).total_seconds()
            if age_seconds < -60.0 or age_seconds > self.max_realtime_age_seconds:
                continue
            fresh_tus.append(tu)
            trip_updates_by_trip.setdefault(tu.trip_id, []).append(tu)
            if tu.schedule_relationship == 3:  # CANCELED
                canceled_trip_ids.add(tu.trip_id)

        if not fresh_vps and not fresh_tus:
            return []

        # 6. Eagerly load matching static trips with routes and stop times
        candidate_trip_ids = list(
            (set(vps_by_trip.keys()) | set(trip_updates_by_trip.keys()))
            - canceled_trip_ids
        )
        if not candidate_trip_ids:
            return []

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

        # 7. Evaluate arrival prediction for each candidate trip
        predictions_by_trip: dict[str, StopArrivalPrediction] = {}
        for trip_id, trip in trips_by_id.items():
            vp_entry = vps_by_trip.get(trip_id)
            vp = vp_entry[0] if vp_entry else None
            vp_obs_time = vp_entry[1] if vp_entry else None
            tus_for_trip = trip_updates_by_trip.get(trip_id, [])

            # Determine service date and active service
            # Check start_date from VP or TripUpdate
            start_date_str: str | None = None
            if vp and vp.start_date:
                start_date_str = vp.start_date
            elif tus_for_trip and tus_for_trip[0].start_date:
                start_date_str = tus_for_trip[0].start_date

            service_date: date | None = None
            if start_date_str:
                try:
                    trip_date = datetime.strptime(start_date_str, "%Y%m%d").date()
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

            # Check if there is a matching TripUpdate for target stop
            matching_tu: TripUpdate | None = None
            for tu in tus_for_trip:
                if (tu.stop_id and tu.stop_id == target_stop.stop_id) or (
                    tu.stop_sequence is not None and tu.stop_sequence == target_seq
                ):
                    matching_tu = tu
                    break

            pred: StopArrivalPrediction | None = None

            if matching_tu is not None:
                # Check for skipped stop
                if matching_tu.stop_schedule_relationship == 1:  # SKIPPED
                    continue

                # Precedence: arrival_time > arrival_delay > departure_time
                # > departure_delay > trip_delay
                if matching_tu.arrival_time is not None:
                    est_arr = to_utc(matching_tu.arrival_time)
                    if est_arr is None:
                        continue
                    delay_sec = int((est_arr - scheduled_arrival_utc).total_seconds())
                elif matching_tu.arrival_delay is not None:
                    delay_sec = matching_tu.arrival_delay
                    est_arr = scheduled_arrival_utc + timedelta(seconds=delay_sec)
                elif matching_tu.departure_time is not None:
                    est_arr = to_utc(matching_tu.departure_time)
                    if est_arr is None:
                        continue
                    delay_sec = int((est_arr - scheduled_arrival_utc).total_seconds())
                elif matching_tu.departure_delay is not None:
                    delay_sec = matching_tu.departure_delay
                    est_arr = scheduled_arrival_utc + timedelta(seconds=delay_sec)
                elif matching_tu.trip_delay is not None:
                    delay_sec = matching_tu.trip_delay
                    est_arr = scheduled_arrival_utc + timedelta(seconds=delay_sec)
                else:
                    est_arr = scheduled_arrival_utc
                    delay_sec = 0

                tu_obs_raw = (
                    matching_tu.update_timestamp
                    or matching_tu.feed_timestamp
                    or matching_tu.recorded_at
                )
                tu_obs_time = to_utc(tu_obs_raw)
                vehicle_id = matching_tu.vehicle_id or (vp.vehicle_id if vp else None)

                pred = StopArrivalPrediction(
                    feed_slug=feed.slug,
                    feed_id=feed.id,
                    stop_id=target_stop.stop_id,
                    trip_id=trip.trip_id,
                    route_id=trip.route.route_id,
                    route_short_name=trip.route.short_name,
                    trip_headsign=trip.trip_headsign,
                    vehicle_id=vehicle_id,
                    stop_sequence=target_st.stop_sequence,
                    scheduled_arrival_time=scheduled_arrival_utc,
                    estimated_arrival_time=est_arr,
                    delay_seconds=delay_sec,
                    prediction_source="TRIP_UPDATE",
                    source_observation_time=tu_obs_time,
                )

            elif vp is not None and vp_obs_time is not None:
                # Fall back to live vehicle position and historical delay adjustment
                curr_seq = vp.current_stop_sequence
                if curr_seq is None or curr_seq > target_seq:
                    # Target stop is not downstream of vehicle position
                    continue

                # Query historical observations for same trip / vehicle
                since_history = now_utc - timedelta(
                    minutes=self.history_lookback_minutes
                )
                obs_conditions = [VehicleObservation.trip_id == trip.trip_id]
                if vp.vehicle_id:
                    obs_conditions.append(
                        VehicleObservation.vehicle_id == vp.vehicle_id
                    )

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
                    source_observation_time=vp_obs_time,
                )

            if pred is not None:
                # Deduplicate by trip_id, keeping TRIP_UPDATE or latest telemetry
                existing = predictions_by_trip.get(trip.trip_id)
                if (
                    existing is None
                    or pred.prediction_source == "TRIP_UPDATE"
                    or (
                        (pred.source_observation_time or now_utc)
                        > (existing.source_observation_time or now_utc)
                    )
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
