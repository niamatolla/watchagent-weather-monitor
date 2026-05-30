from datetime import datetime
import httpx


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# City coordinates (lat, lon)
CITY_COORDS: dict[str, tuple[float, float]] = {
	"Ottawa": (45.42, -75.69),
	"Toronto": (43.70, -79.42),
	"Vancouver": (49.25, -123.12),
}

CURRENT_FIELDS = (
	"temperature_2m,apparent_temperature,precipitation,"
	"wind_speed_10m,weather_code"
)


def fetch_current_weather(city: str) -> dict:
	"""Fetch current weather for a supported city and return normalized data"""
	city_name = _normalize_city_name(city)
	latitude, longitude = CITY_COORDS[city_name]

	params = {
		"latitude": latitude,
		"longitude": longitude,
		"current": CURRENT_FIELDS,
		"wind_speed_unit": "kmh",
		"timezone": "auto",
	}

	try:
		response = httpx.get(OPEN_METEO_URL, params=params, timeout=15.0)
		response.raise_for_status()
	except httpx.HTTPError as exc:
		raise RuntimeError(f"Open-Meteo request failed for {city_name}: {exc}") from exc

	payload = response.json()
	current = payload.get("current")
	if not current:
		raise RuntimeError(f"Open-Meteo response missing current data for {city_name}")

	try:
		observed_at = datetime.fromisoformat(current["time"])
	except (KeyError, ValueError) as exc:
		raise RuntimeError(
			f"Open-Meteo response has invalid current.time for {city_name}"
		) from exc

	try:
		return {
			"city": city_name,
			"observed_at": observed_at,
			"temperature_2m": float(current["temperature_2m"]),
			"apparent_temperature": float(current["apparent_temperature"]),
			"precipitation": float(current["precipitation"]),
			"wind_speed_10m": float(current["wind_speed_10m"]),
			"weather_code": int(current["weather_code"]),
		}
	except (KeyError, TypeError, ValueError) as exc:
		raise RuntimeError(
			f"Open-Meteo response missing required weather fields for {city_name}"
		) from exc


def _normalize_city_name(city: str) -> str:
	normalized_city = city.strip().lower()
	city_lookup = {known_city.lower(): known_city for known_city in CITY_COORDS}

	if normalized_city not in city_lookup:
		allowed = ", ".join(CITY_COORDS.keys())
		raise ValueError(f"Unsupported city '{city}'. Allowed cities: {allowed}")

	return city_lookup[normalized_city]
