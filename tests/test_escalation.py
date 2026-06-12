from pathlib import Path

from comms_bot.escalation import (
    HANDOFF_TEXT,
    OutboxNotifier,
    is_escalation,
    send_transcript,
)
from comms_bot.models import AnswerSource, Conversation, Message, MessageRole, utcnow


def test_escalation_keywords_detected(settings):
    assert is_escalation("Can I speak to someone please?", settings)
    assert is_escalation("HUMAN please", settings)
    assert is_escalation("I want to make a complaint", settings)
    assert is_escalation("get me an agent now", settings)
    assert is_escalation("can I talk to a person", settings)


def test_non_escalation_messages_pass_through(settings):
    assert not is_escalation("what does humanity mean", settings)  # word boundary
    assert not is_escalation("this is urgent", settings)
    assert not is_escalation("what are your opening hours", settings)
    assert not is_escalation("", settings)


def test_send_transcript_writes_outbox_email(settings):
    conversation = Conversation(
        session_id="abcd1234efgh5678", started_at=utcnow(), escalated=True
    )
    conversation.messages.append(
        Message(role=MessageRole.USER, content="I want to speak to someone", created_at=utcnow())
    )
    conversation.messages.append(
        Message(
            role=MessageRole.ASSISTANT,
            content=HANDOFF_TEXT,
            source=AnswerSource.HANDOFF,
            created_at=utcnow(),
        )
    )

    notifier = OutboxNotifier(settings)
    send_transcript(conversation, notifier, settings)

    files = list(Path(settings.outbox_dir).glob("*.html"))
    assert len(files) == 1
    assert "Chat_escalation" in files[0].name

    content = files[0].read_text(encoding="utf-8")
    assert f"To: {settings.cs_team_email}" in content
    assert "I want to speak to someone" in content
    assert "abcd1234" in content
