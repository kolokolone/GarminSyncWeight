"""Application configuration via environment variables.

Uses pydantic-settings to load from .env or environment.
Secrets (client_secret, tokens) are never logged or exposed in status.
"""

from functools import lru_cache
from pathlib import Path
from shlex import split
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # ─── Withings ─────────────────────────────────────────────
    withings_client_id: str = ""
    withings_client_secret: str = ""
    withings_redirect_uri: str = "http://127.0.0.1:8010/api/withings/auth/callback"
    withings_scope: str = "user.metrics"

    # ─── Application ──────────────────────────────────────────
    app_base_url: str = "http://127.0.0.1:8010"
    app_host: str = "127.0.0.1"
    app_port: int = 8010
    app_timezone: str = "Europe/Paris"
    user_height_m: float | None = None

    # ─── Garmin authentication / Taxuspt garmin_mcp ───────────
    garmin_mcp_source: str = "git+https://github.com/Taxuspt/garmin_mcp"
    garmin_token_dir: Path = Field(default=Path.home() / ".garminconnect")
    garmin_auth_command: str = (
        "uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp-auth"
    )
    garmin_verify_command: str = (
        "uvx --python 3.12 --from git+https://github.com/Taxuspt/garmin_mcp "
        "garmin-mcp-auth --verify"
    )
    garmin_auth_timeout_seconds: int = 60
    garmin_verify_timeout_seconds: int = 20

    # ─── Paths ────────────────────────────────────────────────
    data_dir: Path = Field(default=Path("./data"))
    log_dir: Path = Field(default=Path("./logs"))
    runtime_dir: Path = Field(default=Path("./runtime"))

    # ─── Sync behaviour ───────────────────────────────────────
    sync_requires_active_connections: bool = True
    admin_api_token: str = ""

    # ─── Anti-duplicate thresholds ────────────────────────────
    weight_duplicate_epsilon_kg: float = 0.05
    weight_conflict_epsilon_kg: float = 0.2
    garmin_lookback_days: int = 7
    garmin_lookahead_days: int = 1
    withings_per_day_strategy: Literal[
        "latest_per_day", "earliest_per_day", "all_if_distinct"
    ] = "latest_per_day"

    # ─── Logging ──────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: Literal["jsonl", "text"] = "jsonl"

    # ─── Version ──────────────────────────────────────────────
    app_version: str = "0.3.3"

    @field_validator("app_host")
    @classmethod
    def require_localhost_by_default(cls, value: str) -> str:
        if value not in ("127.0.0.1", "0.0.0.0"):
            raise ValueError("APP_HOST must be 127.0.0.1 or 0.0.0.0")
        return value

    @property
    def resolved_data_dir(self) -> Path:
        p = self.data_dir
        return p if p.is_absolute() else (Path.cwd() / p).resolve()

    @property
    def resolved_log_dir(self) -> Path:
        p = self.log_dir
        return p if p.is_absolute() else (Path.cwd() / p).resolve()

    @property
    def resolved_runtime_dir(self) -> Path:
        p = self.runtime_dir
        return p if p.is_absolute() else (Path.cwd() / p).resolve()

    @property
    def reports_dir(self) -> Path:
        return self.resolved_runtime_dir / "reports"

    @property
    def garmin_token_path(self) -> Path:
        p = self.garmin_token_dir.expanduser()
        return p if p.is_absolute() else (Path.cwd() / p).resolve()

    @property
    def garmin_auth_args(self) -> list[str]:
        return split(self.garmin_auth_command)

    @property
    def garmin_verify_args(self) -> list[str]:
        return split(self.garmin_verify_command)

    def ensure_directories(self) -> None:
        dirs = (
            self.resolved_data_dir, self.resolved_log_dir,
            self.resolved_runtime_dir, self.reports_dir,
        )
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
