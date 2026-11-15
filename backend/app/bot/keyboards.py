from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from ..config import settings


def open_app_kb(label: str = "📱 Открыть SelfControl", path: str = "") -> InlineKeyboardMarkup | None:
    if not settings.webapp_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, web_app=WebAppInfo(url=settings.webapp_url.rstrip("/") + "/" + path))
    ]])


def medication_kb(med_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Принял", callback_data=f"med:{med_id}:taken"),
        InlineKeyboardButton(text="⏭ Пропустил", callback_data=f"med:{med_id}:skipped"),
    ]])
