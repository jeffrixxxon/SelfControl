"""Claude-ассистент: понимает текст, голос, фото и документы и ведёт записи через инструменты."""
import base64
import logging
from dataclasses import dataclass, field

import anthropic
from anthropic import AsyncAnthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import ChatMessage, User
from ..timeutils import now_local
from . import core
from .tools import TOOLS, dumps, run_tool

log = logging.getLogger(__name__)
_client: AsyncAnthropic | None = None

WEEKDAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

SYSTEM_TEMPLATE = """Ты — SelfControl, личный ассистент пользователя в Telegram. Помогаешь держать под контролем \
финансы (покупки, бюджет, долги), здоровье (питание, лекарства, вес) и спорт (тренировки, цели, мотивация).

Правила:
- Отвечай по-русски, коротко и по делу, как заботливый, но честный коуч. Без воды и длинных списков.
- Если пользователь сообщает факт (купил, поел, выпил таблетку, взвесился, потренировался, занял денег) — \
сразу запиши его инструментом, не переспрашивая очевидное. Переспрашивай, только если не хватает суммы или сути.
- После записи кратко подтверди, что сохранено, и, если уместно, дай одно полезное замечание: \
остаток бюджета, калории до цели, напоминание о лекарстве, похвалу за тренировку.
- Фото чека: распознай все позиции и вызови save_receipt (итог бери из строки «ИТОГ»). \
Фото еды: оцени блюдо и КБЖУ и вызови add_meal. Рецепт или назначение врача: предложи добавить лекарства с расписанием. \
Счёт/квитанция: предложи записать расход. Другой документ: кратко перескажи суть и предложи действия.
- Голосовые приходят расшифровкой — в ней могут быть ошибки распознавания, интерпретируй по смыслу.
- Ты не врач: по дозировкам и симптомам советуй обращаться к врачу, не назначай лечение. \
Если видишь тревожные признаки (резкая потеря веса, отказ от еды, опасные сочетания лекарств) — мягко скажи об этом.
- Не выдумывай данные. Для отчётов пользуйся инструментами *_report.
- Пиши для Telegram: можно **жирный** и списки, без таблиц и заголовков.

Сейчас у пользователя: {now} ({weekday}), часовой пояс {tz}, валюта {currency}.
Имя: {name}.
Что известно о пользователе: {about}

Текущее состояние:
{snapshot}"""


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def api_error_text(e: Exception) -> str:
    """Понятное сообщение вместо падения, если Claude API вернул ошибку."""
    msg = str(getattr(e, "message", e)).lower()
    if "credit balance" in msg:
        return ("⚠️ На балансе Claude API закончились кредиты. Пополните его в console.anthropic.com → "
                "Plans & Billing. Записи в мини-приложении работают и без ассистента.")
    if isinstance(e, anthropic.AuthenticationError):
        return "⚠️ Неверный ANTHROPIC_API_KEY. Проверьте ключ в .env и перезапустите бэкенд."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "⚠️ У ключа API нет доступа к этой модели. Проверьте CLAUDE_MODEL в .env."
    if isinstance(e, anthropic.NotFoundError):
        return "⚠️ Модель не найдена. Проверьте CLAUDE_MODEL в .env."
    if isinstance(e, anthropic.RateLimitError):
        return "⏳ Слишком много запросов к Claude. Подождите минуту и повторите."
    if isinstance(e, (anthropic.InternalServerError, anthropic.APIConnectionError)):
        return "⏳ Claude временно недоступен. Попробуйте чуть позже."
    return f"⚠️ Ошибка Claude API: {getattr(e, 'message', e)}"


@dataclass
class Attachment:
    data: bytes
    media_type: str  # image/jpeg, image/png, image/webp, application/pdf, text/plain
    filename: str | None = None


@dataclass
class AgentResult:
    text: str
    actions: list[dict] = field(default_factory=list)


async def build_system(session: AsyncSession, user: User) -> str:
    now = now_local(user)
    return SYSTEM_TEMPLATE.format(
        now=now.strftime("%Y-%m-%d %H:%M"), weekday=WEEKDAYS[now.weekday()], tz=user.timezone,
        currency=user.currency, name=user.first_name or "—", about=user.about or "пока ничего",
        snapshot=await core.snapshot_text(session, user),
    )


