"""Модели данных SelfControl. Все записи привязаны к пользователю (user_id)."""
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserOwned(TimestampMixin):
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)


# ---------- Пользователь ----------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    calorie_goal: Mapped[int | None] = mapped_column(Integer)
    weight_goal: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    # Вечерний разбор дня от Claude
    daily_report_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_report_time: Mapped[str] = mapped_column(String(5), default="21:00")
    last_report_date: Mapped[date | None] = mapped_column(Date)
    # Что пользователь рассказал о себе — Claude учитывает это в ответах
    about: Mapped[str | None] = mapped_column(Text)


# ---------- Финансы ----------
class Transaction(UserOwned, Base):
    __tablename__ = "transactions"

    kind: Mapped[str] = mapped_column(String(16), default="expense")  # expense | income
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    category: Mapped[str] = mapped_column(String(64), default="Прочее")
    description: Mapped[str | None] = mapped_column(String(512))
    merchant: Mapped[str | None] = mapped_column(String(256))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")  # manual|ai|voice|receipt
    receipt_id: Mapped[int | None] = mapped_column(ForeignKey("receipts.id", ondelete="SET NULL"))


class Receipt(UserOwned, Base):
    __tablename__ = "receipts"

    merchant: Mapped[str | None] = mapped_column(String(256))
    total: Mapped[float] = mapped_column(Float, default=0)
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list] = mapped_column(JSON, default=list)  # [{name, qty, price, total, category}]
    tg_file_id: Mapped[str | None] = mapped_column(String(256))


class Budget(UserOwned, Base):
    __tablename__ = "budgets"

    category: Mapped[str | None] = mapped_column(String(64))  # None = общий бюджет на месяц
    monthly_limit: Mapped[float] = mapped_column(Float)


class Debt(UserOwned, Base):
    __tablename__ = "debts"

    direction: Mapped[str] = mapped_column(String(16))  # i_owe | owed_to_me
    counterparty: Mapped[str] = mapped_column(String(128))
    amount: Mapped[float] = mapped_column(Float)
    remaining: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    due_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(512))
    closed: Mapped[bool] = mapped_column(Boolean, default=False)

    payments: Mapped[list["DebtPayment"]] = relationship(
        back_populates="debt", cascade="all, delete-orphan", lazy="selectin"
    )


class DebtPayment(TimestampMixin, Base):
    __tablename__ = "debt_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    debt_id: Mapped[int] = mapped_column(ForeignKey("debts.id", ondelete="CASCADE"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    debt: Mapped[Debt] = relationship(back_populates="payments")


# ---------- Здоровье ----------
class Meal(UserOwned, Base):
    __tablename__ = "meals"

    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    meal_type: Mapped[str | None] = mapped_column(String(16))  # breakfast|lunch|dinner|snack
    description: Mapped[str] = mapped_column(String(512))
    calories: Mapped[float | None] = mapped_column(Float)
    protein: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)


class Medication(UserOwned, Base):
    __tablename__ = "medications"

    name: Mapped[str] = mapped_column(String(128))
    dosage: Mapped[str | None] = mapped_column(String(128))
    times: Mapped[list] = mapped_column(JSON, default=list)  # ["09:00", "21:00"]
    notes: Mapped[str | None] = mapped_column(String(512))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class MedicationLog(UserOwned, Base):
    __tablename__ = "medication_logs"

    medication_id: Mapped[int] = mapped_column(ForeignKey("medications.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="taken")  # taken | skipped
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class WeightEntry(UserOwned, Base):
    __tablename__ = "weights"

    weight_kg: Mapped[float] = mapped_column(Float)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    note: Mapped[str | None] = mapped_column(String(256))


# ---------- Тренировки и цели ----------
class Workout(UserOwned, Base):
    __tablename__ = "workouts"

    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    type: Mapped[str] = mapped_column(String(64))  # Силовая, Бег, Йога...
    duration_min: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[float | None] = mapped_column(Float)
    exercises: Mapped[list] = mapped_column(JSON, default=list)  # [{name, sets, reps, weight}]
    notes: Mapped[str | None] = mapped_column(String(512))


class Goal(UserOwned, Base):
    __tablename__ = "goals"

    title: Mapped[str] = mapped_column(String(256))
    area: Mapped[str] = mapped_column(String(16), default="other")  # finance|health|fitness|other
    target_value: Mapped[float | None] = mapped_column(Float)
    current_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    deadline: Mapped[date | None] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------- Напоминания ----------
class Reminder(UserOwned, Base):
    __tablename__ = "reminders"

    text: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(16), default="custom")  # custom|medication|workout|motivation
    # Повторяющееся: time_of_day + days_of_week (0=Пн … 6=Вс, пусто = каждый день)
    time_of_day: Mapped[str | None] = mapped_column(String(5))
    days_of_week: Mapped[list] = mapped_column(JSON, default=list)
    # Разовое: run_at
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    medication_id: Mapped[int | None] = mapped_column(ForeignKey("medications.id", ondelete="CASCADE"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------- Диалог с Claude ----------
class ChatMessage(UserOwned, Base):
    __tablename__ = "chat_messages"

    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
