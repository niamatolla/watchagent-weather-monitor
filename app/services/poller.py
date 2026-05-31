import asyncio
import logging
import signal
import sys

from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.reading import WeatherReading
from app.services.event_detection.engine import detect_city_events, detect_regional_events
from app.services.weather_client import CITY_COORDS, fetch_current_weather


logger = logging.getLogger(__name__)


def save_reading(db, reading_data: dict) -> WeatherReading | None:
    """Insert a reading and return persisted row, or None when duplicate."""
    reading = WeatherReading(**reading_data)
    db.add(reading)
    try:
        db.commit()
        db.refresh(reading)
        return reading
    except IntegrityError:
        db.rollback()
        return None


def poll_all_cities() -> dict:
    """Poll current weather for all supported cities and save to database and returns a summary of results"""
    db = SessionLocal()

    result = {
        "inserted": 0,
        "skipped": 0,
        "events_created": 0,
        "errors": [],
    }

    try:
        for city in CITY_COORDS.keys():
            try:
                reading_data = fetch_current_weather(city)
                inserted_reading = save_reading(db, reading_data)

                if inserted_reading:
                    result["inserted"] += 1
                    print(f"Inserted reading for {city}")

                    city_events = detect_city_events(db, inserted_reading)
                    if city_events:
                        result["events_created"] += len(city_events)
                        print(f"Generated {len(city_events)} city event(s) for {city}")
                else:
                    result["skipped"] += 1
                    print(f"Skipped duplicate for {city}")

            except Exception as e:
                result["errors"].append({"city": city, "error": str(e)})
                print(f"Error polling {city}: {e}")

        try:
            regional_events = detect_regional_events(db)
            if regional_events:
                result["events_created"] += len(regional_events)
                print(f"Generated {len(regional_events)} regional event(s)")
        except Exception as e:
            result["errors"].append({"city": "REGIONAL", "error": str(e)})
            print(f"Error detecting regional events: {e}")

        return result

    finally:
        db.close()


async def run_polling_loop(interval_seconds: int) -> None:
    """Run weather polling forever using the configured interval."""
    while True:
        try:
            result = await asyncio.to_thread(poll_all_cities)
            print(f"Polling cycle complete: {result}")
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Polling loop error: {e}")
            await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    def _shutdown_handler(signum, _frame):
        signame = signal.Signals(signum).name
        logger.info("Received %s, shutting down poller", signame)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _shutdown_handler)
    signal.signal(signal.SIGINT, _shutdown_handler)

    logger.info(
        "Starting poller loop with interval %s seconds",
        settings.poll_interval_seconds,
    )

    try:
        asyncio.run(run_polling_loop(settings.poll_interval_seconds))
    except SystemExit:
        logger.info("Poller stopped")
        sys.exit(0)