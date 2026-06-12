"""SQLAlchemy 2.0 models."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class AnswerSource(enum.StrEnum):
    FAQ = "FAQ"            # rapidfuzz match against the knowledge base — no API call
    CACHE = "CACHE"        # repeated question answered from cache — no API call
    LLM = "LLM"            # claude-haiku fallback with FAQ as context
    FALLBACK = "FALLBACK"  # no match and no API key — canned response
    HANDOFF = "HANDOFF"    # escalation hand-over message


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.id", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id} session={self.session_id[:8]} escalated={self.escalated}>"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole, native_enum=False, length=12))
    content: Mapped[str] = mapped_column(Text)

    # How the assistant reply was produced; null for user messages
    source: Mapped[AnswerSource | None] = mapped_column(
        Enum(AnswerSource, native_enum=False, length=12)
    )
    # FAQ question the reply matched, shown in the staff view
    matched_question: Mapped[str | None] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} {self.role} conv={self.conversation_id}>"
