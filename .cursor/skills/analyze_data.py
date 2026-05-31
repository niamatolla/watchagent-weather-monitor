#!/usr/bin/env python3
"""
Skill: analyze_data.py
======================
A Cursor-invokable data analysis tool for the WatchAgent database.

Usage (from repo root):
	python .cursor/skills/analyze_data.py --question "Which city had the most events?"
	python .cursor/skills/analyze_data.py --question "Show temperature trends for Ottawa"
	python .cursor/skills/analyze_data.py --question "What events fired in the last 24 hours?"
	python .cursor/skills/analyze_data.py --question "Compare wind speeds across cities"
	python .cursor/skills/analyze_data.py --summary

This script is wired to the actual project schema:
- weather_readings (observed_at, temperature_2m, ...)
- weather_events (event_type, severity, observed_at, description, ...)
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Resolve project root from this file location:
# .cursor/skills/analyze_data.py -> project root is parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sqlite_path_from_url(database_url: str | None) -> Path | None:
	if not database_url:
		return None
	if not database_url.startswith("sqlite:///"):
		return None
	raw = database_url.removeprefix("sqlite:///")
	if not raw:
		return None
	return Path(raw)


def _database_url_from_dotenv(dotenv_path: Path) -> str | None:
	if not dotenv_path.exists():
		return None
	for line in dotenv_path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		if key.strip() == "DATABASE_URL":
			return value.strip().strip('"').strip("'")
	return None


def _resolve_candidate(path_str: str) -> Path:
	path = Path(path_str)
	if path.is_absolute():
		return path
	return PROJECT_ROOT / path


def _candidate_db_paths() -> list[Path]:
	env_db_path = os.getenv("DB_PATH")
	env_db_url = os.getenv("DATABASE_URL")
	dotenv_db_url = _database_url_from_dotenv(Path(".env"))

	candidates: list[Path] = []

	if env_db_path:
		candidates.append(_resolve_candidate(env_db_path))

	for url in (env_db_url, dotenv_db_url):
		maybe = _sqlite_path_from_url(url)
		if maybe:
			candidates.append(_resolve_candidate(str(maybe)))

	# Fallbacks for local/dev layouts.
	candidates.extend(
		[
			PROJECT_ROOT / "data/weather.db",
			PROJECT_ROOT / "data/watchagent.db",
			PROJECT_ROOT / "watchagent.db",
			Path("/data/weather.db"),
			Path("/data/watchagent.db"),
		]
	)
	return candidates


def find_db() -> Path:
	tried = []
	for p in _candidate_db_paths():
		tried.append(str(p))
		if p.exists():
			return p
	print("ERROR: Could not locate the database file.")
	print("Tried:", tried)
	print("Set DB_PATH or DATABASE_URL, or create ./data/weather.db.")
	sys.exit(1)


def connect(db_path: Path) -> sqlite3.Connection:
	conn = sqlite3.connect(str(db_path))
	conn.row_factory = sqlite3.Row
	return conn


def _extract_city(text: str) -> str | None:
	for city in ("ottawa", "toronto", "vancouver", "regional"):
		if city in text:
			return city.upper() if city == "regional" else city.capitalize()
	return None


def summary(conn: sqlite3.Connection) -> str:
	lines: list[str] = []

	r = conn.execute("SELECT COUNT(*) as n FROM weather_readings").fetchone()
	e = conn.execute("SELECT COUNT(*) as n FROM weather_events").fetchone()
	lines.append("=" * 60)
	lines.append("  WatchAgent Data Summary")
	lines.append("=" * 60)
	lines.append(f"  Total readings : {r['n']}")
	lines.append(f"  Total events   : {e['n']}")
	lines.append("")

	lines.append("Readings per city:")
	rows = conn.execute(
		"SELECT city, COUNT(*) as n, MIN(observed_at) as first, MAX(observed_at) as last "
		"FROM weather_readings GROUP BY city ORDER BY city"
	).fetchall()
	if rows:
		for row in rows:
			lines.append(
				f"  {row['city']:<12} {row['n']:>5} readings  ({row['first']} -> {row['last']})"
			)
	else:
		lines.append("  (no readings recorded yet)")
	lines.append("")

	lines.append("Temperature stats (C):")
	rows = conn.execute(
		"SELECT city, "
		"  ROUND(MIN(temperature_2m),1) as t_min, "
		"  ROUND(MAX(temperature_2m),1) as t_max, "
		"  ROUND(AVG(temperature_2m),1) as t_avg "
		"FROM weather_readings GROUP BY city ORDER BY city"
	).fetchall()
	if rows:
		for row in rows:
			lines.append(
				f"  {row['city']:<12} min={row['t_min']:>6}  max={row['t_max']:>6}  avg={row['t_avg']:>6}"
			)
	else:
		lines.append("  (no readings recorded yet)")
	lines.append("")

	lines.append("Wind speed stats (km/h):")
	rows = conn.execute(
		"SELECT city, "
		"  ROUND(MAX(wind_speed_10m),1) as w_max, "
		"  ROUND(AVG(wind_speed_10m),1) as w_avg "
		"FROM weather_readings GROUP BY city ORDER BY city"
	).fetchall()
	if rows:
		for row in rows:
			lines.append(f"  {row['city']:<12} max={row['w_max']:>6}  avg={row['w_avg']:>6}")
	else:
		lines.append("  (no readings recorded yet)")
	lines.append("")

	lines.append("Events by type and city:")
	rows = conn.execute(
		"SELECT city, event_type, severity, COUNT(*) as n "
		"FROM weather_events GROUP BY city, event_type, severity "
		"ORDER BY city, n DESC"
	).fetchall()
	if rows:
		for row in rows:
			lines.append(
				f"  {row['city']:<12} {row['event_type']:<30} {row['severity']:<13} x {row['n']}"
			)
	else:
		lines.append("  (no events recorded yet)")
	lines.append("")

	lines.append("5 most recent events:")
	rows = conn.execute(
		"SELECT city, event_type, severity, observed_at, description "
		"FROM weather_events ORDER BY observed_at DESC LIMIT 5"
	).fetchall()
	if rows:
		for row in rows:
			lines.append(
				f"  [{row['observed_at']}] {row['city']} | {row['event_type']} ({row['severity']})"
			)
			lines.append(f"    -> {row['description']}")
	else:
		lines.append("  (none)")

	lines.append("=" * 60)
	return "\n".join(lines)


def answer_question(conn: sqlite3.Connection, question: str) -> str:
	q = question.lower()

	if "most events" in q or "most event" in q:
		rows = conn.execute(
			"SELECT city, COUNT(*) as n FROM weather_events GROUP BY city ORDER BY n DESC"
		).fetchall()
		if not rows:
			return "No events recorded yet."
		lines = ["Events per city (most to least):"]
		for row in rows:
			lines.append(f"  {row['city']}: {row['n']} events")
		return "\n".join(lines)

	if "temperature" in q and "trend" in q:
		city = _extract_city(q)
		if city:
			rows = conn.execute(
				"SELECT city, observed_at, temperature_2m, apparent_temperature "
				"FROM weather_readings WHERE city = ? "
				"ORDER BY observed_at DESC LIMIT 24",
				(city,),
			).fetchall()
		else:
			rows = conn.execute(
				"SELECT city, observed_at, temperature_2m, apparent_temperature "
				"FROM weather_readings ORDER BY observed_at DESC LIMIT 24"
			).fetchall()

		if not rows:
			return f"No readings found{' for ' + city if city else ''}."

		lines = [
			f"Last {len(rows)} readings{' for ' + city if city else ''} (most recent first):"
		]
		for row in rows:
			lines.append(
				f"  {row['observed_at']}  {row['city']:<12} "
				f"temp={row['temperature_2m']:>6.1f}C  "
				f"feels={row['apparent_temperature']:>6.1f}C"
			)
		return "\n".join(lines)

	if "last 24" in q or "24 hour" in q or "recent events" in q:
		cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(tzinfo=None).isoformat()
		rows = conn.execute(
			"SELECT city, event_type, severity, observed_at, description "
			"FROM weather_events WHERE observed_at >= ? ORDER BY observed_at DESC",
			(cutoff,),
		).fetchall()
		if not rows:
			return "No events in the last 24 hours."
		lines = [f"{len(rows)} event(s) in the last 24 hours:"]
		for row in rows:
			lines.append(
				f"  [{row['observed_at']}] {row['city']} | {row['event_type']} ({row['severity']})"
			)
			lines.append(f"    {row['description']}")
		return "\n".join(lines)

	if "wind" in q and ("compare" in q or "across" in q or "cities" in q):
		rows = conn.execute(
			"SELECT city, "
			"  ROUND(MAX(wind_speed_10m),1) as w_max, "
			"  ROUND(AVG(wind_speed_10m),2) as w_avg, "
			"  ROUND(MIN(wind_speed_10m),1) as w_min "
			"FROM weather_readings GROUP BY city ORDER BY w_avg DESC"
		).fetchall()
		if not rows:
			return "No readings found."
		lines = ["Wind speed comparison across cities (km/h):"]
		for row in rows:
			lines.append(
				f"  {row['city']:<12}  avg={row['w_avg']:>6}  max={row['w_max']:>6}  min={row['w_min']:>6}"
			)
		return "\n".join(lines)

	if "precipitation" in q or "rain" in q or "precip" in q:
		city = _extract_city(q)
		if city:
			rows = conn.execute(
				"SELECT city, "
				"  ROUND(MAX(precipitation),1) as p_max, "
				"  ROUND(SUM(precipitation),1) as p_total, "
				"  SUM(CASE WHEN precipitation > 0 THEN 1 ELSE 0 END) as rainy_hours "
				"FROM weather_readings WHERE city = ? GROUP BY city",
				(city,),
			).fetchall()
		else:
			rows = conn.execute(
				"SELECT city, "
				"  ROUND(MAX(precipitation),1) as p_max, "
				"  ROUND(SUM(precipitation),1) as p_total, "
				"  SUM(CASE WHEN precipitation > 0 THEN 1 ELSE 0 END) as rainy_hours "
				"FROM weather_readings GROUP BY city ORDER BY p_total DESC"
			).fetchall()

		if not rows:
			return "No readings found."

		lines = ["Precipitation summary (mm/hr readings):"]
		for row in rows:
			lines.append(
				f"  {row['city']:<12}  max_hourly={row['p_max']:>5}mm  "
				f"total_sum={row['p_total']:>7}mm  rainy_hours={row['rainy_hours']}"
			)
		return "\n".join(lines)

	if ("spread" in q or "difference" in q or "diverge" in q) and "temperature" in q:
		rows = conn.execute(
			"SELECT observed_at, "
			"  MAX(temperature_2m) - MIN(temperature_2m) as spread, "
			"  GROUP_CONCAT(city || '=' || ROUND(temperature_2m,1)) as cities "
			"FROM weather_readings GROUP BY observed_at "
			"HAVING COUNT(DISTINCT city) = 3 "
			"ORDER BY spread DESC LIMIT 10"
		).fetchall()
		if not rows:
			return "Not enough data to compute cross-city spreads yet."
		lines = ["Top 10 timestamps with highest cross-city temperature spread:"]
		for row in rows:
			lines.append(
				f"  {row['observed_at']}  spread={row['spread']:.1f}C  ({row['cities']})"
			)
		return "\n".join(lines)

	return (
		"I couldn't match a specific query pattern. Here's the full summary instead:\n\n"
		+ summary(conn)
	)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Analyze WatchAgent weather data from the SQLite database."
	)
	parser.add_argument(
		"--question",
		"-q",
		type=str,
		help='Natural language question, e.g. "Which city had the most events?"',
	)
	parser.add_argument(
		"--summary",
		"-s",
		action="store_true",
		help="Print a full data summary report.",
	)
	parser.add_argument(
		"--db",
		type=str,
		help="Path to the SQLite database file (overrides DB_PATH and DATABASE_URL).",
	)
	args = parser.parse_args()

	if args.db:
		db_path = Path(args.db)
		if not db_path.exists():
			print(f"ERROR: Database not found at {db_path}")
			sys.exit(1)
	else:
		db_path = find_db()

	print(f"[analyze_data] Using database: {db_path}")
	print(f"[analyze_data] Queried at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

	conn = connect(db_path)
	try:
		if args.summary or not args.question:
			print(summary(conn))
		else:
			print(answer_question(conn, args.question))
	finally:
		conn.close()


if __name__ == "__main__":
	main()
