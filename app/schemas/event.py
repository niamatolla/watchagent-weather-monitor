from datetime import datetime

from pydantic import BaseModel, ConfigDict

class EventResponse(BaseModel):
	id: int
	city: str
	event_type: str
	severity: str
	title: str
	description: str
	reason: str
	observed_at: datetime
	reading_id: int | None
	created_at: datetime

	model_config = ConfigDict(from_attributes=True)


class EventsListResponse(BaseModel):
	events: list[EventResponse]
