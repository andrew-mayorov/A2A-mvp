from __future__ import annotations

import tomllib
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RankingConfig(BaseModel):
    price: Decimal
    delivery: Decimal
    warranty: Decimal
    risk: Decimal
    payment_terms: Decimal
    version: str

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> RankingConfig:
        weights = [
            self.price,
            self.delivery,
            self.warranty,
            self.risk,
            self.payment_terms,
        ]
        if any(weight < 0 for weight in weights) or sum(weights) != Decimal("1"):
            raise ValueError("Ranking weights must be non-negative and sum to 1")
        return self


class DemoProfile(BaseModel):
    name: str
    production_like: bool
    default_currency: str = Field(pattern=r"^[A-Z]{3}$")
    default_category: str
    minimum_quotes: int = Field(ge=2)
    buyer_agent_id: str
    buyer_organization_id: str
    approver_subject: str
    delivery_city: str
    delivery_days: int = Field(gt=0)
    mandate_validity_hours: int = Field(gt=0)
    default_sku: str
    default_product_name: str
    default_quantity: int = Field(gt=0)
    default_maximum_amount: Decimal = Field(gt=0)
    mandate_version: str
    mandate_signature: str
    mandate_issuer: str
    allowed_actions: list[str]
    forbidden_actions: list[str]
    approval_role: str


class NetworkConfig(BaseModel):
    allowed_schemes: list[str]
    allowed_ports: list[int]
    allow_private_networks: bool
    max_response_bytes: int = Field(gt=0)
    connect_timeout_seconds: float = Field(gt=0)
    read_timeout_seconds: float = Field(gt=0)
    max_attempts: int = Field(gt=0)


class SecurityConfig(BaseModel):
    signature_algorithm: str
    key_provider: str
    keys_directory: str
    nonce_ttl_seconds: int = Field(gt=0)
    financial_kill_switch: bool


class OidcConfig(BaseModel):
    issuer: str
    audience: str
    required_approval_role: str
    required_admin_role: str


class SupplierSeed(BaseModel):
    agent_id: str
    organization_id: str
    name: str
    endpoint: str
    bank_binding_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    catalog_file: str
    risk: Decimal = Field(ge=0, le=1)
    risk_tier: str
    status: str
    categories: list[str]


class RuntimeConfig(BaseModel):
    profile: DemoProfile
    ranking: RankingConfig
    network: NetworkConfig
    security: SecurityConfig
    oidc: OidcConfig
    suppliers: list[SupplierSeed]

    @classmethod
    def load(cls, path: str | Path) -> RuntimeConfig:
        with Path(path).open("rb") as stream:
            return cls.model_validate(tomllib.load(stream))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Trusted A2A Procurement MVP"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    public_url: str | None = None
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///./data/a2a.db"
    runtime_config_file: str = "config/demo.toml"
    keys_directory: str | None = None
    supplier_mode: Literal["embedded", "remote"] = "embedded"
    supplier_id: str | None = None
    trust_api_url: str | None = None
    demo_identity_enabled: bool = False
    demo_identity_header: str = "X-Demo-User"

    llm_provider: Literal["disabled", "openrouter", "gigachat"] = "disabled"
    llm_timeout_seconds: float = Field(default=8.0, gt=0)
    llm_max_attempts: int = Field(default=2, gt=0)
    llm_max_tokens: int = Field(default=800, gt=0)
    llm_temperature: float = Field(default=0.0, ge=0, le=2)
    openrouter_api_key: SecretStr | None = None
    openrouter_model: str | None = None
    openrouter_base_url: str | None = None
    openrouter_allowed_models: str = ""
    openrouter_allowed_providers: str = ""
    openrouter_app_url: str | None = None
    openrouter_app_title: str | None = None
    openrouter_data_retention: Literal["deny", "allow"] = "deny"
    gigachat_credentials: SecretStr | None = None
    gigachat_access_token: SecretStr | None = None
    gigachat_model: str | None = None
    gigachat_scope: str | None = None
    gigachat_oauth_url: str | None = None
    gigachat_base_url: str | None = None
    gigachat_ca_bundle_file: str | None = None
    gigachat_verify_ssl_certs: bool = True

    @property
    def runtime(self) -> RuntimeConfig:
        return RuntimeConfig.load(self.runtime_config_file)

    @property
    def llm_ready(self) -> bool:
        if self.llm_provider == "openrouter":
            allowed = self.allowed_openrouter_models
            return bool(
                self.openrouter_api_key
                and self.openrouter_api_key.get_secret_value()
                and self.openrouter_model
                and self.openrouter_model in allowed
                and self.allowed_openrouter_providers
            )
        if self.llm_provider == "gigachat":
            credentials_present = bool(
                self.gigachat_credentials and self.gigachat_credentials.get_secret_value()
            )
            token_present = bool(
                self.gigachat_access_token and self.gigachat_access_token.get_secret_value()
            )
            return bool((credentials_present or token_present) and self.gigachat_model)
        return False

    @property
    def allowed_openrouter_models(self) -> set[str]:
        return {item.strip() for item in self.openrouter_allowed_models.split(",") if item.strip()}

    @property
    def allowed_openrouter_providers(self) -> list[str]:
        return [
            item.strip() for item in self.openrouter_allowed_providers.split(",") if item.strip()
        ]

    @property
    def supplier_seeds(self) -> list[SupplierSeed]:
        return self.runtime.suppliers

    @property
    def effective_keys_directory(self) -> str:
        return self.keys_directory or self.runtime.security.keys_directory


@lru_cache
def get_settings() -> Settings:
    return Settings()
