from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.core.database import Base, get_db
from app.models.event import WeatherEvent
from app.models.reading import WeatherReading


def _build_test_client() -> tuple[TestClient, sessionmaker]:
	engine = create_engine(
		"sqlite://",
		connect_args={"check_same_thread": False},
		poolclass=StaticPool,
	)
	TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
	Base.metadata.create_all(bind=engine)

	app = FastAPI()
	app.include_router(router)

	def override_get_db():
		db = TestingSessionLocal()
		try:
			yield db
		finally:
			db.close()

	app.dependency_overrides[get_db] = override_get_db
	client = TestClient(app)
	return client, TestingSessionLocal


def _seed_data(SessionLocal: sessionmaker) -> None:
	with SessionLocal() as db:
		reading_old = WeatherReading(
			city="Ottawa",
			observed_at=datetime(2026, 5, 30, 11, 0, 0),
			temperature_2m=10.0,
			apparent_temperature=9.0,
			precipitation=0.0,
			wind_speed_10m=12.0,
			weather_code=2,
		)
		reading_new = WeatherReading(
			city="Ottawa",
			observed_at=datetime(2026, 5, 30, 12, 0, 0),
			temperature_2m=8.0,
			apparent_temperature=7.0,
			precipitation=0.1,
			wind_speed_10m=14.0,
			weather_code=3,
		)
		reading_toronto = WeatherReading(
			city="Toronto",
			observed_at=datetime(2026, 5, 30, 12, 0, 0),
			temperature_2m=13.0,
			apparent_temperature=12.0,
			precipitation=0.0,
			wind_speed_10m=10.0,
			weather_code=1,
		)
		db.add_all([reading_old, reading_new, reading_toronto])
		db.commit()
		db.refresh(reading_new)

		event_city = WeatherEvent(
			city="Ottawa",
			event_type="RapidTemperatureDrop",
			severity="Warning",
			title="Rapid temperature drop in Ottawa",
			description="Temperature fell quickly.",
			reason="Drop exceeds configured threshold.",
			observed_at=datetime(2026, 5, 30, 12, 0, 0),
			reading_id=reading_new.id,
		)
		event_regional = WeatherEvent(
			city="REGIONAL",
			event_type="CrossCityTemperatureSpread",
			severity="Informational",
			title="Large cross-city temperature spread",
			description="Spread is high across monitored cities.",
			reason="Regional spread threshold exceeded.",
			observed_at=datetime(2026, 5, 30, 12, 0, 0),
			reading_id=None,
		)
		db.add_all([event_city, event_regional])
		db.commit()


def test_health_returns_expected_shape_for_seeded_dataset():
	client, SessionLocal = _build_test_client()
	_seed_data(SessionLocal)

	response = client.get("/health")

	assert response.status_code == 200
	payload = response.json()
	assert set(payload.keys()) == {"status", "readings_stored", "events_stored"}
	assert payload["status"] == "ok"
	assert payload["readings_stored"] == 3
	assert payload["events_stored"] == 2


def test_readings_returns_expected_shape_and_most_recent_first():
	client, SessionLocal = _build_test_client()
	_seed_data(SessionLocal)

	response = client.get("/readings", params={"city": "Ottawa", "limit": 50})

	assert response.status_code == 200
	payload = response.json()
	assert "readings" in payload
	assert isinstance(payload["readings"], list)
	assert len(payload["readings"]) == 2

	first = payload["readings"][0]
	expected_keys = {
		"id",
		"city",
		"observed_at",
		"temperature_2m",
		"apparent_temperature",
		"precipitation",
		"wind_speed_10m",
		"weather_code",
		"created_at",
	}
	assert set(first.keys()) == expected_keys
	assert first["city"] == "Ottawa"
	assert payload["readings"][0]["observed_at"] >= payload["readings"][1]["observed_at"]


def test_events_returns_expected_shape_and_filters():
	client, SessionLocal = _build_test_client()
	_seed_data(SessionLocal)

	response = client.get(
		"/events",
		params={"city": "Ottawa", "event_type": "RapidTemperatureDrop", "limit": 50},
	)

	assert response.status_code == 200
	payload = response.json()
	assert "events" in payload
	assert isinstance(payload["events"], list)
	assert len(payload["events"]) == 1

	event = payload["events"][0]
	expected_keys = {
		"id",
		"city",
		"event_type",
		"severity",
		"title",
		"description",
		"reason",
		"observed_at",
		"reading_id",
		"created_at",
	}
	assert set(event.keys()) == expected_keys
	assert event["city"] == "Ottawa"
	assert event["event_type"] == "RapidTemperatureDrop"
