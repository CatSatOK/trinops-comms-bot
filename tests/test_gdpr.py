"""GDPR: right-to-erasure delete of a conversation and its messages."""


def _start_conversation(client, session_id, text="opening hours?"):
    with client.websocket_connect(f"/ws/chat?session={session_id}") as ws:
        ws.receive_json()  # session
        ws.send_json({"message": text})
        ws.receive_json()  # reply


def test_erase_conversation_removes_it(client):
    _start_conversation(client, "erase-me")
    conv = next(c for c in client.get("/conversations").json() if c["session_id"] == "erase-me")

    assert client.delete(f"/conversations/{conv['id']}").status_code == 204
    assert all(c["id"] != conv["id"] for c in client.get("/conversations").json())
    assert client.get(f"/conversations/{conv['id']}").status_code == 404


def test_erase_missing_conversation_404(client):
    assert client.delete("/conversations/999999").status_code == 404
