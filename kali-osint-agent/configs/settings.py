from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProxyMode(str, Enum):
    STEALTH = "stealth"
    FAST = "fast"
    DIRECT = "direct"
    ROTATING = "rotating"
    WHONIX = "whonix"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── vLLM Local Instance ──────────────────────────────────────────────
    vllm_base_url: str = "http://192.168.1.100:8000/v1"
    vllm_model: str = "nvidia/Nemotron-Mini-4B-Instruct"
    vllm_api_key: str = "not-needed"

    # ── OpenRouter (Cloud Fallback) ──────────────────────────────────────
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "nvidia/nemotron-super"

    # ── OSINT APIs ───────────────────────────────────────────────────────
    shodan_api_key: str = ""
    censys_api_id: str = ""
    censys_api_secret: str = ""

    # ── Telegram Bot ─────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""

    # ── PostgreSQL ───────────────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "kali_osint"
    postgres_user: str = "osint_agent"
    postgres_password: str = "changeme-postgres-password"
    database_url: str = "postgresql+asyncpg://osint_agent:changeme-postgres-password@localhost:5432/kali_osint"

    # ── Neo4j ────────────────────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "changeme-neo4j-password"

    # ── Redis ────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── OPSEC / Proxy Configuration ──────────────────────────────────────
    tor_socks_port: int = 9050
    tor_control_port: int = 9051
    tor_control_password: str = "changeme-tor-password"
    proxy_mode: ProxyMode = ProxyMode.STEALTH
    socks5_proxy_list: str = "socks5://127.0.0.1:1080,socks5://127.0.0.1:1081"
    whonix_gateway_ip: str = "10.152.152.10"
    whonix_socks_port: int = 9050

    # ── FastAPI Server ───────────────────────────────────────────────────
    fastapi_host: str = "0.0.0.0"
    fastapi_port: int = 8080
    jwt_secret: str = "changeme-jwt-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # ── General ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    environment: Environment = Environment.DEVELOPMENT

    # ── Computed Properties ──────────────────────────────────────────────

    @property
    def socks5_proxies(self) -> list[str]:
        """Parse the comma-separated proxy list into individual proxy URLs."""
        if not self.socks5_proxy_list:
            return []
        return [p.strip() for p in self.socks5_proxy_list.split(",") if p.strip()]

    @property
    def tor_socks_url(self) -> str:
        """Construct the Tor SOCKS5 proxy URL."""
        return f"socks5://127.0.0.1:{self.tor_socks_port}"

    @property
    def whonix_socks_url(self) -> str:
        """Construct the Whonix SOCKS5 proxy URL."""
        return f"socks5://{self.whonix_gateway_ip}:{self.whonix_socks_port}"


settings = Settings()
