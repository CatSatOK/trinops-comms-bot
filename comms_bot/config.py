"""Application settings.

Every company-specific or environment-specific value lives in `.env`
(see `.env.example`). Nothing client-identifying is hardcoded.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    demo_mode: bool = True

    # Protects staff/admin endpoints when demo_mode is false (sent as X-API-Key).
    admin_api_key: str = ""

    # Public chat WebSocket guards. The chat endpoint is unauthenticated by
    # design (any visitor can talk to the bot), so it gets its own limits:
    #  - rate limit per caller IP (messages per minute); 0 disables it. This is
    #    the main guard on Anthropic spend, since the LLM fallback runs per message.
    #  - hard cap on a single message length (chars); longer messages are
    #    truncated server-side regardless of the widget's own maxlength.
    #  - Origin allowlist: when set, the browser Origin header must match one of
    #    these or the connection is refused. Empty (the demo default) allows any
    #    origin so the embeddable widget keeps working anywhere.
    chat_rate_limit_per_minute: int = 30
    max_message_chars: int = 1000
    allowed_origins: list[str] = []

    database_url: str = "sqlite:///./data/comms.db"

    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"

    # Knowledge base: faq.json is written by the scraper and read by the
    # answer engine. faq_source is the page the scraper points at — a URL
    # for a real client site, a bundled HTML file in demo mode.
    faq_file: str = "knowledge_base/faq.json"
    faq_source: str = "demo/faq-page.html"
    faq_refresh_hours: int = 24  # 0 disables the scheduled re-scrape

    # rapidfuzz token_set_ratio score (0-100) a question must reach to be
    # answered straight from the FAQ with no API call
    fuzzy_match_threshold: int = 80
    llm_max_context_pairs: int = 40

    # Phrases that hand the conversation to a human. Matched on word
    # boundaries, case-insensitive. Override with a JSON list.
    escalation_keywords: list[str] = [
        "speak to someone",
        "speak to a person",
        "talk to someone",
        "talk to a person",
        "human",
        "agent",
        "real person",
        "complaint",
    ]

    company_name: str = "Company A"
    company_email: str = "hello@example.com"
    cs_team_email: str = "support@example.com"

    google_credentials_file: str = "credentials.json"
    google_token_file: str = "token.json"

    outbox_dir: str = "data/outbox"
    seed_conversations_file: str = "seed/conversations.json"

    def ensure_dirs(self) -> None:
        Path(self.outbox_dir).mkdir(parents=True, exist_ok=True)
        Path(self.faq_file).parent.mkdir(parents=True, exist_ok=True)
        db_path = self.database_url.removeprefix("sqlite:///")
        if db_path != self.database_url:  # only for sqlite URLs
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
