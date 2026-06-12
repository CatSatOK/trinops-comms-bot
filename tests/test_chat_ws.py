"""End-to-end through the real app: WebSocket chat -> DB -> outbox.

The fixture points the app at temp paths and an empty FAQ_FILE, so startup
exercises the real demo path: scrape demo/faq-page.html into faq.json, then
answer over the WebSocket from that knowledge base.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    monkeypatch.setenv("OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("FAQ_FILE", str(tmp_path / "faq.json"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("FAQ_REFRESH_HOURS", "0")
    monkeypatch.setenv("SEED_CONVERSATIONS_FILE", str(tmp_path / "no-seed.json"))

    # reset cached settings and singletons so each test gets a fresh app state
    import comms_bot.claude_client as claude_client
    import comms_bot.database as database
    from comms_bot.config import get_settings

    get_settings.cache_clear()
    database._engine = None
    database._SessionLocal = None
    claude_client._engine = None

    from api.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    database._engine = None
    database._SessionLocal = None
    claude_client._engine = None


def test_faq_question_answered_over_websocket(client):
    with client.websocket_connect("/ws/chat") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "session"
        assert hello["session_id"]

        ws.send_json({"message": "What are your opening hours?"})
        reply = ws.receive_json()
        assert reply["type"] == "message"
        assert reply["source"] == "faq"
        assert "Monday to Friday" in reply["content"]


def test_unknown_question_gets_fallback(client):
    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()
        ws.send_json({"message": "Can I bring my dog to the showroom?"})
        reply = ws.receive_json()
        assert reply["source"] == "fallback"


def test_escalation_marks_conversation_and_emails_transcript(client, tmp_path):
    with client.websocket_connect("/ws/chat?session=e2e-escalation") as ws:
        ws.receive_json()
        ws.send_json({"message": "I want to speak to someone"})
        reply = ws.receive_json()
        assert reply["type"] == "handoff"

    conversations = client.get("/conversations").json()
    matching = [c for c in conversations if c["session_id"] == "e2e-escalation"]
    assert matching and matching[0]["escalated"]

    detail = client.get(f"/conversations/{matching[0]['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["USER", "ASSISTANT"]
    assert detail["messages"][1]["source"] == "HANDOFF"

    outbox = list((tmp_path / "outbox").glob("*.html"))
    assert len(outbox) == 1
    assert "I want to speak to someone" in outbox[0].read_text(encoding="utf-8")


def test_session_resumes_existing_conversation(client):
    with client.websocket_connect("/ws/chat?session=e2e-resume") as ws:
        ws.receive_json()
        ws.send_json({"message": "opening hours?"})
        ws.receive_json()
    with client.websocket_connect("/ws/chat?session=e2e-resume") as ws:
        ws.receive_json()
        ws.send_json({"message": "how do I get a quote?"})
        ws.receive_json()

    conversations = client.get("/conversations").json()
    matching = [c for c in conversations if c["session_id"] == "e2e-resume"]
    assert len(matching) == 1
    assert matching[0]["message_count"] == 4


def test_admin_retrain_rebuilds_knowledge_base(client, tmp_path):
    response = client.post("/admin/retrain", json={})
    assert response.status_code == 200
    assert response.json()["pairs"] == 10

    faq = client.get("/admin/faq").json()
    assert len(faq) == 10
