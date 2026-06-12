"""Admin: retrain the knowledge base from the client's FAQ page.

Demo scope: these endpoints are unauthenticated. Put them behind your
reverse-proxy auth (or an API key middleware) before exposing publicly.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from comms_bot.claude_client import get_answer_engine
from comms_bot.config import get_settings
from comms_bot.faq_scraper import scrape_to_file

router = APIRouter(prefix="/admin", tags=["admin"])


class RetrainRequest(BaseModel):
    source: str | None = None  # URL or local HTML file; defaults to FAQ_SOURCE


@router.post("/retrain")
def retrain(body: RetrainRequest | None = None) -> dict:
    settings = get_settings()
    source = (body.source if body else None) or settings.faq_source
    pairs = scrape_to_file(source, settings.faq_file)
    get_answer_engine().reload()
    return {"source": source, "pairs": pairs}


@router.get("/faq")
def get_faq() -> list[dict]:
    return [
        {"question": entry.question, "answer": entry.answer}
        for entry in get_answer_engine().faq
    ]
