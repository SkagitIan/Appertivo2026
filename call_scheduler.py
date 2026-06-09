import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app

from models import CallSchedule, Restaurant, db
from vapi_client import trigger_julie_call


logger = logging.getLogger(__name__)
_DEFAULT_TZ = "America/Los_Angeles"


def _local_now(tz_name):
    tz = ZoneInfo(tz_name or _DEFAULT_TZ)
    return datetime.now(timezone.utc).astimezone(tz)


def check_and_fire_calls():
    """Fire Vapi calls for schedules due in the current 5-minute polling window.

    Returns a dict with counts: fired, skipped, errors.
    """
    now_utc = datetime.now(timezone.utc)

    schedules = (
        CallSchedule.query
        .filter_by(is_active=True)
        .join(Restaurant)
        .filter(Restaurant.catalog_status == "included")
        .all()
    )

    fired = skipped = errors = 0

    for schedule in schedules:
        restaurant = schedule.restaurant
        tz_name = (restaurant.timezone or "").strip() or _DEFAULT_TZ
        try:
            now_local = now_utc.astimezone(ZoneInfo(tz_name))
        except Exception:
            now_local = now_utc.astimezone(ZoneInfo(_DEFAULT_TZ))

        # Wrong day of week (Monday=0, Sunday=6)
        if now_local.weekday() != schedule.day_of_week:
            continue

        # Outside the 5-minute firing window starting at call_time
        window_start = now_local.replace(
            hour=schedule.call_time.hour,
            minute=schedule.call_time.minute,
            second=0, microsecond=0,
        )
        if not (window_start <= now_local < window_start + timedelta(minutes=5)):
            continue

        # Already fired today (compare dates in restaurant's local timezone)
        if schedule.last_called_at:
            last_local = schedule.last_called_at.replace(tzinfo=timezone.utc).astimezone(now_local.tzinfo)
            if last_local.date() == now_local.date():
                skipped += 1
                continue

        result = trigger_julie_call(restaurant)
        if result["success"]:
            schedule.last_called_at = now_utc.replace(tzinfo=None)
            db.session.commit()
            fired += 1
            logger.info(
                "Fired call for %s (id=%s), call_id=%s",
                restaurant.name, restaurant.id, result["call_id"],
            )
        else:
            errors += 1
            logger.error(
                "Call failed for %s (id=%s): %s",
                restaurant.name, restaurant.id, result["error"],
            )

    return {"fired": fired, "skipped": skipped, "errors": errors}
