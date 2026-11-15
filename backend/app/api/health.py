from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user
from ..db import get_session
from ..models import Meal, Medication, MedicationLog, User, WeightEntry
from ..services import core
from ..timeutils import local_day_bounds, now_local, parse_local

router = APIRouter(tags=["health"])

TIME_RE = r"^([01]\d|2[0-3]):[0-5]\d$"


class MealIn(BaseModel):
    description: str
    meal_type: str | None = None
    calories: float | None = None
    protein: float | None = None
    fat: float | None = None
    carbs: float | None = None
    eaten_at: str | None = None


class MedicationIn(BaseModel):
    name: str
    dosage: str | None = None
    times: list[str] = []
    notes: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    active: bool = True

    @field_validator("times")
    @classmethod
    def check_times(cls, v):
        import re
        for t in v:
            if not re.match(TIME_RE, t):
                raise ValueError(f"время {t} должно быть в формате ЧЧ:ММ")
        return sorted(set(v))


class MedLogIn(BaseModel):
    status: str = Field("taken", pattern="^(taken|skipped)$")


class WeightIn(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)
    measured_at: str | None = None
    note: str | None = None


@router.get("/health/today")
async def today(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await core.health_today(session, user)


@router.get("/meals")
async def list_meals(day: date | None = None, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    start, end = local_day_bounds(user, day)
    rows = (await session.scalars(select(Meal).where(Meal.user_id == user.id, Meal.eaten_at >= start,
                                                     Meal.eaten_at < end).order_by(Meal.eaten_at))).all()
    return [core.to_dict(m) for m in rows]


@router.post("/meals")
async def create_meal(data: MealIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    payload = data.model_dump()
    payload["eaten_at"] = parse_local(user, data.eaten_at)
    return core.to_dict(await core.add_simple(session, Meal, user, **payload))


@router.delete("/meals/{meal_id}")
async def delete_meal(meal_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    m = await core.get_owned(session, Meal, user, meal_id)
    if not m:
        raise HTTPException(404)
    await session.delete(m)
    await session.commit()
    return {"ok": True}


@router.get("/medications")
async def list_meds(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(Medication).where(Medication.user_id == user.id)
                                  .order_by(Medication.active.desc(), Medication.name))).all()
    return [core.to_dict(m) for m in rows]


@router.post("/medications")
async def create_med(data: MedicationIn, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    return core.to_dict(await core.add_medication(session, user, **data.model_dump()))


@router.put("/medications/{med_id}")
async def update_med(med_id: int, data: MedicationIn, user: User = Depends(current_user),
                     session: AsyncSession = Depends(get_session)):
    m = await core.get_owned(session, Medication, user, med_id)
    if not m:
        raise HTTPException(404)
    for k, v in data.model_dump().items():
        setattr(m, k, v)
    await session.commit()
    await core.sync_medication_reminders(session, user, m)
    return core.to_dict(m)


@router.delete("/medications/{med_id}")
async def delete_med(med_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    m = await core.get_owned(session, Medication, user, med_id)
    if not m:
        raise HTTPException(404)
    await session.delete(m)
    await session.commit()
    return {"ok": True}


@router.post("/medications/{med_id}/log")
async def log_med(med_id: int, data: MedLogIn, user: User = Depends(current_user),
                  session: AsyncSession = Depends(get_session)):
    m = await core.get_owned(session, Medication, user, med_id)
    if not m:
        raise HTTPException(404)
    lg = await core.add_simple(session, MedicationLog, user, medication_id=m.id, status=data.status)
    return core.to_dict(lg)


@router.get("/medications/history")
async def med_history(days: int = 14, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    start, _ = local_day_bounds(user, now_local(user).date() - timedelta(days=days - 1))
    rows = (await session.scalars(select(MedicationLog).where(MedicationLog.user_id == user.id,
                                                              MedicationLog.taken_at >= start)
                                  .order_by(MedicationLog.taken_at.desc()))).all()
    return [core.to_dict(r) for r in rows]


@router.get("/weights")
async def list_weights(limit: int = 90, user: User = Depends(current_user),
                       session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(WeightEntry).where(WeightEntry.user_id == user.id)
                                  .order_by(WeightEntry.measured_at.desc()).limit(limit))).all()
    return [core.to_dict(w) for w in reversed(rows)]


@router.post("/weights")
async def create_weight(data: WeightIn, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    payload = data.model_dump()
    payload["measured_at"] = parse_local(user, data.measured_at)
    return core.to_dict(await core.add_simple(session, WeightEntry, user, **payload))


@router.delete("/weights/{w_id}")
async def delete_weight(w_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    w = await core.get_owned(session, WeightEntry, user, w_id)
    if not w:
        raise HTTPException(404)
    await session.delete(w)
    await session.commit()
    return {"ok": True}
