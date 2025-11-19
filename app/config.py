from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    # Tell Pydantic Settings to load from .env
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",  
    )

    # Env vars: names must match your .env keys by default
    openweather_api_key: str = Field(f"{os.getenv('openweather_api_key', '')}")
    mongo_uri: str = Field(f"{os.getenv('mongo_uri', 'mongodb://localhost:27017')}")
    mongo_db: str = Field(f"{os.getenv('mongo_db', 'weather_health_db')}")
    ollama_base_url: str = Field(f"({os.getenv('ollama_base_url', 'http://localhost:11434')})")
    ollama_model: str = Field(f"{os.getenv('ollama_model', 'phi4-mini')}")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
