"""Точка входа: FastAPI (API мини-аппа) + Telegram-бот (long polling) + планировщик в одном процессе."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from fastapi import APIRouter, FastAPI

from .api import finance, fitness, general, health
from .bot.handlers import AccessMiddleware, router as bot_router
from .config import settings
from .db import init_db
from .services.scheduler import run_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("selfcontrol")


async def setup_bot(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="app", description="Открыть приложение"),
        BotCommand(command="report", description="Итоги дня"),
        BotCommand(command="help", description="Что я умею"),
        BotCommand(command="reset", description="Очистить контекст диалога"),
    ])
    if settings.webapp_url:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="SelfControl", web_app=WebAppInfo(url=settings.webapp_url)))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    tasks: list[asyncio.Task] = []
    bot = None
    if settings.bot_token:
        bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = Dispatcher()
        dp.message.outer_middleware(AccessMiddleware())
        dp.callback_query.outer_middleware(AccessMiddleware())
        dp.include_router(bot_router)
        with suppress(Exception):
            await setup_bot(bot)
        tasks.append(asyncio.create_task(dp.start_polling(bot, handle_signals=False)))
        tasks.append(asyncio.create_task(run_scheduler(bot)))
    else:
        log.warning("BOT_TOKEN не задан — бот и напоминания не запущены, работает только API")
    yield
    for t in tasks:
        t.cancel()
    if bot:
        await bot.session.close()


app = FastAPI(title="SelfControl API", lifespan=lifespan)

api = APIRouter(prefix="/api")
for r in (general.router, finance.router, health.router, fitness.router):
    api.include_router(r)
app.include_router(api)


@app.get("/health")
async def healthcheck():
    return {"ok": True}
