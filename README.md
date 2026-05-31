## Event Detection Design

The goal of this event detection system is to surface weather conditions that are actually worth paying attention to while avoiding alert spam.

When I designed these events, I tried to balance two competing problems:

* If thresholds are too sensitive, the system generates noise and events lose their value.
* If thresholds are too strict, important weather changes are missed.

To solve this, I chose a mix of different detection approaches. Some events look for rapid changes over time, some look for meaningful threshold crossings, some use absolute thresholds, and one compares conditions across multiple cities.

Another important design decision is that event detection only runs when a new weather reading is inserted into the database.

Open-Meteo updates its weather data hourly, but the poller runs every 15 minutes. This means most poll cycles return the same timestamp that has already been stored. Because the application enforces a unique `(city, observed_at)` constraint, duplicate readings are discarded before event detection runs.

As a result, event detection is only executed when genuinely new weather information becomes available.

### Detection Philosophy

I intentionally chose different categories of events because each one captures a different type of weather signal:

* **Trend-based events** detect conditions that are changing quickly.
* **Threshold-crossing events** detect transitions through important values.
* **Absolute threshold events** detect conditions that are already severe.
* **Regional comparison events** detect meaningful differences between cities.

I also wanted to avoid alert fatigue. If the same event fires every hour during a long weather pattern, it stops being useful. To reduce noise, the system uses:

* meaningful thresholds
* city-specific event scopes where appropriate
* cooldown periods
* regional events only when differences are large enough to matter

The result is a small set of events that focus on significant weather changes rather than reporting every fluctuation in the data.

## Event Catalogue

### 1. RapidTemperatureDrop
- Severity: `Warning`
- Cooldown: `3 hours`
- Scope: `City-level`

This event fires when the temperature drops by at least `6°C` within a `3-hour` window.

I chose this event because a sudden temperature drop is more useful than just checking whether temperature is cold. A city can stay cold for hours and that is not necessarily a new signal. The useful signal is how fast conditions are changing.

A `1-3°C` drop can happen naturally during the day and would create noise. A `6°C` drop in only `3 hours` is more meaningful and can indicate a cold front or rapidly changing conditions that affect safety and planning.

Key idea: this event does not care whether the city is currently warm or cold. It cares whether weather is changing unusually fast.

### 2. FreezeThawRisk
- Severity: `Warning`
- Cooldown: `6 hours`
- Scope: `Ottawa` and `Toronto` only

This event fires when temperature crosses `0°C` in either direction within a `6-hour` window.

I chose the freezing-point crossing because that transition is often more operationally important than absolute cold. If temperature stays below freezing, conditions may remain stable; when it moves around `0°C`, melt/refreeze cycles can create icy surfaces.

I scoped this event to Ottawa and Toronto because freeze-thaw cycles are more relevant there. Vancouver is intentionally excluded for this detector to reduce low-value noise.

Key idea: the risk is the transition around freezing, not just cold weather.

### 3. WindEscalation
- Severity: `Warning`
- Cooldown: `3 hours`
- Scope: `City-level`

This event fires when either:
- wind speed increases by at least `20 km/h` between consecutive readings, or
- wind speed reaches at least `50 km/h`.

I used two conditions because they capture different situations. The jump condition catches approaching risk (rapid escalation). The absolute threshold catches existing risk even if the increase was gradual.

Key idea: one condition captures fast worsening; the other captures already severe wind.

### 4. CrossCityTemperatureSpread
- Severity: `Informational`
- Cooldown: `6 hours`
- Scope: `Regional`

This event fires when the temperature spread between the warmest and coldest monitored city is at least `14°C`.

This is a regional comparator event, not a city-local hazard event. It highlights meaningful weather divergence across monitored cities. The stored event uses `city = "REGIONAL"`, which also enables filtering with `/events?city=REGIONAL`.

Key idea: this event tracks cross-city divergence, not danger in a single city.

## Cooldown Design

Cooldowns reduce alert fatigue. Without them, the same event could repeat every cycle during a persistent pattern.

| Event | Cooldown | Why |
|---|---:|---|
| RapidTemperatureDrop | 3 hours | Rapid changes can recur; repeated short-window alerts would be noisy |
| WindEscalation | 3 hours | Wind can shift quickly, so shorter suppression is appropriate |
| FreezeThawRisk | 6 hours | Freeze/thaw patterns usually evolve more slowly |
| CrossCityTemperatureSpread | 6 hours | Regional spread often persists for several hours |

Cooldown is based on `observed_at` (not `created_at`) so suppression follows weather time, not ingestion time.

For a new event with `observed_at = 2026-05-30 16:00` and a 3-hour cooldown, the
system queries:
 
```sql
SELECT * FROM weather_events
WHERE city = 'Ottawa'
  AND event_type = 'RapidTemperatureDrop'
  AND observed_at >= '2026-05-30 13:00'
```
 
If a matching row exists, the event is suppressed. No new row is created.

## Polling Interval

The poller runs every `15 minutes`. Open-Meteo updates hourly, so this is frequent enough to pick up new hourly data quickly while staying lightweight.

Why `15 minutes`:
1. Detects new hourly data soon after it appears.
2. Avoids unnecessary API load.
3. Shows visible runtime activity during short reviewer sessions.
4. Four requests per city per hour (12 in total) is negligible load on a free API with no rate limits.

Duplicate control via `(city, observed_at)` means frequent polling does not create duplicate readings or duplicate detector runs.

Flow:

```text
Poll Open-Meteo every 15 minutes
        ↓
Fetch latest reading for each city
        ↓
Check if (city, observed_at) already exists
        ↓
If duplicate: skip insert and skip event detection
        ↓
If new: insert reading, commit, then run event detection
```

## How Unit Tests Verify the Logic

Unit tests use controlled synthetic readings (no live Open-Meteo dependency) so detector behavior is deterministic.

Implemented positive vs negative cases:

| Detector | Positive test implemented | Negative test implemented |
|---|---|---|
| RapidTemperatureDrop | `12.0°C → 5.0°C` within 3 hours fires | `12.0°C → 8.5°C` does not fire |
| FreezeThawRisk | Ottawa crosses `1.5°C → -0.5°C` and fires | Ottawa `3.0°C → 2.0°C` does not fire |
| FreezeThawRisk scope | N/A | Vancouver crossing `1.5°C → -0.5°C` does not fire (out of scope) |
| WindEscalation | Consecutive jump `18.0 → 40.0 km/h` fires | `20.0 → 32.0 km/h` does not fire (jump below 20 and absolute below 50) |
| CrossCityTemperatureSpread | Ottawa `2°C`, Toronto `5°C`, Vancouver `16°C` fires | Ottawa `9°C`, Toronto `11°C`, Vancouver `14°C` does not fire |

The negative cases are as important as the positives. They prove detectors are selective and avoid reporting normal variation as notable events.