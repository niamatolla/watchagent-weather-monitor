from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReadingResponse(BaseModel):
	id: int
	city: str
	observed_at: datetime
	temperature_2m: float
	apparent_temperature: float
	precipitation: float
	wind_speed_10m: float
	weather_code: int
	created_at: datetime

	model_config = ConfigDict(from_attributes=True)


class ReadingsListResponse(BaseModel):
	readings: list[ReadingResponse]
