"""FastAPI app: chat WebSocket + staff API + static widget and demo site."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.routes.admin import router as admin_router
from api.routes.chat import router as chat_router
from api.routes.conversations import router as conversations_router
from comms_bot.config import get_settings
from comms_bot.database import init_db
from comms_bot.logging_conf import setup_logging
from comms_bot.scheduler import start_scheduler, stop_scheduler
from comms_bot.seed_loader import ensure_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    init_db()
    settings = get_settings()
    if settings.demo_mode:
        ensure_demo_data(settings)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Trinops Comms Bot", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(conversations_router)
app.include_router(admin_router)
app.mount("/widget", StaticFiles(directory="widget"), name="widget")
app.mount("/", StaticFiles(directory="demo", html=True), name="demo")
