from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, sourced from environment variables.

    Matches docker/.env.example. No secret ever gets a hardcoded default
    that would be safe to ship — POSTGRES_PASSWORD/JWT_SECRET defaults
    below are for local dev only and must be overridden in any shared
    environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "linkintel"
    postgres_password: str = "linkintel"
    postgres_db: str = "linkintel"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    redis_host: str = "localhost"
    redis_port: int = 6379

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # AnthropicSearchProvider (app/engines/search/anthropic_provider.py),
    # the search backend behind Phase 7 (search-pattern discovery) and
    # Phase 18 (GEO citation checking). None lets the Anthropic SDK
    # resolve credentials itself (env var, `ant auth login` profile, ...)
    # -- see that module's docstring. Never hardcode a key here.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"

    crawler_user_agent: str = "LinkIntelBot/0.1 (+https://example.invalid/bot)"
    crawler_max_pages_per_job: int = 50
    crawler_respect_robots_txt: bool = True

    # Only needed when Playwright's own browser-revision resolution can't
    # find a matching install (e.g. a pre-provisioned browser cache with a
    # different revision than this Playwright version expects). Leave
    # unset in normal deployments where `playwright install chromium` was
    # run against this exact Playwright version.
    playwright_executable_path: str | None = None

    # Chromium's sandbox needs kernel namespace privileges that aren't
    # available when the browser is launched as root (common in minimal
    # container images/CI runners) -- Playwright/Puppeteer's own guidance
    # for that case is --no-sandbox. Leave False by default; only flip it
    # on for a root/CI environment, and prefer running the crawler as a
    # non-root user instead where possible.
    playwright_no_sandbox: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
