"""Real-time chat over WebSocket.

Each widget session maps to one Conversation row. Every user message is
checked against the escalation rules first (no API call); everything else
goes through the answer engine: FAQ match -> cache -> claude-haiku fallback.
"""

import json
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

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
    await websocket.accept()
    settings = get_settings()
    session_id = websocket.query_params.get("session") or uuid4().hex
    conversation_id = get_or_create_conversation_id(session_id)
    await websocket.send_json({"type": "session", "session_id": session_id})

    engine = get_answer_engine()
    notifier = get_notifier(settings)
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
            payload = handle_message(conversation_id, text, engine, notifier, settings)
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        logger.info("session %s disconnected", session_id[:8])
