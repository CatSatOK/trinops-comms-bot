import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comms_bot.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent

# Jinja templates and demo assets are loaded relative to the repo root
os.chdir(REPO_ROOT)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        demo_mode=True,
        anthropic_api_key="",
        outbox_dir=str(tmp_path / "outbox"),
        database_url=f"sqlite:///{tmp_path}/test.db",
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient on the real app, pointed at temp paths with no seed data."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("FAQ_FILE", str(tmp_path / "faq.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("FAQ_REFRESH_HOURS", "0")
    monkeypatch.setenv("SEED_CONVERSATIONS_FILE", str(tmp_path / "no-seed.json"))

    def _reset():
        import api.routes.chat as chat
        import comms_bot.claude_client as claude_client
        import comms_bot.database as database
        from comms_bot.config import get_settings

        get_settings.cache_clear()
        chat._chat_limiter.cache_clear()
        database._engine = None
        database._SessionLocal = None
        claude_client._engine = None

    _reset()
    from api.main import app

    with TestClient(app) as test_client:
        yield test_client

    _reset()
