# API and DB Conventions

## Scope

Rules for API routes, response schemas, database access, and SQLAlchemy models in this project. 

---

## Architecture Split

The implemented split is:

```text
app/api/routes.py        # FastAPI route handlers
app/schemas/*.py         # Pydantic response models
app/models/*.py          # SQLAlchemy ORM tables
app/core/database.py     # engine, SessionLocal, Base, get_db
app/core/config.py       # runtime settings
```

Rules:
- Route handlers live in `app/api/routes.py`.
- ORM tables live in `app/models/`.
- API response contracts live in `app/schemas/`.
- Database session creation and dependency wiring live in `app/core/database.py`.
- Allowed cities and database URL come from `app/core/config.py`.

---

## Database Setup

The current database layer uses SQLAlchemy with a single shared engine and a session dependency.

Implemented pattern:

```python
engine = create_engine(
	DATABASE_URL,
	connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
	autocommit=False,
	autoflush=False,
	bind=engine,
)

Base = declarative_base()

def get_db():
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()
```

Rules:
- Use `SessionLocal()` to create DB sessions.
- Access DB sessions in routes via `db: Session = Depends(get_db)`.
- `get_db()` must always close the session in `finally`.
- ORM models must inherit from `Base` from `app.core.database`.

---

## Configuration Values

The current settings model defines:

```python
class Settings(BaseSettings):
	app_name: str = "WatchAgent Weather Monitor"
	database_url: str = "sqlite:///data/weather.db"
	app_version: str = "1.0.0"
	allowed_cities: tuple[str, str, str] = ("Ottawa", "Toronto", "Vancouver")
	poll_interval_seconds: int = 900
```

Rules:
- Validate city query parameters against `settings.allowed_cities`.
- Do not duplicate the canonical city list elsewhere when route validation can use settings.
- Use the configured `database_url` through `settings.database_url`.

---

## API Route Conventions

The implemented routes are:
- `GET /health`
- `GET /readings`
- `GET /events`

Rules:
- Rules:
- Route handlers access the database through the injected `db` session, either directly or through project service functions.
- `GET /readings` returns `response_model=ReadingsListResponse`.
- `GET /events` returns `response_model=EventsListResponse`.
- Responses are wrapped in top-level objects, not returned as bare lists:
  - `/readings` returns `{ "readings": [...] }`
  - `/events` returns `{ "events": [...] }`

---

## Health Endpoint

The current `/health` endpoint returns database counts.

Implemented response shape:

```python
{
	"status": "ok",
	"readings_stored": db.query(WeatherReading).count(),
	"events_stored": db.query(WeatherEvent).count(),
}
```

Rules:
- `status` is the string `"ok"`.
- `readings_stored` is the count of `WeatherReading` rows.
- `events_stored` is the count of `WeatherEvent` rows.

---

## Readings Endpoint

The current `/readings` endpoint supports:
- optional `city`
- optional `limit` with `ge=1`

Implemented query pattern:

```python
query = db.query(WeatherReading)

if city:
	normalized_city = city.strip().lower()
	city_lookup = {allowed.lower(): allowed for allowed in settings.allowed_cities}
	if normalized_city not in city_lookup:
		raise HTTPException(status_code=400, detail={...})
	query = query.filter(WeatherReading.city == city_lookup[normalized_city])

readings = (
	query.order_by(WeatherReading.observed_at.desc(), WeatherReading.id.desc())
	.limit(limit)
	.all()
)
```

Rules:
- Normalize incoming `city` using `.strip().lower()` before validation.
- Validate `city` against `settings.allowed_cities`.
- Invalid city returns `HTTPException(status_code=400)` with:
  - `error: "invalid_city"`
  - `message: "city must be one of: Ottawa, Toronto, Vancouver"`
- Order readings by `observed_at.desc(), id.desc()`.
- Return serialized rows through `ReadingResponse.model_validate(row)`.

---

## Events Endpoint

The current `/events` endpoint supports:
- optional `city`
- optional `event_type`
- optional `limit` with `ge=1`

Implemented query pattern:

