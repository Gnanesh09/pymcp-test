from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Umon Commerce API"
    environment: str = "development"
    api_prefix: str = "/api"

    mongodb_uri: str
    mongodb_db: str = "umon"

    clerk_jwks_url: str
    clerk_issuer: str
    clerk_authorized_party: str | None = None

    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    razorpay_currency: str = "INR"

    merchant_id: str = "umon-mart"
    merchant_name: str = "Umon Mart"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
