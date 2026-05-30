from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.reading import WeatherReading
from app.models.event import WeatherEvent
from app.schemas.reading import ReadingResponse, ReadingsListResponse

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)):
    return {
        "status": "ok",
        "readings_stored": db.query(WeatherReading).count(),
        "events_stored": db.query(WeatherEvent).count(),
    }


@router.get("/readings", response_model=ReadingsListResponse)
def list_readings(
    city: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1),
    db: Session = Depends(get_db),
):
    query = db.query(WeatherReading)

    if city:
        normalized_city = city.strip().lower()
        city_lookup = {allowed.lower(): allowed for allowed in settings.allowed_cities}
        if normalized_city not in city_lookup:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_city",
                    "message": "city must be one of: Ottawa, Toronto, Vancouver",
                },
            )
        query = query.filter(WeatherReading.city == city_lookup[normalized_city])

    readings = (
        query.order_by(WeatherReading.observed_at.desc(), WeatherReading.id.desc())
        .limit(limit)
        .all()
    )

    return {"readings": [ReadingResponse.model_validate(row) for row in readings]}