```python
query = db.query(WeatherEvent)

if city:
	normalized_city = city.strip().lower()
	allowed_event_cities = (*settings.allowed_cities, "REGIONAL")
	city_lookup = {allowed.lower(): allowed for allowed in allowed_event_cities}
	if normalized_city not in city_lookup:
		raise HTTPException(status_code=400, detail={...})
	query = query.filter(WeatherEvent.city == city_lookup[normalized_city])

if event_type:
	query = query.filter(WeatherEvent.event_type == event_type.strip())

events = (
	query.order_by(WeatherEvent.observed_at.desc(), WeatherEvent.id.desc())
	.limit(limit)
	.all()
)
```

Rules:
- `city` validation includes `REGIONAL` in addition to configured cities.
- Normalize `city` using `.strip().lower()` before validation.
- Normalize `event_type` with `.strip()` before filtering.
- Invalid city returns `HTTPException(status_code=400)` with:
  - `error: "invalid_city"`
  - `message: "city must be one of: Ottawa, Toronto, Vancouver, REGIONAL"`
- Order events by `observed_at.desc(), id.desc()`.
- Return serialized rows through `EventResponse.model_validate(row)`.

---

## Response Schema Conventions

Current response schemas use Pydantic models with `from_attributes=True`.

Implemented pattern:

```python
class ReadingResponse(BaseModel):
	...
	model_config = ConfigDict(from_attributes=True)

class EventResponse(BaseModel):
	...
	model_config = ConfigDict(from_attributes=True)
```

Rules:
- Route responses are serialized through Pydantic schema models, not returned as raw ORM objects.
- Schema wrappers are:
  - `ReadingsListResponse` with `readings: list[ReadingResponse]`
  - `EventsListResponse` with `events: list[EventResponse]`
- Schema fields must match the ORM columns currently exposed by the API.

Implemented fields:
- `ReadingResponse`: `id`, `city`, `observed_at`, `temperature_2m`, `apparent_temperature`, `precipitation`, `wind_speed_10m`, `weather_code`, `created_at`
- `EventResponse`: `id`, `city`, `event_type`, `severity`, `title`, `description`, `reason`, `observed_at`, `reading_id`, `created_at`

---

## WeatherReading Model Conventions

The current `WeatherReading` model includes:
- `id` primary key
- `city` indexed string
- `observed_at` indexed datetime
- weather metric columns as non-null scalars
- `created_at` with `server_default=func.now()`
- composite uniqueness on `(city, observed_at)`

Implemented pattern:

```python
__table_args__ = (
	UniqueConstraint("city", "observed_at", name="uq_city_observed_at"),
)
```

Rules:
- `observed_at` is the source timestamp from the weather API, not DB insertion time.
- `created_at` is the database record creation timestamp.
- Keep the unique constraint on `(city, observed_at)` to prevent duplicate readings for the same timestamp.

---

## WeatherEvent Model Conventions

The current `WeatherEvent` model includes:
- `id` primary key
- indexed `city`, `event_type`, and `severity`
- `title`, `description`, `reason`
- indexed `observed_at`
- nullable `reading_id` foreign key to `weather_readings.id`
- `created_at` with `server_default=func.now()`

Rules:
- `reading_id` may be `None` for regional events.
- `observed_at` is the event observation timestamp, not the insert timestamp.
- `created_at` is the database record creation timestamp.

---

## API Test Conventions

The current API tests use an isolated in-memory SQLite database and FastAPI dependency overrides.

Implemented pattern:

```python
engine = create_engine(
	"sqlite://",
	connect_args={"check_same_thread": False},
	poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
```

Rules:
- API tests build a dedicated FastAPI app and include the real router.
- API tests override `get_db` with a test session factory.
- Seed test data through ORM objects, then call the HTTP endpoints with `TestClient`.
- API tests assert response shape, filtering behavior, and ordering.

Current test coverage in `tests/test_api.py`:
- `/health` returns `status`, `readings_stored`, `events_stored`
- `/readings` returns the expected keys and most recent rows first
- `/events` returns the expected keys and respects `city` and `event_type` filters
