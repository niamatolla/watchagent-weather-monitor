import logging
from datetime import datetime, timedelta
from app.services.event_detection.schemas import EventCandidate
from app.models.reading import WeatherReading

logger = logging.getLogger(__name__)

# City aware thresholds for event detection

FREEZE_THAW_CITIES = {"Ottawa", "Toronto"}  # Vancouver rarely freezes

# Helpers 
def _get_window(
    readings: list[WeatherReading],
    reference_time: datetime,
    hours: int,
) -> list[WeatherReading]:
    """Return readings within the last N hours of reference_time, oldest first."""
    cutoff = reference_time - timedelta(hours=hours)
    window = [r for r in readings if cutoff <= r.observed_at <= reference_time]
    return sorted(window, key=lambda r: r.observed_at)

# Detector 1: Rapid Temperature Drop
def detect_rapid_temperature_drop(
    reading: WeatherReading,
    recent_readings: list[WeatherReading],
) -> list[EventCandidate]:
    """
    Fires when temperature drops >= 6C within a 3-hour window
    Change based trigger
    """
    THRESHOLD_DROP = 6.0
    WINDOW_HOURS = 3

    window = _get_window(recent_readings, reading.observed_at, WINDOW_HOURS)

    # Include current reading if it is not already in the supplied history.
    if not any(r.observed_at == reading.observed_at and r.city == reading.city for r in window):
        window = sorted([*window, reading], key=lambda r: r.observed_at)

    if len(window) < 2:
        logger.debug("RapidTemperatureDrop: no history window for %s", reading.city)
        return []

    # Smoothed drop compare the average of the earliest and latest segment.
    segment_size = 2 if len(window) >= 4 else 1
    start_avg = sum(r.temperature_2m for r in window[:segment_size]) / segment_size
    end_avg = sum(r.temperature_2m for r in window[-segment_size:]) / segment_size
    drop = start_avg - end_avg

    if drop < THRESHOLD_DROP:
        return []

    logger.info(
        "RapidTemperatureDrop detected in %s — %.1f°C drop over %dh",
        reading.city, drop, WINDOW_HOURS,
    )

    return [EventCandidate(
        city=reading.city,
        event_type="RapidTemperatureDrop",
        severity="Warning",
        title=f"Rapid temperature drop in {reading.city}",
        description=(
            f"Smoothed temperature fell from {start_avg:.1f}°C to "
            f"{end_avg:.1f}°C in {WINDOW_HOURS} hours."
        ),
        reason=(
            f"A smoothed drop of {drop:.1f}°C within {WINDOW_HOURS}h exceeds the "
            f"{THRESHOLD_DROP}°C RapidTemperatureDrop threshold."
        ),
        observed_at=reading.observed_at,
        reading_id=reading.id,
    )]


def detect_freeze_thaw_risk(
    reading: WeatherReading,
    recent_readings: list[WeatherReading],
) -> list[EventCandidate]:
    """Fire when temperature crosses above/below 0C within a 6-hour window"""
    WINDOW_HOURS = 6
    FREEZING_POINT_C = 0.0

    if reading.city not in FREEZE_THAW_CITIES:
        logger.debug("FreezeThawRisk skipped for %s (city not targeted)", reading.city)
        return []

    window = _get_window(recent_readings, reading.observed_at, WINDOW_HOURS)
    if not any(r.observed_at == reading.observed_at and r.city == reading.city for r in window):
        window = sorted([*window, reading], key=lambda r: r.observed_at)

    if len(window) < 2:
        logger.debug("FreezeThawRisk: no history window for %s", reading.city)
        return []

    crossing = None
    for previous, current in zip(window, window[1:]):
        previous_temp = previous.temperature_2m
        current_temp = current.temperature_2m

        crossed_down = previous_temp > FREEZING_POINT_C and current_temp < FREEZING_POINT_C
        crossed_up = previous_temp < FREEZING_POINT_C and current_temp > FREEZING_POINT_C

        if crossed_down or crossed_up:
            crossing = (previous, current)
            break

    if crossing is None:
        return []

    before, after = crossing
    direction = "above to below" if before.temperature_2m > 0 else "below to above"

    logger.info(
        "FreezeThawRisk detected in %s — crossing %s 0C within %dh",
        reading.city,
        direction,
        WINDOW_HOURS,
    )

    return [EventCandidate(
        city=reading.city,
        event_type="FreezeThawRisk",
        severity="Warning",
        title=f"Freeze-thaw risk in {reading.city}",
        description=(
            f"Temperature crossed from {before.temperature_2m:.1f}°C to "
            f"{after.temperature_2m:.1f}°C ({direction} 0°C) within {WINDOW_HOURS} hours."
        ),
        reason=(
            f"Crossing around 0°C within {WINDOW_HOURS}h increases risk of icy roads "
            f"and sidewalks."
        ),
        observed_at=reading.observed_at,
        reading_id=reading.id,
    )]


