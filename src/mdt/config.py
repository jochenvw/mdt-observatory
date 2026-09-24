from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MDT_", extra="ignore")

    db_path: str = "data/mdt.db"
    storage_backend: Literal["sqlite", "azure_blob"] = "sqlite"
    blob_account_url: str = ""
    blob_container: str = "mdt-state"
    presenter_token: str = ""
    step_delay: float = Field(default=0.65, ge=0, le=5)
    secure_cookie: bool = False
    max_meetings: int = Field(default=100, ge=1, le=10000)
    azure_max_concurrent_roles: int = Field(default=3, ge=1, le=7)
    azure_request_interval_seconds: float = Field(default=20, ge=0, le=60, allow_inf_nan=False)
    elevenlabs_api_key: str = ""
    elevenlabs_base_url: str = "https://api.elevenlabs.io/v1"
    elevenlabs_model_id: str = "eleven_multilingual_v2"
    # Smallest matched subgroup that may be described; smaller cohorts are suppressed.
    cohort_minimum_subgroup: int = Field(default=15, ge=5, le=500)
