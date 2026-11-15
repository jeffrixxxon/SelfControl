"""Фоновый цикл: напоминания, мотивация от Claude и вечерний разбор дня."""
import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from ..db import SessionLocal
from ..models import Medication, Reminder, User
from ..timeutils import aware, compute_next_run, now_local
from . import assistant
from ..bot.format import to_tg_html
from ..bot.keyboards import medication_kb, open_app_kb

log = logging.getLogger(__name__)
TICK_SECONDS = 30
STALE = timedelta(hours=2)  # пропущенные из-за простоя напоминания старше 2 часов не досылаем


async def fire_reminders(bot: Bot) -> None:
    now = datetime.now(timezone.utc)
    async with SessionLocal() as session:
        due = (await session.scalars(
            select(Reminder).where(Reminder.active, Reminder.next_run_at.is_not(None), Reminder.next_run_at <= now)
        )).all()
        for r in due:
            user = await session.get(User, r.user_id)
            if user is None:
                continue
            try:
                if now - aware(r.next_run_at) <= STALE:
                    await send_reminder(bot, session, user, r)
            except Exception:  # noqa: BLE001
                log.exception("reminder %s failed", r.id)
            r.next_run_at = compute_next_run(r, user, after=now)
            if r.next_run_at is None:
                r.active = False
            await session.commit()


async def send_reminder(bot: Bot, session, user: User, r: Reminder) -> None:
    if r.kind == "medication" and r.medication_id:
        med = await session.get(Medication, r.medication_id)
        if med is None or not med.active:
            return
        if med.end_date and now_local(user).date() > med.end_date:
            med.active = False
            r.active = False
            return
        await bot.send_message(user.tg_id, html.escape(r.text), reply_markup=medication_kb(med.id))
    elif r.kind == "motivation":
        text = await assistant.simple_completion(session, user, assistant.motivation_prompt(r.text)) or r.text
        await bot.send_message(user.tg_id, "🔥 " + to_tg_html(text))
    elif r.kind == "workout":
        await bot.send_message(user.tg_id, f"🏋️ {html.escape(r.text)}", reply_markup=open_app_kb("Записать тренировку"))
    else:
        await bot.send_message(user.tg_id, f"⏰ {html.escape(r.text)}")


async def daily_reports(bot: Bot) -> None:
    async with SessionLocal() as session:
        users = (await session.scalars(select(User).where(User.daily_report_enabled))).all()
        for user in users:
            local = now_local(user)
            if user.last_report_date == local.date() or local.strftime("%H:%M") < user.daily_report_time:
                continue
            user.last_report_date = local.date()
            await session.commit()
            try:
                text = await assistant.simple_completion(session, user, assistant.DAILY_REPORT_PROMPT)
                if text:
                    await bot.send_message(user.tg_id, "🌙 <b>Итоги дня</b>\n\n" + to_tg_html(text),
                                           reply_markup=open_app_kb("📊 Подробнее"))
            except Exception:  # noqa: BLE001
                log.exception("daily report for %s failed", user.id)


async def run_scheduler(bot: Bot) -> None:
    log.info("Планировщик запущен")
    while True:
        try:
            await fire_reminders(bot)
            await daily_reports(bot)
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
