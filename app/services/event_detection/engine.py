import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta

from app.models.reading import WeatherReading
from app.models.event import WeatherEvent
from app.services.event_detection.schemas import EventCandidate
from app.services.event_detection.cooldown import is_on_cooldown
from app.services.event_detection.detectors import (
    detect_rapid_temperature_drop,
    detect_freeze_thaw_risk,
    detect_wind_escalation,
    detect_cross_city_temperature_spread,
)

logger = logging.getLogger(__name__)

RECENT_READINGS_HOURS = 6


# Helpers 

def _get_recent_readings(
    db: Session,
    city: str,
    reference_time: datetime,
    hours: int = RECENT_READINGS_HOURS,
) -> list[WeatherReading]:
    """Fetch recent readings for a city, oldest first, excluding current"""
    cutoff = reference_time - timedelta(hours=hours)
    return (
        db.query(WeatherReading)
        .filter(
            WeatherReading.city == city,
            WeatherReading.observed_at >= cutoff,
            WeatherReading.observed_at < reference_time,
        )
        .order_by(WeatherReading.observed_at.asc())
        .all()
    )


def _get_latest_reading_per_city(
    db: Session,
) -> dict[str, WeatherReading]:
    """Return the single most recent reading for each city"""
    cities = ["Ottawa", "Toronto", "Vancouver"]
    result = {}
    for city in cities:
        reading = (
            db.query(WeatherReading)
            .filter(WeatherReading.city == city)
            .order_by(WeatherReading.observed_at.desc())
            .first()
        )
        if reading:
            result[city] = reading
    return result


# Persistence 

def persist_candidates(
    db: Session,
    candidates: list[EventCandidate],
) -> list[WeatherEvent]:
    """
    Filter candidates through cooldown check
    Store valid ones to DB and return saved events
    """
    saved = []

    try:
        for candidate in candidates:
            if is_on_cooldown(db, candidate.city, candidate.event_type, candidate.observed_at):
                logger.debug(
                    "Cooldown active — skipping %s for %s",
                    candidate.event_type,
                    candidate.city,
                )
                continue

            event = WeatherEvent(
                city=candidate.city,
                event_type=candidate.event_type,
                severity=candidate.severity,
                title=candidate.title,
                description=candidate.description,
                reason=candidate.reason,
                observed_at=candidate.observed_at,
                reading_id=candidate.reading_id,
            )
            db.add(event)
            saved.append(event)
            logger.info(
                "Event saved — %s | %s | %s",
                candidate.event_type,
                candidate.city,
                candidate.observed_at,
            )

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return saved


#  Public interface 

def detect_city_events(
    db: Session,
    reading: WeatherReading,
) -> list[WeatherEvent]:
    """
    Run all city-level detectors against the latest reading
    Called once per city after a new reading is inserted
    """
    recent = _get_recent_readings(db, reading.city, reading.observed_at)

    candidates: list[EventCandidate] = []
    candidates.extend(detect_rapid_temperature_drop(reading, recent))
    candidates.extend(detect_freeze_thaw_risk(reading, recent))
    candidates.extend(detect_wind_escalation(reading, recent))

    return persist_candidates(db, candidates)


def detect_regional_events(db: Session) -> list[WeatherEvent]:
    """
    Run all regional detectors that require data across all cities.
    Called once per poll cycle after all cities have been processed.
    """
    latest_by_city = _get_latest_reading_per_city(db)
    latest_readings = list(latest_by_city.values())
    if len(latest_readings) < 3:
        return []

    trigger_reading = max(latest_readings, key=lambda r: r.observed_at)

    candidates: list[EventCandidate] = []
    candidates.extend(detect_cross_city_temperature_spread(trigger_reading, latest_readings))

    return persist_candidates(db, candidates)