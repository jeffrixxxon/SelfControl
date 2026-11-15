"""Общая бизнес-логика: её используют и API мини-аппа, и инструменты Claude."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Budget,
    Debt,
    DebtPayment,
    Goal,
    Meal,
    Medication,
    MedicationLog,
    Receipt,
    Reminder,
    Transaction,
    User,
    WeightEntry,
    Workout,
)
from ..timeutils import aware, compute_next_run, local_day_bounds, local_month_bounds, now_local, tz

EXPENSE_CATEGORIES = [
    "Продукты", "Кафе и рестораны", "Транспорт", "Жильё и ЖКХ", "Связь и интернет",
    "Здоровье и аптека", "Спорт", "Одежда", "Дом и быт", "Развлечения", "Подписки",
    "Образование", "Подарки", "Красота", "Авто", "Путешествия", "Прочее",
]
INCOME_CATEGORIES = ["Зарплата", "Подработка", "Подарок", "Кэшбэк", "Возврат долга", "Прочее"]


def to_dict(obj: Any) -> dict:
    data = {}
    for col in obj.__table__.columns:
        v = getattr(obj, col.key)
        if isinstance(v, datetime):
            v = aware(v).isoformat()
        elif isinstance(v, date):
            v = v.isoformat()
        data[col.key] = v
    return data


async def get_owned(session: AsyncSession, model, user: User, obj_id: int):
    obj = await session.get(model, obj_id)
    if obj is None or obj.user_id != user.id:
        return None
    return obj


# ---------- Финансы ----------
async def add_transaction(session: AsyncSession, user: User, **kw) -> Transaction:
    kw.setdefault("currency", user.currency)
    t = Transaction(user_id=user.id, **kw)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


async def save_receipt(
    session: AsyncSession, user: User, merchant: str | None, total: float, purchased_at: datetime,
    items: list[dict], tg_file_id: str | None = None,
) -> tuple[Receipt, list[Transaction]]:
    r = Receipt(user_id=user.id, merchant=merchant, total=total, purchased_at=purchased_at,
                items=items, tg_file_id=tg_file_id)
    session.add(r)
    await session.flush()
    # Расход разбивается по категориям позиций чека
    by_cat: dict[str, float] = defaultdict(float)
    for it in items:
        by_cat[it.get("category") or "Продукты"] += float(it.get("total") or 0)
    diff = round(total - sum(by_cat.values()), 2)
    if not by_cat:
        by_cat["Продукты"] = total
    elif abs(diff) >= 0.01:  # скидки/округления — к самой крупной категории
        top = max(by_cat, key=by_cat.get)
        by_cat[top] += diff
    txs = []
    for cat, amount in by_cat.items():
        t = Transaction(user_id=user.id, kind="expense", amount=round(amount, 2), currency=user.currency,
                        category=cat, merchant=merchant, description=f"Чек {merchant or ''}".strip(),
                        occurred_at=purchased_at, source="receipt", receipt_id=r.id)
        session.add(t)
        txs.append(t)
    await session.commit()
    return r, txs


async def month_finance(session: AsyncSession, user: User, year: int | None = None, month: int | None = None) -> dict:
    start, end = local_month_bounds(user, year, month)
    rows = (await session.execute(
        select(Transaction.kind, Transaction.category, func.sum(Transaction.amount))
        .where(Transaction.user_id == user.id, Transaction.occurred_at >= start, Transaction.occurred_at < end)
        .group_by(Transaction.kind, Transaction.category)
    )).all()
    expenses = {c: round(s, 2) for k, c, s in rows if k == "expense"}
    incomes = {c: round(s, 2) for k, c, s in rows if k == "income"}
    spent = round(sum(expenses.values()), 2)
    budgets = (await session.scalars(select(Budget).where(Budget.user_id == user.id))).all()
    budget_status = []
    for b in budgets:
        used = spent if b.category is None else expenses.get(b.category, 0)
        budget_status.append({
            "id": b.id, "category": b.category or "Всего", "limit": b.monthly_limit,
            "spent": round(used, 2), "left": round(b.monthly_limit - used, 2),
            "percent": round(used / b.monthly_limit * 100) if b.monthly_limit else 0,
        })
    return {
        "period": start.astimezone(tz(user)).strftime("%Y-%m"),
        "spent": spent,
        "income": round(sum(incomes.values()), 2),
        "by_category": dict(sorted(expenses.items(), key=lambda x: -x[1])),
        "income_by_category": incomes,
        "budgets": budget_status,
    }


async def add_debt(session: AsyncSession, user: User, **kw) -> Debt:
    kw.setdefault("currency", user.currency)
    kw.setdefault("remaining", kw["amount"])
    d = Debt(user_id=user.id, **kw)
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return d


async def pay_debt(session: AsyncSession, user: User, debt: Debt, amount: float) -> Debt:
    session.add(DebtPayment(debt_id=debt.id, amount=amount))
    debt.remaining = round(max(debt.remaining - amount, 0), 2)
    debt.closed = debt.remaining <= 0
    await session.commit()
    await session.refresh(debt)
    return debt


def debt_dict(d: Debt) -> dict:
    data = to_dict(d)
    data["payments"] = [to_dict(p) for p in d.payments]
    return data


# ---------- Здоровье ----------
async def add_simple(session: AsyncSession, model, user: User, **kw):
    obj = model(user_id=user.id, **kw)
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


async def sync_medication_reminders(session: AsyncSession, user: User, med: Medication) -> None:
    """Пересоздаёт напоминания под расписание приёма лекарства."""
    await session.execute(delete(Reminder).where(Reminder.medication_id == med.id))
    if med.active:
        for t in med.times or []:
            r = Reminder(user_id=user.id, kind="medication", medication_id=med.id, time_of_day=t,
                         text=f"💊 Пора принять: {med.name}" + (f" — {med.dosage}" if med.dosage else ""))
            r.next_run_at = compute_next_run(r, user)
            session.add(r)
    await session.commit()


async def add_medication(session: AsyncSession, user: User, **kw) -> Medication:
    med = await add_simple(session, Medication, user, **kw)
    await sync_medication_reminders(session, user, med)
    return med


async def health_today(session: AsyncSession, user: User) -> dict:
    start, end = local_day_bounds(user)
    meals = (await session.scalars(
        select(Meal).where(Meal.user_id == user.id, Meal.eaten_at >= start, Meal.eaten_at < end)
        .order_by(Meal.eaten_at)
    )).all()
    totals = {k: round(sum(getattr(m, k) or 0 for m in meals)) for k in ("calories", "protein", "fat", "carbs")}
    meds = (await session.scalars(select(Medication).where(Medication.user_id == user.id, Medication.active))).all()
    logs = (await session.scalars(
        select(MedicationLog).where(MedicationLog.user_id == user.id, MedicationLog.taken_at >= start,
                                    MedicationLog.taken_at < end)
    )).all()
    taken = defaultdict(int)
    for lg in logs:
        if lg.status == "taken":
            taken[lg.medication_id] += 1
    weights = (await session.scalars(
        select(WeightEntry).where(WeightEntry.user_id == user.id).order_by(WeightEntry.measured_at.desc()).limit(30)
    )).all()
    return {
        "meals": [to_dict(m) for m in meals],
        "totals": totals,
        "calorie_goal": user.calorie_goal,
        "medications": [
            {"id": m.id, "name": m.name, "dosage": m.dosage, "times": m.times,
             "planned": len(m.times or []), "taken": taken.get(m.id, 0)}
            for m in meds
        ],
        "weights": [to_dict(w) for w in reversed(weights)],
        "weight_goal": user.weight_goal,
    }


# ---------- Тренировки ----------
async def fitness_week(session: AsyncSession, user: User) -> dict:
    today = now_local(user).date()
    monday = today - timedelta(days=today.weekday())
    start, _ = local_day_bounds(user, monday)
    workouts = (await session.scalars(
        select(Workout).where(Workout.user_id == user.id, Workout.performed_at >= start)
        .order_by(Workout.performed_at.desc())
    )).all()
    return {
        "count": len(workouts),
        "minutes": sum(w.duration_min or 0 for w in workouts),
        "calories": round(sum(w.calories or 0 for w in workouts)),
        "workouts": [to_dict(w) for w in workouts],
    }


# ---------- Напоминания ----------
async def add_reminder(session: AsyncSession, user: User, **kw) -> Reminder:
    r = Reminder(user_id=user.id, **kw)
    r.next_run_at = compute_next_run(r, user)
    session.add(r)
    await session.commit()
    await session.refresh(r)
    return r


# ---------- Сводка ----------
async def dashboard(session: AsyncSession, user: User) -> dict:
    start, end = local_day_bounds(user)
    spent_today = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user.id, Transaction.kind == "expense",
            Transaction.occurred_at >= start, Transaction.occurred_at < end)
    )
    debts = (await session.scalars(select(Debt).where(Debt.user_id == user.id, Debt.closed.is_(False)))).all()
    goals = (await session.scalars(select(Goal).where(Goal.user_id == user.id, Goal.done.is_(False)))).all()
    reminders = (await session.scalars(
        select(Reminder).where(Reminder.user_id == user.id, Reminder.active, Reminder.next_run_at.is_not(None),
                               Reminder.next_run_at < end + timedelta(days=1))
        .order_by(Reminder.next_run_at).limit(5)
    )).all()
    return {
        "user": {"first_name": user.first_name, "currency": user.currency, "timezone": user.timezone},
        "date": now_local(user).date().isoformat(),
        "finance": {
            "spent_today": round(spent_today or 0, 2),
            "month": await month_finance(session, user),
            "i_owe": round(sum(d.remaining for d in debts if d.direction == "i_owe"), 2),
            "owed_to_me": round(sum(d.remaining for d in debts if d.direction == "owed_to_me"), 2),
        },
        "health": await health_today(session, user),
        "fitness": await fitness_week(session, user),
        "goals": [to_dict(g) for g in goals],
        "upcoming": [to_dict(r) for r in reminders],
    }


async def snapshot_text(session: AsyncSession, user: User) -> str:
    """Краткое состояние пользователя для системного промпта Claude."""
    d = await dashboard(session, user)
    f, h, fit = d["finance"], d["health"], d["fitness"]
    cur = user.currency
    lines = [
        f"Потрачено сегодня: {f['spent_today']} {cur}; за месяц: {f['month']['spent']} {cur}, доход {f['month']['income']} {cur}.",
    ]
    for b in f["month"]["budgets"]:
        lines.append(f"Бюджет «{b['category']}»: {b['spent']}/{b['limit']} {cur} ({b['percent']}%).")
    if f["month"]["by_category"]:
        top = ", ".join(f"{k} {v}" for k, v in list(f["month"]["by_category"].items())[:5])
        lines.append(f"Топ расходов месяца: {top}.")
    if f["i_owe"] or f["owed_to_me"]:
        lines.append(f"Долги: я должен {f['i_owe']} {cur}, мне должны {f['owed_to_me']} {cur}.")
    t = h["totals"]
    lines.append(
        f"Питание сегодня: {t['calories']} ккал (Б{t['protein']}/Ж{t['fat']}/У{t['carbs']})"
        + (f", цель {h['calorie_goal']} ккал." if h["calorie_goal"] else ".")
    )
    for m in h["medications"]:
        lines.append(f"Лекарство {m['name']} (id={m['id']}): принято {m['taken']}/{m['planned']} сегодня.")
    if h["weights"]:
        w = h["weights"][-1]
        lines.append(f"Последний вес: {w['weight_kg']} кг ({w['measured_at'][:10]})"
                     + (f", цель {h['weight_goal']} кг." if h["weight_goal"] else "."))
    lines.append(f"Тренировок на этой неделе: {fit['count']}, {fit['minutes']} мин.")
    for g in d["goals"]:
        progress = f": {g['current_value'] or 0}/{g['target_value']} {g['unit'] or ''}".rstrip() if g["target_value"] else ""
        lines.append(f"Цель «{g['title']}» (id={g['id']}){progress}.")
    return "\n".join(lines)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
