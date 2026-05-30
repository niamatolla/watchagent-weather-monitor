from datetime import datetime, timedelta

from app.models.reading import WeatherReading
from app.services.event_detection.detectors import (
	detect_freeze_thaw_risk,
	detect_rapid_temperature_drop,
	detect_wind_escalation,
)

# Note: these tests are focused on the core logic of the detectors and do not require database access or full event persistence. They directly call the detector functions with crafted WeatherReading inputs to verify correct event candidate generation.

# FreezeThawRisk Detector Tests
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

# RapidTemperatureDrop Detector Tests
def test_rapid_temperature_drop_fires_on_6c_or_more_drop_within_3_hours():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=2),
		temperature_2m=12.0,
		apparent_temperature=11.5,
		precipitation=0.0,
		wind_speed_10m=9.0,
		weather_code=2,
	)
	current = WeatherReading(
		id=103,
		city="Ottawa",
		observed_at=now,
		temperature_2m=5.0,
		apparent_temperature=4.0,
		precipitation=0.0,
		wind_speed_10m=10.0,
		weather_code=3,
	)

	events = detect_rapid_temperature_drop(current, [previous])

	assert len(events) == 1
	assert events[0].event_type == "RapidTemperatureDrop"
	assert events[0].severity == "Warning"


def test_rapid_temperature_drop_does_not_fire_below_threshold():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=2),
		temperature_2m=12.0,
		apparent_temperature=11.0,
		precipitation=0.0,
		wind_speed_10m=9.0,
		weather_code=2,
	)
	current = WeatherReading(
		id=104,
		city="Ottawa",
		observed_at=now,
		temperature_2m=8.5,
		apparent_temperature=8.0,
		precipitation=0.0,
		wind_speed_10m=9.5,
		weather_code=2,
	)

	events = detect_rapid_temperature_drop(current, [previous])

	assert events == []


# WindEscalation Detector Tests
def test_wind_escalation_fires_on_consecutive_jump_of_20_kmh_or_more():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=1),
		temperature_2m=10.0,
		apparent_temperature=9.0,
		precipitation=0.0,
		wind_speed_10m=18.0,
		weather_code=2,
	)
	current = WeatherReading(
		id=105,
		city="Ottawa",
		observed_at=now,
		temperature_2m=9.0,
		apparent_temperature=8.0,
		precipitation=0.0,
		wind_speed_10m=40.0,
		weather_code=3,
	)

	events = detect_wind_escalation(current, [previous])

	assert len(events) == 1
	assert events[0].event_type == "WindEscalation"
	assert events[0].severity == "Warning"


def test_wind_escalation_does_not_fire_below_jump_and_absolute_thresholds():
	now = datetime(2026, 5, 30, 12, 0, 0)
	previous = WeatherReading(
		city="Ottawa",
		observed_at=now - timedelta(hours=1),
		temperature_2m=10.0,
		apparent_temperature=9.0,
		precipitation=0.0,
		wind_speed_10m=20.0,
		weather_code=2,
	)
	current = WeatherReading(
		id=106,
		city="Ottawa",
		observed_at=now,
		temperature_2m=9.5,
		apparent_temperature=8.7,
		precipitation=0.0,
		wind_speed_10m=32.0,
		weather_code=2,
	)

	events = detect_wind_escalation(current, [previous])

	assert events == []
