"""Agent settings. Provider keys come from the environment and are never logged
or returned by the API."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # anthropic | openai | local (any OpenAI-compatible server, e.g. Ollama)
    AI_PROVIDER: str = "anthropic"
    # Empty uses the provider default; openai and local require a model name.
    AI_MODEL: str = ""
    ANTHROPIC_API_KEY: str = Field(default="", repr=False)
    OPENAI_API_KEY: str = Field(default="", repr=False)
    OPENAI_BASE_URL: str = ""
    LOCAL_AI_BASE_URL: str = ""
    LOCAL_AI_API_KEY: str = Field(default="local", repr=False)

    PROMETHEUS_URL: str = "http://prometheus:9090"
    # Live diagnostics through the MCP servers as principal ui-agent. Empty
    # token: Prometheus tools only. "env=url" pairs, comma-separated.
    AGENT_MCP_TOKEN: str = Field(default="", repr=False)
    AGENT_MCP_SERVERS: str = "development=http://data-eyes-mcp-dev:8080/mcp"
    AI_MAX_TOOL_CALLS: int = Field(default=8, ge=1, le=20)
    AI_MAX_TOKENS: int = Field(default=2000, ge=256, le=16000)
    AI_TIMEOUT_SECONDS: float = Field(default=120, gt=0)
    AI_MAX_CONCURRENT_ASKS: int = Field(default=4, ge=1, le=32)
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore", hide_input_in_errors=True)  # the repository .env


settings = Settings()

DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}
PROVIDER_LABELS = {"anthropic": "Anthropic", "openai": "OpenAI", "local": "Local model"}


def model_name() -> str:
    return settings.AI_MODEL or DEFAULT_MODELS.get(settings.AI_PROVIDER, "")


def status() -> dict:
    """Provider, model and whether the agent can answer; no secrets."""
    provider = settings.AI_PROVIDER
    reason = None
    if provider not in PROVIDER_LABELS:
        reason = "AI_PROVIDER must be anthropic, openai, or local."
    elif provider == "anthropic" and not settings.ANTHROPIC_API_KEY:
        reason = "ANTHROPIC_API_KEY is not configured."
    elif provider == "openai" and not settings.OPENAI_API_KEY:
        reason = "OPENAI_API_KEY is not configured."
    elif provider == "local" and not settings.LOCAL_AI_BASE_URL:
        reason = "LOCAL_AI_BASE_URL is not configured."
    elif not model_name():
        reason = "AI_MODEL is required for this provider."
    return {
        "provider": provider,
        "provider_label": PROVIDER_LABELS.get(provider, provider),
        "model": model_name(),
        "base_url": settings.LOCAL_AI_BASE_URL if provider == "local" else (settings.OPENAI_BASE_URL or None if provider == "openai" else None),
        "configured": reason is None,
        "live_diagnostics": bool(settings.AGENT_MCP_TOKEN),
        "reason": reason,
    }
