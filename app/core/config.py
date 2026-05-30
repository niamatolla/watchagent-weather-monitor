from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "WatchAgent Weather Monitor"
    database_url: str = "sqlite:///data/weather.db"
    app_version: str = "1.0.0"


settings = Settings()