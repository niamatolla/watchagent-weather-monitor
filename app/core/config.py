from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WatchAgent Weather Monitor"
    database_url: str = "sqlite:///data/weather.db"
    app_version: str = "1.0.0"
    allowed_cities: tuple[str, str, str] = ("Ottawa", "Toronto", "Vancouver")


settings = Settings()