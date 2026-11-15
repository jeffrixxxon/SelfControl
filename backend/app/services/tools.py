"""Инструменты, которыми Claude управляет данными пользователя."""
import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Budget, Debt, Goal, Meal, Medication, MedicationLog, Reminder, Transaction, User, WeightEntry, Workout
from ..timeutils import local_day_bounds, now_local, parse_local
from . import core

DT = {"type": "string", "description": "Дата-время 'YYYY-MM-DD HH:MM' по времени пользователя. Не указывай, если сейчас."}
CATS = ", ".join(core.EXPENSE_CATEGORIES)

TOOLS: list[dict[str, Any]] = [
    {
        "name": "add_transaction",
        "description": f"Записать расход или доход. Категории расходов: {CATS}. Доходов: {', '.join(core.INCOME_CATEGORIES)}.",
        "input_schema": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["expense", "income"]},
            "amount": {"type": "number"},
            "category": {"type": "string"},
            "description": {"type": "string"},
            "merchant": {"type": "string"},
            "occurred_at": DT,
        }, "required": ["kind", "amount", "category"]},
    },
    {
        "name": "save_receipt",
        "description": "Сохранить распознанный кассовый чек: позиции и итог. Расходы создаются автоматически по категориям позиций.",
        "input_schema": {"type": "object", "properties": {
            "merchant": {"type": "string"},
            "purchased_at": DT,
            "total": {"type": "number", "description": "Итог к оплате по чеку"},
            "items": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "qty": {"type": "number"}, "price": {"type": "number"},
                "total": {"type": "number"}, "category": {"type": "string", "description": f"Одна из: {CATS}"},
            }, "required": ["name", "total", "category"]}},
        }, "required": ["total", "items"]},
    },
    {
        "name": "list_transactions",
        "description": "Последние операции за N дней (по умолчанию 7), опционально по категории.",
        "input_schema": {"type": "object", "properties": {
            "days": {"type": "integer"}, "category": {"type": "string"}}},
    },
    {
        "name": "delete_transaction",
        "description": "Удалить операцию по id (например, если пользователь просит отменить ошибочную запись).",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "set_budget",
        "description": "Задать месячный лимит. category=null — общий бюджет на месяц.",
        "input_schema": {"type": "object", "properties": {
            "category": {"type": ["string", "null"]}, "monthly_limit": {"type": "number"}},
            "required": ["monthly_limit"]},
    },
    {
        "name": "finance_report",
        "description": "Сводка финансов за месяц: расходы по категориям, доходы, бюджеты. По умолчанию текущий месяц.",
        "input_schema": {"type": "object", "properties": {"year": {"type": "integer"}, "month": {"type": "integer"}}},
    },
    {
        "name": "add_debt",
        "description": "Записать долг. i_owe — я должен кому-то; owed_to_me — мне должны.",
        "input_schema": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["i_owe", "owed_to_me"]},
            "counterparty": {"type": "string"}, "amount": {"type": "number"},
            "due_date": {"type": "string", "description": "YYYY-MM-DD"}, "note": {"type": "string"},
        }, "required": ["direction", "counterparty", "amount"]},
    },
    {
        "name": "list_debts",
        "description": "Список открытых долгов с id и остатком.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pay_debt",
        "description": "Зафиксировать частичное или полное погашение долга.",
        "input_schema": {"type": "object", "properties": {
            "debt_id": {"type": "integer"}, "amount": {"type": "number"}}, "required": ["debt_id", "amount"]},
    },
    {
        "name": "add_meal",
        "description": "Записать приём пищи. Если КБЖУ не указаны — оцени сам по описанию/фото и честно скажи, что это оценка.",
        "input_schema": {"type": "object", "properties": {
            "description": {"type": "string"},
            "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
            "calories": {"type": "number"}, "protein": {"type": "number"},
            "fat": {"type": "number"}, "carbs": {"type": "number"}, "eaten_at": DT,
        }, "required": ["description"]},
    },
    {
        "name": "add_medication",
        "description": "Добавить лекарство в курс приёма. times — время приёма 'ЧЧ:ММ'; напоминания создаются автоматически.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": "string"}, "dosage": {"type": "string"},
            "times": {"type": "array", "items": {"type": "string"}},
            "notes": {"type": "string"}, "end_date": {"type": "string", "description": "YYYY-MM-DD"},
        }, "required": ["name"]},
    },
    {
        "name": "log_medication",
        "description": "Отметить приём (taken) или пропуск (skipped) лекарства.",
        "input_schema": {"type": "object", "properties": {
            "medication_id": {"type": "integer"}, "status": {"type": "string", "enum": ["taken", "skipped"]}},
            "required": ["medication_id"]},
    },
    {
        "name": "stop_medication",
        "description": "Завершить курс лекарства (отключает напоминания).",
        "input_schema": {"type": "object", "properties": {"medication_id": {"type": "integer"}},
                         "required": ["medication_id"]},
    },
    {
        "name": "add_weight",
        "description": "Записать вес в кг.",
        "input_schema": {"type": "object", "properties": {"weight_kg": {"type": "number"}, "measured_at": DT},
                         "required": ["weight_kg"]},
    },
    {
        "name": "health_report",
        "description": "Питание и лекарства за сегодня, история веса.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_workout",
        "description": "Записать тренировку.",
        "input_schema": {"type": "object", "properties": {
            "type": {"type": "string", "description": "Силовая, Бег, Ходьба, Велосипед, Плавание, Йога, Растяжка, Другое"},
            "duration_min": {"type": "integer"}, "calories": {"type": "number"},
            "exercises": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "sets": {"type": "integer"}, "reps": {"type": "integer"},
                "weight": {"type": "number"}, "distance_km": {"type": "number"}}}},
            "notes": {"type": "string"}, "performed_at": DT,
        }, "required": ["type"]},
    },
    {
        "name": "fitness_report",
        "description": "Тренировки за текущую неделю.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_goal",
        "description": "Создать цель (финансы, здоровье, спорт и т.д.).",
        "input_schema": {"type": "object", "properties": {
            "title": {"type": "string"},
            "area": {"type": "string", "enum": ["finance", "health", "fitness", "other"]},
            "target_value": {"type": "number"}, "current_value": {"type": "number"},
            "unit": {"type": "string"}, "deadline": {"type": "string", "description": "YYYY-MM-DD"},
        }, "required": ["title"]},
    },
    {
        "name": "update_goal",
        "description": "Обновить прогресс цели или отметить выполненной.",
        "input_schema": {"type": "object", "properties": {
            "goal_id": {"type": "integer"}, "current_value": {"type": "number"}, "done": {"type": "boolean"}},
            "required": ["goal_id"]},
    },
    {
        "name": "add_reminder",
        "description": ("Создать напоминание. Повторяющееся: time_of_day 'ЧЧ:ММ' и days_of_week (0=Пн…6=Вс, пусто — каждый день). "
                        "Разовое: run_at. kind=motivation — в момент срабатывания ты напишешь персональное мотивирующее сообщение."),
        "input_schema": {"type": "object", "properties": {
            "text": {"type": "string"},
            "kind": {"type": "string", "enum": ["custom", "workout", "motivation"]},
            "time_of_day": {"type": "string"},
            "days_of_week": {"type": "array", "items": {"type": "integer"}},
            "run_at": DT,
        }, "required": ["text"]},
    },
    {
        "name": "list_reminders",
        "description": "Активные напоминания с id.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "delete_reminder",
        "description": "Удалить напоминание по id.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "update_profile",
        "description": ("Обновить настройки и сведения о пользователе: часовой пояс (IANA, напр. Europe/Moscow), валюта, "
                        "цель по калориям, целевой вес, рост, время вечернего разбора, заметки о себе (about) — "
                        "сохраняй туда важные факты: цели, ограничения по здоровью, предпочтения."),
        "input_schema": {"type": "object", "properties": {
            "timezone": {"type": "string"}, "currency": {"type": "string"},
            "calorie_goal": {"type": "integer"}, "weight_goal": {"type": "number"}, "height_cm": {"type": "number"},
            "daily_report_time": {"type": "string"}, "daily_report_enabled": {"type": "boolean"},
            "about": {"type": "string", "description": "Полный обновлённый текст заметок о пользователе"},
        }},
    },
]


