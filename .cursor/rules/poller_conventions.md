# Rule: Weather Poller Conventions

## Scope
Applies to  `app/services/poller.py` and `app/services/weather_client.py` these conventions.

---

## API Fetch Failures

When a fetch to Open-Meteo fails for any reason (network error, non-200 status, malformed JSON, timeout), you MUST:

1. Log at WARNING level with structured context including:

- city name
- HTTP status code (if available)
- error message

Example:
```python
 logger.warning(
    "poll_failed city=%s status=%s error=%s",
    city_name,
    http_status_or_none,
    str(exception),
)
```
2. Do NOT raise the exception — swallow it and continue the poll loop.
3. Do NOT write a partial or empty reading to the database.


**Rationale:** The poller is a long-running background loop. A single city failing must never crash the entire service or skip the other cities. Structured log fields (city, status, attempt) make filtering in production trivial.

---

## Deduplication

## Deduplication

A reading is a duplicate if a reading already exists in the database for the same `city` and the same `observed_at`.

You MUST:

- Enforce a `UNIQUE` constraint on `(city, observed_at)` in the schema.
- Treat duplicate inserts as a no-op.
- Never crash the poller because of a duplicate reading.
- Roll back the failed transaction if the database raises an integrity error.
- Log at `DEBUG` level when a duplicate is skipped:

```python
logger.debug("duplicate_skipped city=%s observed_at=%s", city, observed_at)
```
**Rationale:** Open-Meteo updates once per hour but we poll more frequently (Every 15 min). Most polls will return data we have already stored. The constraint at the DB layer is a suspenders guard against race conditions.

---

## Reading Record Structure

Every stored reading MUST include these fields :


- `city`
- `observed_at`
- `temperature_2m`
- `apparent_temperature`
- `precipitation`
- `wind_speed_10m`
- `weather_code`
Do NOT store raw API response blobs. Extract only these fields.

---
## City Isolation

Failure for one city must not prevent polling of the remaining cities.

Example:

Ottawa -> failure
Toronto -> success
Vancouver -> success

The poll cycle is considered successful if remaining cities continue processing.

---

## Event detection trigger

Event detection should only run after a new reading is successfully inserted.

Duplicate readings must not trigger event detection.

## Reason

The poller is a long-running monitoring loop. One bad API response for one city should not crash the full service or block the other cities from being monitored.
