# Event Detection Conventions

Rules for adding or modifying event detectors in `app/services/event_detection/`.

---

## Module Layout

```
app/services/event_detection/
├── schemas.py    # EventCandidate dataclass — the detector output contract
├── detectors.py  # Pure detector functions — no DB, no side effects
├── cooldown.py   # DB-backed cooldown guard — one cooldown per event_type
└── engine.py     # Orchestrator — wires detectors → cooldown → persistence
```

**Rule:** never import from `engine.py` inside `detectors.py` or `cooldown.py`. The dependency flow is strictly one-way: `engine → detectors`, `engine → cooldown`.

---

## Detector Function Contract

Every detector must follow this exact signature:

```python
def detect_<event_name>(
    reading: WeatherReading,
    recent_readings: list[WeatherReading],
) -> list[EventCandidate]:
```

- `reading` — the current (latest) `WeatherReading` being evaluated.
- `recent_readings` — historical readings for the same city, fetched by the engine. The detector must not query the DB itself.
- Return an **empty list** when the condition is not met; never return `None`.
- Return a **list with one `EventCandidate`** when the condition is met (detectors are not expected to return multiple candidates per call today).

---

## EventCandidate Fields

All fields are required unless noted. Populate them precisely:

| Field | Type | Rule |
|-------|------|------|
| `city` | `str` | Copy from `reading.city`. |
| `event_type` | `str` | PascalCase, matches the function name suffix (e.g. `"FreezeThawRisk"`). Must also exist as a key in `COOLDOWN_HOURS`. |
| `severity` | `str` | `"Warning"` or `"Informational"`. |
| `title` | `str` | Short human label, include city name. |
| `description` | `str` | Full sentence explaining what was observed with concrete values. |
| `reason` | `str` | Full sentence explaining why the threshold was crossed. Mention the threshold value. |
| `observed_at` | `datetime` | Copy from `reading.observed_at`. |
| `reading_id` | `int \| None` | Copy from `reading.id`. |

---

## Time Window Helper

Use `_get_window()` (defined in `detectors.py`) to slice `recent_readings` to a precise lookback period. Do not reimplement time filtering inside a new detector.

```python
window = _get_window(recent_readings, reading.observed_at, hours=WINDOW_HOURS)
```

Always include the current reading in the window if it is not already present:

```python
if not any(r.observed_at == reading.observed_at and r.city == reading.city for r in window):
    window = sorted([*window, reading], key=lambda r: r.observed_at)
```

Guard against single-reading windows before computing deltas:

```python
if len(window) < 2:
    logger.debug("DetectorName: no history window for %s", reading.city)
    return []
```

---

## City Scope Guards

Some detectors only apply to specific cities. Declare the allowed set as a module-level constant and guard at the top of the function:

```python
FREEZE_THAW_CITIES = {"Ottawa", "Toronto"}  # Vancouver rarely freezes

def detect_freeze_thaw_risk(reading, recent_readings):
    if reading.city not in FREEZE_THAW_CITIES:
        logger.debug("FreezeThawRisk skipped for %s (city not targeted)", reading.city)
        return []
```

**Rule:** city-scope constants live in `detectors.py`, not in `engine.py` or `cooldown.py`.

---

## Thresholds

- Declare all numeric thresholds as local `UPPER_CASE` constants at the top of each detector function body.
- Reference the constant in the `EventCandidate.reason` field so the reason string always matches the actual threshold.
- When you change a threshold, update the corresponding unit test.

---

## Cooldown Registration

Every new `event_type` **must** be registered in `COOLDOWN_HOURS` in `cooldown.py`:

```python
COOLDOWN_HOURS: dict[str, int] = {
    "RapidTemperatureDrop": 3,
    "FreezeThawRisk": 6,
    "WindEscalation": 3,
    "CrossCityTemperatureSpread": 6,
    # Add your new event_type here
}
```

If missing, `is_on_cooldown` silently falls back to 3 h (the default), which may not be the intended behaviour.

---

## Engine Registration

City-level detectors are called in `detect_city_events()`. Regional detectors (requiring data from multiple cities) are called in `detect_regional_events()`.

**City-level** — add to `detect_city_events`:
```python
candidates.extend(detect_your_new_detector(reading, recent))
```

**Regional** — add to `detect_regional_events`:
```python
candidates.extend(detect_your_regional_detector(trigger_reading, latest_readings))
```

Do not call `persist_candidates()` directly from a detector. The engine owns persistence.

---

## Logging

Use the module-level logger (`logger = logging.getLogger(__name__)`):

| Situation | Level |
|-----------|-------|
| Condition not met / skipped | `logger.debug(...)` |
| Condition met, event firing | `logger.info(...)` |
| Unexpected error | `logger.error(...)` or raise |

Always include `city` and the quantitative delta in `logger.info` messages.

---

## Unit Testing

Every detector must have unit tests in `tests/test_event_detection.py`.

### Required test cases per detector

1. **Fires** — craft a `previous` + `current` `WeatherReading` pair that clearly crosses the threshold. Assert:
   - `len(events) == 1`
   - `events[0].event_type == "<EventType>"`
   - `events[0].severity == "Warning"` (or `"Informational"` for regional/informational events)

2. **Does not fire** — same pair shape but values just below the threshold. Assert `events == []`.

3. **City exclusion** — only required when the detector has a city-scope guard (e.g. `FREEZE_THAW_CITIES`). Use an excluded city with values that would otherwise fire. Assert `events == []`.

### Regional detectors (e.g. CrossCityTemperatureSpread)

Regional detectors receive one reading per city as a flat list. The fires test must also assert:
- `events[0].city == "REGIONAL"`

### Test structure rules

- Build `WeatherReading` objects directly with keyword arguments — no DB session, no HTTP calls.
- Pass `[previous]` as `recent_readings`; the detector under test handles window construction.
- Import only from `app.services.event_detection.detectors` — never from `engine.py`.
- If you change a threshold in `detectors.py`, update the corresponding test values to match.

---

## Naming Conventions

| Artifact | Convention | Example |
|----------|-----------|---------|
| Detector function | `detect_<snake_case>` | `detect_freeze_thaw_risk` |
| `event_type` string | PascalCase | `"FreezeThawRisk"` |
| City-scope constant | `<EVENT>_CITIES` | `FREEZE_THAW_CITIES` |
| Window constant | `WINDOW_HOURS` | `WINDOW_HOURS = 6` |
| Threshold constant | Descriptive upper snake | `THRESHOLD_DROP = 6.0` |
