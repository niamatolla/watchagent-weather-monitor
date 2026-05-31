from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.reading import WeatherReading
from app.services import poller


def test_poller_deduplicates_same_city_and_observed_at(monkeypatch):
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)
	TestingSessionLocal = sessionmaker(
		autocommit=False,
		autoflush=False,
		bind=engine,
	)
	Base.metadata.create_all(bind=engine)

	monkeypatch.setattr(poller, "SessionLocal", TestingSessionLocal)
	monkeypatch.setattr(poller, "CITY_COORDS", {"Ottawa": (45.42, -75.69)})
	monkeypatch.setattr(poller, "detect_city_events", lambda db, reading: [])
	monkeypatch.setattr(poller, "detect_regional_events", lambda db: [])

	observed_at = datetime(2026, 5, 30, 12, 0, 0)
	reading_payload = {
		"city": "Ottawa",
		"observed_at": observed_at,
		"temperature_2m": 12.0,
		"apparent_temperature": 11.0,
		"precipitation": 0.0,
		"wind_speed_10m": 18.0,
		"weather_code": 2,
	}

	monkeypatch.setattr(
		poller,
		"fetch_current_weather",
		lambda city: dict(reading_payload),
	)

	first_cycle = poller.poll_all_cities()
	second_cycle = poller.poll_all_cities()

	with TestingSessionLocal() as db:
		count = (
			db.query(WeatherReading)
			.filter(
				WeatherReading.city == "Ottawa",
				WeatherReading.observed_at == observed_at,
			)
			.count()
		)

	assert first_cycle["inserted"] == 1
	assert first_cycle["skipped"] == 0
	assert second_cycle["inserted"] == 0
	assert second_cycle["skipped"] == 1
	assert count == 1
