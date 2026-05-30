from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.reading import WeatherReading
from app.models.event import WeatherEvent

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "readings_stored": db.query(WeatherReading).count(),
        "events_stored": db.query(WeatherEvent).count(),
    }