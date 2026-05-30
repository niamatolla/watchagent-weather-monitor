from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.event import WeatherEvent


COOLDOWN_HOURS: dict[str, int] = {
	"RapidTemperatureDrop": 3,
	"FreezeThawRisk": 6,
	"WindEscalation": 3,
	"CrossCityTemperatureSpread": 6,
}


def is_on_cooldown(
	db: Session,
	city: str,
	event_type: str,
	observed_at: datetime,
) -> bool:
	"""Return True when the same event type already fired recently for a city."""
	hours = COOLDOWN_HOURS.get(event_type, 3)
	cutoff = observed_at - timedelta(hours=hours)

	recent_event = (
		db.query(WeatherEvent)
		.filter(
			WeatherEvent.city == city,
			WeatherEvent.event_type == event_type,
			WeatherEvent.observed_at >= cutoff,
		)
		.order_by(WeatherEvent.observed_at.desc(), WeatherEvent.id.desc())
		.first()
	)

	return recent_event is not None
