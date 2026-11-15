import asyncio
import html
import logging
from contextlib import suppress

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import delete

from ..auth import get_or_create_user, is_allowed
from ..db import SessionLocal
from ..models import ChatMessage, Medication, MedicationLog
from ..services import assistant, core
from ..services.assistant import Attachment
from ..services.transcribe import transcribe
from .format import chunks, to_tg_html
from .keyboards import open_app_kb

log = logging.getLogger(__name__)
router = Router()

MAX_IMAGE = 5 * 1024 * 1024
MAX_PDF = 20 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

HELP = (
    "Я — <b>SelfControl</b>, твой помощник по контролю жизни.\n\n"
    "Просто пиши или говори голосом, как другу:\n"
    "• «Купил продукты на 1850» · «Вернул Саше 3000»\n"
    "• «На обед борщ и котлета» · «Вешу 82.4»\n"
    "• «Пью омепразол 20 мг в 8:00 и 20:00 две недели»\n"
    "• «Пробежал 5 км за 28 минут»\n"
    "• «Напоминай каждый будний день в 7:30 про зарядку»\n"
    "• «Сколько я потратил на кафе в этом месяце?»\n\n"
    "📸 Пришли <b>фото чека</b> — разнесу покупки по категориям.\n"
    "📄 Пришли <b>документ</b> (PDF, фото рецепта, счёт) — разберу и предложу действия.\n"
    "🍽 Фото еды — оценю калории.\n\n"
    "Команды: /app — приложение, /report — итоги дня, /reset — очистить контекст диалога."
)


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not is_allowed(user.id):
            if isinstance(event, Message):
                await event.answer("Доступ к боту закрыт.")
            return None
        return await handler(event, data)


async def keep_typing(bot: Bot, chat_id: int, stop: asyncio.Event) -> None:
    while not stop.is_set():
        with suppress(Exception):
            await bot.send_chat_action(chat_id, ChatAction.TYPING)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=4)


async def reply(message: Message, text: str) -> None:
    for part in chunks(to_tg_html(text)):
        try:
            await message.answer(part)
        except Exception:  # noqa: BLE001  неудачная разметка — отправляем как есть
            await message.answer(html.unescape(part), parse_mode=None)


async def handle_with_agent(message: Message, bot: Bot, text: str, attachments: list[Attachment] | None = None,
                            source: str = "ai", tg_file_id: str | None = None) -> None:
    stop = asyncio.Event()
    typing = asyncio.create_task(keep_typing(bot, message.chat.id, stop))
    try:
        async with SessionLocal() as session:
            u = message.from_user
            user = await get_or_create_user(session, u.id, u.first_name, u.username)
            result = await assistant.run_agent(session, user, text, attachments, source, tg_file_id)
        await reply(message, result.text)
    except Exception:  # noqa: BLE001
        log.exception("agent failed")
        await message.answer("😔 Не получилось обработать сообщение. Попробуй ещё раз чуть позже.")
    finally:
        stop.set()
        typing.cancel()


@router.message(CommandStart())
async def start(message: Message):
    async with SessionLocal() as session:
        u = message.from_user
        await get_or_create_user(session, u.id, u.first_name, u.username)
    await message.answer(f"Привет, {html.escape(u.first_name or '')}! 👋\n\n" + HELP, reply_markup=open_app_kb())


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(HELP, reply_markup=open_app_kb())


@router.message(Command("app"))
async def app_cmd(message: Message):
    kb = open_app_kb()
    await message.answer("Открыть приложение:" if kb else "WEBAPP_URL не настроен.", reply_markup=kb)


@router.message(Command("reset"))
async def reset_cmd(message: Message):
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        await session.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
        await session.commit()
    await message.answer("Контекст диалога очищен. Данные (расходы, питание и т.д.) не тронуты.")


@router.message(Command("report"))
async def report_cmd(message: Message, bot: Bot):
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    async with SessionLocal() as session:
        user = await get_or_create_user(session, message.from_user.id)
        text = await assistant.simple_completion(session, user, assistant.DAILY_REPORT_PROMPT)
    await reply(message, text or "Claude сейчас недоступен (проверьте ключ и баланс API в логах бэкенда).")


@router.message(F.voice | F.audio | F.video_note)
async def voice(message: Message, bot: Bot):
    media = message.voice or message.audio or message.video_note
    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        buf = await bot.download(media.file_id)
        text = await transcribe(buf.read(), getattr(media, "file_name", None) or "voice.ogg")
    except Exception:  # noqa: BLE001
        log.exception("transcribe failed")
        await message.answer("Не удалось распознать голосовое 😔")
        return
    if not text:
        await message.answer("Ничего не расслышал — попробуй ещё раз.")
        return
    await message.answer(f"🎙 <i>{html.escape(text)}</i>")
    await handle_with_agent(message, bot, text, source="voice")


@router.message(F.photo)
async def photo(message: Message, bot: Bot):
    ph = message.photo[-1]
    buf = await bot.download(ph.file_id)
    caption = message.caption or "Что на фото? Если это чек — сохрани его, если еда — запиши приём пищи."
    await handle_with_agent(message, bot, caption, [Attachment(buf.read(), "image/jpeg")],
                            source="receipt", tg_file_id=ph.file_id)


@router.message(F.document)
async def document(message: Message, bot: Bot):
    doc = message.document
    mime = (doc.mime_type or "").lower()
    name = (doc.file_name or "").lower()
    if name.endswith(".pdf"):
        mime = "application/pdf"
    if mime in IMAGE_TYPES:
        limit = MAX_IMAGE
    elif mime == "application/pdf":
        limit = MAX_PDF
    elif mime.startswith("text/") or name.endswith((".txt", ".csv", ".md")):
        mime, limit = "text/plain", 1024 * 1024
    else:
        await message.answer("Пока умею читать PDF, изображения и текстовые файлы.")
        return
    if (doc.file_size or 0) > limit:
        await message.answer(f"Файл слишком большой (лимит {limit // 1024 // 1024} МБ).")
        return
    buf = await bot.download(doc.file_id)
    caption = message.caption or "Разбери этот документ и предложи, что записать."
    await handle_with_agent(message, bot, caption, [Attachment(buf.read(), mime, doc.file_name)],
                            source="receipt", tg_file_id=doc.file_id)


@router.message(F.text)
async def text_msg(message: Message, bot: Bot):
    await handle_with_agent(message, bot, message.text)


@router.callback_query(F.data.startswith("med:"))
async def med_callback(cb: CallbackQuery):
    _, med_id, status = cb.data.split(":")
    async with SessionLocal() as session:
        user = await get_or_create_user(session, cb.from_user.id)
        med = await core.get_owned(session, Medication, user, int(med_id))
        if not med:
            await cb.answer("Лекарство не найдено")
            return
        await core.add_simple(session, MedicationLog, user, medication_id=med.id, status=status)
    mark = "✅ Принято" if status == "taken" else "⏭ Пропущено"
    with suppress(Exception):
        await cb.message.edit_text(f"{html.escape(cb.message.text or '')}\n\n{mark}")
    await cb.answer(mark)
