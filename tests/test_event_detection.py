from datetime import datetime, timedelta

from app.models.reading import WeatherReading
from app.services.event_detection.detectors import detect_freeze_thaw_risk


def test_freeze_thaw_risk_fires_on_crossing_zero():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=1),
		temperature_2m=1.5,
		apparent_temperature=1.0,
		precipitation=0.0,
		wind_speed_10m=12.0,
		weather_code=3,
	)
	current = WeatherReading(
		id=101,
		city="Ottawa",
		observed_at=now,
		temperature_2m=-0.5,
		apparent_temperature=-1.0,
		precipitation=0.2,
		wind_speed_10m=14.0,
		weather_code=71,
	)

	events = detect_freeze_thaw_risk(current, [previous])

	assert len(events) == 1
	assert events[0].event_type == "FreezeThawRisk"
	assert events[0].severity == "Warning"


def test_freeze_thaw_risk_does_not_fire_without_crossing_zero():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=1),
		temperature_2m=3.0,
		apparent_temperature=2.5,
		precipitation=0.0,
		wind_speed_10m=10.0,
		weather_code=2,
	)
	current = WeatherReading(
		id=102,
		city="Ottawa",
		observed_at=now,
		temperature_2m=2.0,
		apparent_temperature=1.7,
		precipitation=0.0,
		wind_speed_10m=11.0,
		weather_code=2,
	)

	events = detect_freeze_thaw_risk(current, [previous])

	assert events == []
