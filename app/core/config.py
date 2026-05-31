import json
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "WatchAgent Weather Monitor"
    database_url: str
    app_version: str = "1.0.0"
    allowed_cities: Annotated[tuple[str, ...], NoDecode] = (
        "Ottawa",
        "Toronto",
        "Vancouver",
    )
    poller_enabled: bool = True
    poll_interval_seconds: int = Field(default=900, ge=1)

    @field_validator("allowed_cities", mode="before")
    @classmethod
    def parse_allowed_cities(cls, value: object) -> object:
        # Accept comma-separated values in .env while still supporting JSON/tuple input.
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return ("Ottawa", "Toronto", "Vancouver")

            # If user provides JSON in env, let pydantic handle list/tuple shape.
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return tuple(str(item).strip() for item in parsed if str(item).strip())
                except json.JSONDecodeError:
                    pass

            # Fallback: comma-separated format, e.g. ALLOWED_CITIES=Ottawa,Toronto,Vancouver
            return tuple(part.strip() for part in raw.split(",") if part.strip())

        return value


settings = Settings()