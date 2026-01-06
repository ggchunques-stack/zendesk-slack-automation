from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    ENV: str = "dev"
    SLACK_WEBHOOK_URL: str | None = None
    ZENDESK_SUBDOMAIN: str | None = None
    ZENDESK_EMAIL: str | None = None
    ZENDESK_API_TOKEN: str | None = None
    ZENDESK_WEBHOOK_SECRET: str | None = None
    ZENDESK_DRY_RUN: bool = True
    ZENDESK_ADD_INTERNAL_COMMENT: bool = False
    DEBUG_WEBHOOK_SIGNATURE: bool = False
    DEBUG_FORCE_NOTIFY: bool = False
    DATABASE_PATH: str = Field(default_factory=lambda: str(project_root() / "data.db"))
    MAPPING_PATH: str = Field(
        default_factory=lambda: str(project_root() / "config" / "mapping.json")
    )
    SIGNATURE_HEADER_CANDIDATES: list[str] = Field(
        default_factory=lambda: [
            "X-Zendesk-Webhook-Signature",
            "X-Zendesk-Signature",
            "X-Hub-Signature-256",
        ]
    )
    SIGNATURE_TIMESTAMP_HEADER: str = "X-Zendesk-Webhook-Signature-Timestamp"

    @field_validator("SIGNATURE_HEADER_CANDIDATES", mode="before")
    @classmethod
    def _split_signature_candidates(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            return [item for item in items if item]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
