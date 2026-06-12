"""Escalation to a human.

Keyword rules decide when a visitor wants a person — no API call. On
escalation the full transcript is emailed to the CS team: OutboxNotifier
(DEMO_MODE=true) writes it as an HTML file into `data/outbox/` so the demo is
fully inspectable without sending anything; GmailNotifier (DEMO_MODE=false)
sends through the Gmail API.
"""

import base64
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, select_autoescape

from comms_bot.config import Settings
from comms_bot.logging_conf import get_logger
from comms_bot.models import Conversation

logger = get_logger(__name__)

HANDOFF_TEXT = (
    "No problem — I've passed this conversation to the team. "
    "Someone will pick it up and get back to you shortly."
)

_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
)


def is_escalation(text: str, settings: Settings) -> bool:
    lowered = text.lower()
    for keyword in settings.escalation_keywords:
        if re.search(rf"\b{re.escape(keyword.lower())}\b", lowered):
            return True
    return False


class Notifier(Protocol):
    def send(self, to: str, subject: str, html_body: str) -> None: ...


class OutboxNotifier:
    def __init__(self, settings: Settings) -> None:
        self._outbox = Path(settings.outbox_dir)
        self._outbox.mkdir(parents=True, exist_ok=True)

    def send(self, to: str, subject: str, html_body: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        safe_subject = re.sub(r"[^\w-]+", "_", subject)[:60]
        path = self._outbox / f"{stamp}_{safe_subject}.html"
        header = f"<!-- To: {to} -->\n<!-- Subject: {subject} -->\n"
        path.write_text(header + html_body, encoding="utf-8")
        logger.info("outbox: wrote %s (to=%s)", path.name, to)


class GmailNotifier:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._service = None

    def _client(self):
        if self._service is None:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_authorized_user_file(
                self._settings.google_token_file,
                scopes=["https://www.googleapis.com/auth/gmail.send"],
            )
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def send(self, to: str, subject: str, html_body: str) -> None:
        msg = MIMEText(html_body, "html")
        msg["to"] = to
        msg["from"] = self._settings.company_email
        msg["subject"] = subject
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._client().users().messages().send(userId="me", body={"raw": raw}).execute()
        logger.info("gmail: sent %r to %s", subject, to)


def send_transcript(conversation: Conversation, notifier: Notifier, settings: Settings) -> None:
    template = _env.get_template("escalation_email.html.j2")
    html = template.render(
        company_name=settings.company_name,
        session_id=conversation.session_id,
        started_at=conversation.started_at,
        messages=conversation.messages,
    )
    notifier.send(
        to=settings.cs_team_email,
        subject=f"Chat escalation — session {conversation.session_id[:8]}",
        html_body=html,
    )


def get_notifier(settings: Settings) -> Notifier:
    return OutboxNotifier(settings) if settings.demo_mode else GmailNotifier(settings)
