import asyncio

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.reading import WeatherReading
from app.services.weather_client import CITY_COORDS, fetch_current_weather


def save_reading(db, reading_data: dict) -> bool:
    """Insert a reading and return True if inserted False if duplicate (DB constraint)"""
    reading = WeatherReading(**reading_data)
    db.add(reading)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def poll_all_cities() -> dict:
    """Poll current weather for all supported cities and save to database and returns a summary of results"""
    db = SessionLocal()

    result = {
        "inserted": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        for city in CITY_COORDS.keys():
            try:
                reading_data = fetch_current_weather(city)
                inserted = save_reading(db, reading_data)

                if inserted:
                    result["inserted"] += 1
                    print(f"Inserted reading for {city}")
                else:
                    result["skipped"] += 1
                    print(f"Skipped duplicate for {city}")

            except Exception as e:
                result["errors"].append({"city": city, "error": str(e)})
                print(f"Error polling {city}: {e}")

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
    print(poll_all_cities())