def _date(v: str | None) -> date | None:
    return date.fromisoformat(v) if v else None


async def run_tool(session: AsyncSession, user: User, name: str, args: dict, ctx: dict) -> Any:
    """Выполняет инструмент и возвращает JSON-совместимый результат."""
    src = ctx.get("source", "ai")
    match name:
        case "add_transaction":
            t = await core.add_transaction(
                session, user, kind=args["kind"], amount=float(args["amount"]), category=args.get("category", "Прочее"),
                description=args.get("description"), merchant=args.get("merchant"),
                occurred_at=parse_local(user, args.get("occurred_at")), source=src)
            return {"ok": True, "id": t.id}
        case "save_receipt":
            r, txs = await core.save_receipt(
                session, user, args.get("merchant"), float(args["total"]),
                parse_local(user, args.get("purchased_at")), args.get("items", []), ctx.get("tg_file_id"))
            return {"ok": True, "receipt_id": r.id,
                    "transactions": [{"id": t.id, "category": t.category, "amount": t.amount} for t in txs]}
        case "list_transactions":
            start, _ = local_day_bounds(user, now_local(user).date() - timedelta(days=int(args.get("days", 7)) - 1))
            q = select(Transaction).where(Transaction.user_id == user.id, Transaction.occurred_at >= start)
            if args.get("category"):
                q = q.where(Transaction.category == args["category"])
            rows = (await session.scalars(q.order_by(Transaction.occurred_at.desc()).limit(60))).all()
            return [{k: core.to_dict(t)[k] for k in ("id", "kind", "amount", "category", "description", "merchant",
                                                     "occurred_at")} for t in rows]
        case "delete_transaction":
            t = await core.get_owned(session, Transaction, user, int(args["id"]))
            if not t:
                return {"error": "не найдено"}
            await session.delete(t)
            await session.commit()
            return {"ok": True}
        case "set_budget":
            cat = args.get("category")
            q = select(Budget).where(Budget.user_id == user.id)
            q = q.where(Budget.category == cat) if cat else q.where(Budget.category.is_(None))
            b = await session.scalar(q)
            if b:
                b.monthly_limit = float(args["monthly_limit"])
                await session.commit()
            else:
                await core.add_simple(session, Budget, user, category=cat, monthly_limit=float(args["monthly_limit"]))
            return {"ok": True}
        case "finance_report":
            return await core.month_finance(session, user, args.get("year"), args.get("month"))
        case "add_debt":
            d = await core.add_debt(session, user, direction=args["direction"], counterparty=args["counterparty"],
                                    amount=float(args["amount"]), due_date=_date(args.get("due_date")),
                                    note=args.get("note"))
            return {"ok": True, "id": d.id}
        case "list_debts":
            rows = (await session.scalars(select(Debt).where(Debt.user_id == user.id, Debt.closed.is_(False)))).all()
            return [{k: core.to_dict(d)[k] for k in ("id", "direction", "counterparty", "amount", "remaining",
                                                     "due_date", "note")} for d in rows]
        case "pay_debt":
            d = await core.get_owned(session, Debt, user, int(args["debt_id"]))
            if not d:
                return {"error": "долг не найден"}
            d = await core.pay_debt(session, user, d, float(args["amount"]))
            return {"ok": True, "remaining": d.remaining, "closed": d.closed}
        case "add_meal":
            m = await core.add_simple(session, Meal, user, description=args["description"],
                                      meal_type=args.get("meal_type"), calories=args.get("calories"),
                                      protein=args.get("protein"), fat=args.get("fat"), carbs=args.get("carbs"),
                                      eaten_at=parse_local(user, args.get("eaten_at")))
            return {"ok": True, "id": m.id}
        case "add_medication":
            m = await core.add_medication(session, user, name=args["name"], dosage=args.get("dosage"),
                                          times=sorted(set(args.get("times", []))), notes=args.get("notes"),
                                          start_date=now_local(user).date(), end_date=_date(args.get("end_date")))
            return {"ok": True, "id": m.id}
        case "log_medication":
            m = await core.get_owned(session, Medication, user, int(args["medication_id"]))
            if not m:
                return {"error": "лекарство не найдено"}
            await core.add_simple(session, MedicationLog, user, medication_id=m.id,
                                  status=args.get("status", "taken"))
            return {"ok": True}
        case "stop_medication":
            m = await core.get_owned(session, Medication, user, int(args["medication_id"]))
            if not m:
                return {"error": "лекарство не найдено"}
            m.active = False
            await session.commit()
            await core.sync_medication_reminders(session, user, m)
            return {"ok": True}
        case "add_weight":
            w = await core.add_simple(session, WeightEntry, user, weight_kg=float(args["weight_kg"]),
                                      measured_at=parse_local(user, args.get("measured_at")))
            return {"ok": True, "id": w.id}
        case "health_report":
            return await core.health_today(session, user)
        case "add_workout":
            w = await core.add_simple(session, Workout, user, type=args["type"], duration_min=args.get("duration_min"),
                                      calories=args.get("calories"), exercises=args.get("exercises", []),
                                      notes=args.get("notes"), performed_at=parse_local(user, args.get("performed_at")))
            return {"ok": True, "id": w.id}
        case "fitness_report":
            return await core.fitness_week(session, user)
        case "add_goal":
            g = await core.add_simple(session, Goal, user, title=args["title"], area=args.get("area", "other"),
                                      target_value=args.get("target_value"), current_value=args.get("current_value"),
                                      unit=args.get("unit"), deadline=_date(args.get("deadline")))
            return {"ok": True, "id": g.id}
        case "update_goal":
            g = await core.get_owned(session, Goal, user, int(args["goal_id"]))
            if not g:
                return {"error": "цель не найдена"}
            if "current_value" in args:
                g.current_value = args["current_value"]
            if "done" in args:
                g.done = bool(args["done"])
            await session.commit()
            return {"ok": True}
        case "add_reminder":
            if not args.get("time_of_day") and not args.get("run_at"):
                return {"error": "нужно time_of_day или run_at"}
            r = await core.add_reminder(
                session, user, text=args["text"], kind=args.get("kind", "custom"),
                time_of_day=args.get("time_of_day"), days_of_week=args.get("days_of_week", []),
                run_at=parse_local(user, args["run_at"]) if args.get("run_at") else None)
            return {"ok": True, "id": r.id, "next_run_at": core.to_dict(r)["next_run_at"]}
        case "list_reminders":
            rows = (await session.scalars(select(Reminder).where(Reminder.user_id == user.id, Reminder.active))).all()
            return [{k: core.to_dict(r)[k] for k in ("id", "text", "kind", "time_of_day", "days_of_week",
                                                     "next_run_at")} for r in rows]
        case "delete_reminder":
            r = await core.get_owned(session, Reminder, user, int(args["id"]))
            if not r:
                return {"error": "не найдено"}
            await session.delete(r)
            await session.commit()
            return {"ok": True}
        case "update_profile":
            allowed = {"timezone", "currency", "calorie_goal", "weight_goal", "height_cm", "daily_report_time",
                       "daily_report_enabled", "about"}
            for k, v in args.items():
                if k in allowed:
                    setattr(user, k, v)
            await session.commit()
            return {"ok": True}
    return {"error": f"неизвестный инструмент {name}"}


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
