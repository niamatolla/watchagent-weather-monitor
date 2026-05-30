from dataclasses import dataclass
from datetime import datetime


@dataclass
class EventCandidate:
    city: str
    event_type: str
    severity: str
    title: str
    description: str
    reason: str
    observed_at: datetime
    reading_id: int | None = None