def attachment_block(att: Attachment) -> dict:
    if att.media_type == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.b64encode(att.data).decode()}}
    if att.media_type.startswith("text/"):
        return {"type": "document", "source": {"type": "text", "media_type": "text/plain",
                                               "data": att.data.decode("utf-8", errors="replace")}}
    return {"type": "image", "source": {"type": "base64", "media_type": att.media_type,
                                        "data": base64.b64encode(att.data).decode()}}


async def load_history(session: AsyncSession, user: User) -> list[dict]:
    rows = (await session.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc()).limit(settings.history_messages)
    )).all()
    msgs: list[dict] = []
    for m in reversed(rows):
        if msgs and msgs[-1]["role"] == m.role:  # API требует чередования ролей
            msgs[-1]["content"] += "\n" + m.content
        else:
            msgs.append({"role": m.role, "content": m.content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


async def run_agent(
    session: AsyncSession, user: User, text: str, attachments: list[Attachment] | None = None,
    source: str = "ai", tg_file_id: str | None = None,
) -> AgentResult:
    if not settings.anthropic_api_key:
        return AgentResult("⚠️ Не задан ANTHROPIC_API_KEY — ассистент отключён.")

    attachments = attachments or []
    history = await load_history(session, user)
    content: list[dict] = [attachment_block(a) for a in attachments]
    content.append({"type": "text", "text": text or "Разбери вложение."})
    messages = history + [{"role": "user", "content": content}]
    if len(messages) > 1 and messages[-2]["role"] == "user":  # на случай оборванного диалога
        messages.pop(-2)

    system = [{"type": "text", "text": await build_system(session, user)}]
    ctx = {"source": source, "tg_file_id": tg_file_id}
    actions: list[dict] = []
    final_text = ""

    for _ in range(8):
        try:
            resp = await client().messages.create(
                model=settings.claude_model, max_tokens=settings.claude_max_tokens,
                system=system, tools=TOOLS, messages=messages,
            )
        except anthropic.APIError as e:
            log.error("Claude API error: %s", e)
            if actions:  # часть действий уже выполнена — сообщаем об этом
                done = ", ".join(a["tool"] for a in actions)
                return AgentResult(f"{api_error_text(e)}\n\nУспел выполнить: {done}.", actions)
            return AgentResult(api_error_text(e), actions)
        messages.append({"role": "assistant", "content": resp.content})
        text_parts = [b.text for b in resp.content if b.type == "text"]
        if text_parts:
            final_text = "\n".join(text_parts).strip()
        if resp.stop_reason != "tool_use":
            break
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                out = await run_tool(session, user, block.name, block.input, ctx)
                is_error = isinstance(out, dict) and "error" in out
            except Exception as e:  # noqa: BLE001
                log.exception("tool %s failed", block.name)
                await session.rollback()
                out, is_error = {"error": str(e)}, True
            actions.append({"tool": block.name, "input": block.input, "result": out})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": dumps(out),
                            "is_error": is_error})
        messages.append({"role": "user", "content": results})

    final_text = final_text or "Готово ✅"
    marker = " ".join(f"[{a.media_type.split('/')[-1]}]" for a in attachments)
    session.add(ChatMessage(user_id=user.id, role="user", content=f"{marker} {text}".strip()))
    session.add(ChatMessage(user_id=user.id, role="assistant", content=final_text))
    await session.commit()
    return AgentResult(final_text, actions)


async def simple_completion(session: AsyncSession, user: User, instruction: str) -> str:
    """Ответ без инструментов — для вечернего разбора и мотивационных сообщений."""
    if not settings.anthropic_api_key:
        return ""
    try:
        resp = await client().messages.create(
            model=settings.claude_model, max_tokens=800,
            system=await build_system(session, user),
            messages=[{"role": "user", "content": instruction}],
        )
    except anthropic.APIError as e:
        log.error("Claude API error: %s", e)
        return ""
    return "".join(b.text for b in resp.content if b.type == "text").strip()


DAILY_REPORT_PROMPT = (
    "Сделай короткий вечерний разбор моего дня (до 10 строк): деньги (сколько потратил, как бюджет), "
    "питание (калории против цели), лекарства (всё ли принято), активность. Отметь одно, что получилось, "
    "и одно, что улучшить завтра. Закончи коротким ободряющим предложением."
)


def motivation_prompt(reminder_text: str) -> str:
    return (f"Сработало моё мотивационное напоминание: «{reminder_text}». Напиши мне короткое (2–4 предложения) "
            "персональное мотивирующее сообщение, опираясь на мои реальные данные и цели. Без пафоса.")
