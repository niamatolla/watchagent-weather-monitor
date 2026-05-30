from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint, func
from app.core.database import Base

# SQLAlchemy model for weather readings
class WeatherReading(Base):
    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True, index=True)

    city = Column(String, nullable=False, index=True)
    # Timestamp from Open-Meteo API not the database creation time
    observed_at = Column(DateTime, nullable=False, index=True)

    temperature_2m = Column(Float, nullable=False)
    apparent_temperature = Column(Float, nullable=False)
    precipitation = Column(Float, nullable=False)
    wind_speed_10m = Column(Float, nullable=False)
    weather_code = Column(Integer, nullable=False)

    # Timestamp when the record is created in the database
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Composite Unique constraint to ensure that each city can only have one reading per observed_at timestamp
    __table_args__ = (
        UniqueConstraint("city", "observed_at", name="uq_city_observed_at"),
    )