def detect_wind_escalation(
    reading: WeatherReading,
    recent_readings: list[WeatherReading],
) -> list[EventCandidate]:
    """Fire when wind escalates quickly or reaches high absolute speed"""
    ESCALATION_THRESHOLD_KMH = 20.0
    HIGH_WIND_THRESHOLD_KMH = 50.0

    # Absolute trigger does not require history.
    if reading.wind_speed_10m >= HIGH_WIND_THRESHOLD_KMH:
        logger.info(
            "WindEscalation detected in %s — high wind %.1f km/h",
            reading.city,
            reading.wind_speed_10m,
        )
        return [EventCandidate(
            city=reading.city,
            event_type="WindEscalation",
            severity="Warning",
            title=f"Strong wind detected in {reading.city}",
            description=(
                f"Wind speed reached {reading.wind_speed_10m:.1f} km/h, "
                f"meeting the {HIGH_WIND_THRESHOLD_KMH:.0f} km/h threshold."
            ),
            reason=(
                f"Wind speed at or above {HIGH_WIND_THRESHOLD_KMH:.0f} km/h can impact "
                f"transportation and outdoor safety."
            ),
            observed_at=reading.observed_at,
            reading_id=reading.id,
        )]

    # Consecutive-reading trigger requires at least one earlier reading.
    previous_candidates = [
        r for r in recent_readings if r.city == reading.city and r.observed_at < reading.observed_at
    ]
    if not previous_candidates:
        logger.debug("WindEscalation: no previous reading for %s", reading.city)
        return []

    previous = max(previous_candidates, key=lambda r: r.observed_at)
    increase = reading.wind_speed_10m - previous.wind_speed_10m

    if increase < ESCALATION_THRESHOLD_KMH:
        return []

    logger.info(
        "WindEscalation detected in %s — +%.1f km/h between consecutive readings",
        reading.city,
        increase,
    )

    return [EventCandidate(
        city=reading.city,
        event_type="WindEscalation",
        severity="Warning",
        title=f"Wind escalation detected in {reading.city}",
        description=(
            f"Wind speed increased from {previous.wind_speed_10m:.1f} km/h to "
            f"{reading.wind_speed_10m:.1f} km/h between consecutive readings."
        ),
        reason=(
            f"A +{increase:.1f} km/h jump exceeds the {ESCALATION_THRESHOLD_KMH:.0f} km/h "
            f"WindEscalation threshold."
        ),
        observed_at=reading.observed_at,
        reading_id=reading.id,
    )]


def detect_cross_city_temperature_spread(
    reading: WeatherReading,
    recent_readings: list[WeatherReading],
) -> list[EventCandidate]:
    """Fire when cross-city max-min temperature spread is >= 15C"""
    SPREAD_THRESHOLD_C = 15.0

    # Build latest snapshot per city up to this reading timestamp.
    snapshot_candidates = [
        r for r in recent_readings if r.observed_at <= reading.observed_at
    ]
    if not any(
        r.city == reading.city and r.observed_at == reading.observed_at
        for r in snapshot_candidates
    ):
        snapshot_candidates.append(reading)

    latest_by_city: dict[str, WeatherReading] = {}
    for item in sorted(snapshot_candidates, key=lambda r: r.observed_at):
        latest_by_city[item.city] = item

    if len(latest_by_city) < 3:
        logger.debug("CrossCityTemperatureSpread: incomplete city snapshot")
        return []

    city_temps = {city: value.temperature_2m for city, value in latest_by_city.items()}
    hottest_city = max(city_temps, key=city_temps.get)
    coldest_city = min(city_temps, key=city_temps.get)
    spread = city_temps[hottest_city] - city_temps[coldest_city]

    if spread < SPREAD_THRESHOLD_C:
        return []

    logger.info(
        "CrossCityTemperatureSpread detected — %.1fC between %s and %s",
        spread,
        hottest_city,
        coldest_city,
    )

    return [EventCandidate(
        city="REGIONAL",
        event_type="CrossCityTemperatureSpread",
        severity="Informational",
        title="Large cross-city temperature spread",
        description=(
            f"Temperature spread is {spread:.1f}°C between {hottest_city} "
            f"({city_temps[hottest_city]:.1f}°C) and {coldest_city} "
            f"({city_temps[coldest_city]:.1f}°C)."
        ),
        reason=(
            f"Max-min city temperature difference of {spread:.1f}°C meets/exceeds "
            f"the {SPREAD_THRESHOLD_C:.0f}°C CrossCityTemperatureSpread threshold."
        ),
        observed_at=reading.observed_at,
        reading_id=None,
    )]









