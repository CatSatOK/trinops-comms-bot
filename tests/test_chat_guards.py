"""Chat WebSocket guards: rate limit, server-side length cap, Origin allowlist.

The RateLimiter is exercised directly; the guards are exercised end to end
through the real app with a TestClient WebSocket.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.ratelimit import RateLimiter


# --- RateLimiter unit tests -------------------------------------------------


def test_limiter_allows_up_to_max_then_blocks():
    limiter = RateLimiter(max_events=2, window_seconds=60)
    assert limiter.allow("ip", now=0.0) is True
    assert limiter.allow("ip", now=1.0) is True
    assert limiter.allow("ip", now=2.0) is False


def test_limiter_zero_disables():
    limiter = RateLimiter(max_events=0, window_seconds=60)
    for _ in range(5):
        assert limiter.allow("ip", now=0.0) is True


# --- WS guard integration tests ---------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
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


def _refresh_settings():
    from comms_bot.config import get_settings
    import api.routes.chat as chat

    get_settings.cache_clear()
    chat._chat_limiter.cache_clear()


def test_rate_limit_throttles_after_max(client, monkeypatch):
    monkeypatch.setenv("CHAT_RATE_LIMIT_PER_MINUTE", "2")
    _refresh_settings()

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # session
        ws.send_json({"message": "opening hours?"})
        assert ws.receive_json()["type"] == "message"
        ws.send_json({"message": "opening hours?"})
        assert ws.receive_json()["type"] == "message"
        ws.send_json({"message": "opening hours?"})
        assert ws.receive_json()["type"] == "throttled"


def test_long_message_truncated_server_side(client, monkeypatch):
    monkeypatch.setenv("MAX_MESSAGE_CHARS", "10")
    _refresh_settings()

    with client.websocket_connect("/ws/chat?session=truncate") as ws:
        ws.receive_json()
        ws.send_json({"message": "x" * 100})
        ws.receive_json()

    conversations = client.get("/conversations").json()
    match = next(c for c in conversations if c["session_id"] == "truncate")
    detail = client.get(f"/conversations/{match['id']}").json()
    user_msg = next(m for m in detail["messages"] if m["role"] == "USER")
    assert len(user_msg["content"]) == 10


def test_origin_allowlist_blocks_unknown_origin(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com"]')
    _refresh_settings()

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/chat", headers={"origin": "https://evil.example.com"}
        ) as ws:
            ws.receive_json()


def test_origin_allowlist_permits_known_origin(client, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://app.example.com"]')
    _refresh_settings()

    with client.websocket_connect(
        "/ws/chat", headers={"origin": "https://app.example.com"}
    ) as ws:
        assert ws.receive_json()["type"] == "session"


def test_empty_allowlist_permits_any_origin(client):
    with client.websocket_connect(
        "/ws/chat", headers={"origin": "https://anywhere.example.com"}
    ) as ws:
        assert ws.receive_json()["type"] == "session"
