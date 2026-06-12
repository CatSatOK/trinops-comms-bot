"""Read-only conversation history for staff."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from comms_bot.database import session_scope
from comms_bot.models import Conversation

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
def list_conversations() -> list[dict]:
    with session_scope() as session:
        conversations = session.scalars(
            select(Conversation).order_by(Conversation.started_at.desc())
        ).all()
        return [
            {
                "id": c.id,
                "session_id": c.session_id,
                "started_at": c.started_at.isoformat(),
                "escalated": c.escalated,
                "escalated_at": c.escalated_at.isoformat() if c.escalated_at else None,
                "message_count": len(c.messages),
                "last_message": c.messages[-1].content[:120] if c.messages else None,
            }
            for c in conversations
        ]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int) -> dict:
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        return {
            "id": conversation.id,
            "session_id": conversation.session_id,
            "started_at": conversation.started_at.isoformat(),
            "escalated": conversation.escalated,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "source": m.source,
                    "matched_question": m.matched_question,
                    "created_at": m.created_at.isoformat(),
                }
                for m in conversation.messages
            ],
        }
