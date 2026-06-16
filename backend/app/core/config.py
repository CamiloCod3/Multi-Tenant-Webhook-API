# backend/app/core/config.py
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # Public/example URLs. Override these in .env for real deployments.
    public_base_url: str = Field(default="http://localhost:8000")
    dashboard_base_url: str = Field(default="http://localhost:3000")
    automation_base_url: str = Field(default="http://localhost:5678")

    # JWT / HMAC
    jwt_secret: str = Field(default="dev_jwt_secret_CHANGE_IN_PRODUCTION")
    jwt_expires_minutes: int = Field(default=60)
    hmac_secret: str = Field(default="dev_hmac_secret_CHANGE_IN_PRODUCTION")

    # CORS / security
    allowed_origins: str = Field(default="*")
    allowed_headers: str = Field(default="*")
    trusted_hosts: str = Field(default="*")

    # Database
    database_url: str = Field(default="postgresql+psycopg://webhook:devpass@db:5432/webhook_api")
    db_pool_size: int = Field(default=5)
    db_max_overflow: int = Field(default=5)
    db_pool_recycle: int = Field(default=1800)
    db_pool_timeout: int = Field(default=30)
    db_connect_timeout: int = Field(default=10)
    db_ssl_mode: str = Field(default="prefer")

    # Redis / observability
    redis_url: str = Field(default="redis://redis:6379/0")
    sentry_dsn: str = ""

    sentry_traces_sample_rate: float = 0.1
    sentry_profiles_sample_rate: float = 0.0

    # Metrics protection
    metrics_token: str = ""

    # Admin token for tenant management
    tenant_admin_token: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        v = (self.allowed_origins or "").strip()
        if v == "*" or v == "":
            return ["*"]
        return [item.strip() for item in v.split(",") if item.strip()]

    @property
    def allowed_headers_list(self) -> list[str]:
        v = (self.allowed_headers or "").strip()
        if v == "*" or v == "":
            return ["*"]
        return [item.strip() for item in v.split(",") if item.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        v = (self.trusted_hosts or "").strip()
        if v == "*" or v == "":
            return ["*"]
        return [item.strip() for item in v.split(",") if item.strip()]

    @model_validator(mode="after")
    def validate_production_secrets(self):
        if self.env != "production":
            return self

        dangerous_values = [
            "dev_jwt_secret_CHANGE_IN_PRODUCTION",
            "dev_hmac_secret_CHANGE_IN_PRODUCTION",
            "CHANGE_ME_SECRET",
            "CHANGE_ME_HMAC",
            "dev_secret_change_me",
            "dev_hmac_change_me",
        ]

        if self.jwt_secret in dangerous_values:
            raise ValueError(
                "PRODUCTION ERROR: jwt_secret is using default/development value! "
                "Generate a strong secret with: openssl rand -hex 32"
            )
        if len(self.jwt_secret) < 32:
            raise ValueError("jwt_secret must be at least 32 characters in production")

        if self.hmac_secret in dangerous_values:
            raise ValueError(
                "PRODUCTION ERROR: hmac_secret is using default/development value! "
                "Generate a strong secret with: openssl rand -hex 32"
            )
        if len(self.hmac_secret) < 32:
            raise ValueError("hmac_secret must be at least 32 characters in production")

        pb = (self.public_base_url or "").strip()
        if not pb.startswith("https://"):
            raise ValueError("public_base_url must start with https:// in production")
        if pb.endswith("/"):
            raise ValueError("public_base_url must NOT end with a trailing slash")

        import warnings

        if not self.metrics_token or len(self.metrics_token) < 16:
            warnings.warn(
                "metrics_token should be at least 16 characters in production. "
                "Generate with: openssl rand -hex 16"
            )

        if not self.tenant_admin_token or len(self.tenant_admin_token) < 16:
            warnings.warn(
                "tenant_admin_token should be at least 16 characters in production. "
                "Tenant creation will not work without it!"
            )

        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
