"""APScheduler: periodic FAQ re-scrape so the bot stays current as the
client updates their site. Disabled with FAQ_REFRESH_HOURS=0."""

from apscheduler.schedulers.background import BackgroundScheduler

from comms_bot.claude_client import get_answer_engine
from comms_bot.config import get_settings
from comms_bot.faq_scraper import scrape_to_file
from comms_bot.logging_conf import get_logger

logger = get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def retrain() -> int:
    settings = get_settings()
    count = scrape_to_file(settings.faq_source, settings.faq_file)
    get_answer_engine().reload()
    logger.info("retrain complete: %d Q&A pairs", count)
    return count


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if settings.faq_refresh_hours <= 0:
        logger.info("FAQ_REFRESH_HOURS=0 — scheduled retrain disabled")
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        retrain, "interval", hours=settings.faq_refresh_hours, id="faq_retrain"
    )
    _scheduler.start()
    logger.info("scheduler started: retrain every %dh", settings.faq_refresh_hours)


def stop_scheduler() -> None:
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
