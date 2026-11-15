import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user
from ..db import get_session
from ..models import Goal, Reminder, User, Workout
from ..services import core
from ..timeutils import compute_next_run, parse_local

router = APIRouter(tags=["fitness"])


class WorkoutIn(BaseModel):
    type: str
    duration_min: int | None = None
    calories: float | None = None
    exercises: list[dict] = []
    notes: str | None = None
    performed_at: str | None = None


class GoalIn(BaseModel):
    title: str
    area: str = "other"
    target_value: float | None = None
    current_value: float | None = None
    unit: str | None = None
    deadline: date | None = None
    done: bool = False


class ReminderIn(BaseModel):
    text: str
    kind: str = "custom"
    time_of_day: str | None = None
    days_of_week: list[int] = []
    run_at: str | None = None
    active: bool = True

    @field_validator("time_of_day")
    @classmethod
    def check_time(cls, v):
        if v and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("время в формате ЧЧ:ММ")
        return v


@router.get("/fitness/week")
async def week(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await core.fitness_week(session, user)


@router.get("/workouts")
async def list_workouts(limit: int = 50, user: User = Depends(current_user),
                        session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(Workout).where(Workout.user_id == user.id)
                                  .order_by(Workout.performed_at.desc()).limit(limit))).all()
    return [core.to_dict(w) for w in rows]


@router.post("/workouts")
async def create_workout(data: WorkoutIn, user: User = Depends(current_user),
                         session: AsyncSession = Depends(get_session)):
    payload = data.model_dump()
    payload["performed_at"] = parse_local(user, data.performed_at)
    return core.to_dict(await core.add_simple(session, Workout, user, **payload))


@router.delete("/workouts/{w_id}")
async def delete_workout(w_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    w = await core.get_owned(session, Workout, user, w_id)
    if not w:
        raise HTTPException(404)
    await session.delete(w)
    await session.commit()
    return {"ok": True}


@router.get("/goals")
async def list_goals(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(Goal).where(Goal.user_id == user.id)
                                  .order_by(Goal.done, Goal.deadline))).all()
    return [core.to_dict(g) for g in rows]


@router.post("/goals")
async def create_goal(data: GoalIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return core.to_dict(await core.add_simple(session, Goal, user, **data.model_dump()))


@router.put("/goals/{goal_id}")
async def update_goal(goal_id: int, data: GoalIn, user: User = Depends(current_user),
                      session: AsyncSession = Depends(get_session)):
    g = await core.get_owned(session, Goal, user, goal_id)
    if not g:
        raise HTTPException(404)
    for k, v in data.model_dump().items():
        setattr(g, k, v)
    await session.commit()
    return core.to_dict(g)


@router.delete("/goals/{goal_id}")
async def delete_goal(goal_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    g = await core.get_owned(session, Goal, user, goal_id)
    if not g:
        raise HTTPException(404)
    await session.delete(g)
    await session.commit()
    return {"ok": True}


# ---------- Напоминания ----------
@router.get("/reminders")
async def list_reminders(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(Reminder).where(Reminder.user_id == user.id)
                                  .order_by(Reminder.active.desc(), Reminder.next_run_at))).all()
    return [core.to_dict(r) for r in rows]


@router.post("/reminders")
async def create_reminder(data: ReminderIn, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    if not data.time_of_day and not data.run_at:
        raise HTTPException(422, "Укажите время (time_of_day) или дату (run_at)")
    payload = data.model_dump()
    payload["run_at"] = parse_local(user, data.run_at) if data.run_at else None
    return core.to_dict(await core.add_reminder(session, user, **payload))


@router.put("/reminders/{r_id}")
async def update_reminder(r_id: int, data: ReminderIn, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    r = await core.get_owned(session, Reminder, user, r_id)
    if not r:
        raise HTTPException(404)
    payload = data.model_dump()
    payload["run_at"] = parse_local(user, data.run_at) if data.run_at else None
    for k, v in payload.items():
        setattr(r, k, v)
    r.next_run_at = compute_next_run(r, user) if r.active else None
    await session.commit()
    return core.to_dict(r)


@router.delete("/reminders/{r_id}")
async def delete_reminder(r_id: int, user: User = Depends(current_user),
                          session: AsyncSession = Depends(get_session)):
    r = await core.get_owned(session, Reminder, user, r_id)
    if not r:
        raise HTTPException(404)
    await session.delete(r)
    await session.commit()
    return {"ok": True}
