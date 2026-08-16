from functools import lru_cache
from datetime import date
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    app_env: str
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    database_url: SecretStr
    cors_origins: str = ""
    esi_base_url: str = "https://esi.evetech.net"
    esi_compatibility_date: date = date(2026, 8, 13)
    esi_user_agent: str = "ITS-S-EVE-Industry/0.1"
    market_region_id: int = Field(default=10_000_002, gt=0)
    market_location_id: int = Field(default=60_003_760, gt=0)
    market_location_name: str = "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
    sde_latest_url: str = (
        "https://developers.eveonline.com/static-data/"
        "eve-online-static-data-latest-jsonl.zip"
    )
    sde_download_max_bytes: int = Field(
        default=2_147_483_648,
        gt=0,
    )

    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_cors_origins(self) -> tuple[str, ...]:
        configured = tuple(
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        )
        if configured:
            return tuple(dict.fromkeys(configured))
        if self.app_env.casefold() == "development":
            return (
                "http://127.0.0.1:5500",
                "http://localhost:5500",
            )
        return ()


@lru_cache
def get_settings() -> Settings:
    return Settings()
