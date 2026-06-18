"""Real-time chat over WebSocket.

Each widget session maps to one Conversation row. Every user message is
checked against the escalation rules first (no API call); everything else
goes through the answer engine: FAQ match -> cache -> claude-haiku fallback.
"""

import json
from functools import lru_cache
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from api.ratelimit import RateLimiter
from comms_bot.claude_client import AnswerEngine, get_answer_engine
from comms_bot.config import Settings, get_settings
from comms_bot.database import session_scope
from comms_bot.escalation import (
    HANDOFF_TEXT,
    Notifier,
    get_notifier,
    is_escalation,
    send_transcript,
)
from comms_bot.logging_conf import get_logger
from comms_bot.models import AnswerSource, Conversation, Message, MessageRole, utcnow

logger = get_logger(__name__)

router = APIRouter()

# WebSocket close codes (RFC 6455).
WS_POLICY_VIOLATION = 1008


@lru_cache
def _chat_limiter() -> RateLimiter:
    # Built once from settings. Tests that change the limit call cache_clear().
    return RateLimiter(get_settings().chat_rate_limit_per_minute, 60.0)


def origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Empty allowlist = open (the embeddable widget must work anywhere). When
    an allowlist is configured, the browser Origin header must match exactly."""
    if not settings.allowed_origins:
        return True
    return origin in settings.allowed_origins


def get_or_create_conversation_id(session_id: str) -> int:
    with session_scope() as session:
        conversation = session.scalar(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        if conversation is None:
            conversation = Conversation(session_id=session_id)
            session.add(conversation)
            session.flush()
        return conversation.id


def handle_message(
    conversation_id: int,
    text: str,
    engine: AnswerEngine,
    notifier: Notifier,
    settings: Settings,
) -> dict:
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        assert conversation is not None
        conversation.messages.append(Message(role=MessageRole.USER, content=text))

        if is_escalation(text, settings):
            if not conversation.escalated:
                conversation.escalated = True
                conversation.escalated_at = utcnow()
            conversation.messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=HANDOFF_TEXT,
                    source=AnswerSource.HANDOFF,
                )
            )
            session.flush()
            send_transcript(conversation, notifier, settings)
            return {"type": "handoff", "content": HANDOFF_TEXT, "source": "handoff"}

        reply = engine.answer(text)
        conversation.messages.append(
            Message(
                role=MessageRole.ASSISTANT,
                content=reply.text,
                source=AnswerSource(reply.source.upper()),
                matched_question=reply.matched_question,
            )
        )
        return {"type": "message", "content": reply.text, "source": reply.source}


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    settings = get_settings()

    # Refuse cross-origin connections before the handshake when an allowlist is
    # configured. Closing before accept rejects the upgrade with a 403.
    origin = websocket.headers.get("origin")
    if not origin_allowed(origin, settings):
        logger.warning("rejected chat ws from disallowed origin %r", origin)
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    await websocket.accept()
    client = websocket.client.host if websocket.client else "unknown"
    session_id = websocket.query_params.get("session") or uuid4().hex
    conversation_id = get_or_create_conversation_id(session_id)
    await websocket.send_json({"type": "session", "session_id": session_id})

    engine = get_answer_engine()
    notifier = get_notifier(settings)
    limiter = _chat_limiter()
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                logger.warning("session %s sent invalid JSON", session_id[:8])
                continue
            text = str(data.get("message", "")).strip()
            if not text:
                continue
            # Cap message length server-side: the widget sets maxlength but a
            # raw WebSocket client can ignore it, and the LLM fallback bills per token.
            if len(text) > settings.max_message_chars:
                text = text[: settings.max_message_chars]
            # Per-IP rate limit: drop the message without calling the engine so a
            # flood can't run up the Anthropic bill.
            if not limiter.allow(client):
                await websocket.send_json(
                    {
                        "type": "throttled",
                        "content": "You're sending messages too quickly. Please wait a moment and try again.",
                        "source": "system",
                    }
                )
                continue
            payload = handle_message(conversation_id, text, engine, notifier, settings)
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        logger.info("session %s disconnected", session_id[:8])
