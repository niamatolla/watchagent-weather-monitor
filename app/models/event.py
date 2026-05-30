from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from app.core.database import Base


class WeatherEvent(Base):
    __tablename__ = "weather_events"

    id = Column(Integer, primary_key=True, index=True)

    city = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)

    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)

    # Timestamp from Open-Meteo API not the database creation time
    observed_at = Column(DateTime, nullable=False, index=True)

    reading_id = Column(Integer, ForeignKey("weather_readings.id"), nullable=True)

    # Timestamp when the record is created in the database
    created_at = Column(DateTime, server_default=func.now(), nullable=False)