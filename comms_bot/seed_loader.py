"""Demo seed data.

In demo mode the knowledge base is built by scraping the bundled demo FAQ
page (`demo/faq-page.html`) — the exact code path used against a real client
site — and a few sample conversations are loaded on first run so the staff
view has history to show.
"""

import json
from pathlib import Path

from sqlalchemy import func, select

from comms_bot.claude_client import get_answer_engine
from comms_bot.config import Settings
from comms_bot.database import session_scope
from comms_bot.faq_scraper import scrape_to_file
from comms_bot.logging_conf import get_logger
from comms_bot.models import AnswerSource, Conversation, Message, MessageRole, utcnow

logger = get_logger(__name__)


def ensure_demo_data(settings: Settings) -> None:
    if not Path(settings.faq_file).exists():
        logger.info("knowledge base missing — scraping %s", settings.faq_source)
        scrape_to_file(settings.faq_source, settings.faq_file)
        get_answer_engine().reload()
    _seed_conversations(settings)


def _seed_conversations(settings: Settings) -> None:
    seed_file = Path(settings.seed_conversations_file)
    if not seed_file.exists():
        return
    with session_scope() as session:
        existing = session.scalar(select(func.count(Conversation.id)))
        if existing:
            return
        data = json.loads(seed_file.read_text(encoding="utf-8"))
        for item in data:
            conversation = Conversation(
                session_id=item["session_id"],
                escalated=item.get("escalated", False),
            )
            if conversation.escalated:
                conversation.escalated_at = utcnow()
            for message in item["messages"]:
                conversation.messages.append(
                    Message(
                        role=MessageRole(message["role"]),
                        content=message["content"],
                        source=AnswerSource(message["source"]) if message.get("source") else None,
                        matched_question=message.get("matched_question"),
                    )
                )
            session.add(conversation)
        logger.info("seeded %d demo conversations", len(data))
