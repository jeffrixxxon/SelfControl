from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import current_user
from ..db import get_session
from ..models import ChatMessage, User
from ..services import assistant, core
from ..services.assistant import Attachment
from ..services.transcribe import transcribe

router = APIRouter()

ALLOWED_UPLOADS = {"image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf"}


class ProfileIn(BaseModel):
    timezone: str | None = None
    currency: str | None = None
    calorie_goal: int | None = None
    weight_goal: float | None = None
    height_cm: float | None = None
    daily_report_enabled: bool | None = None
    daily_report_time: str | None = None
    about: str | None = None

    @field_validator("timezone")
    @classmethod
    def check_tz(cls, v):
        if v:
            ZoneInfo(v)
        return v


class ChatIn(BaseModel):
    message: str


def profile(user: User) -> dict:
    d = core.to_dict(user)
    d.pop("last_report_date", None)
    return d


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return profile(user)


@router.put("/me")
async def update_me(data: ProfileIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(user, k, v)
    await session.commit()
    return profile(user)


@router.get("/dashboard")
async def dashboard(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await core.dashboard(session, user)


@router.get("/ai/history")
async def history(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = (await session.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id)
                                  .order_by(ChatMessage.id.desc()).limit(50))).all()
    return [{"role": m.role, "content": m.content, "created_at": core.to_dict(m)["created_at"]} for m in reversed(rows)]


@router.delete("/ai/history")
async def clear_history(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await session.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    await session.commit()
    return {"ok": True}


@router.post("/ai/chat")
async def chat(data: ChatIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    res = await assistant.run_agent(session, user, data.message)
    return {"reply": res.text, "actions": [a["tool"] for a in res.actions]}


@router.post("/ai/upload")
async def upload(file: UploadFile = File(...), message: str = Form(""), user: User = Depends(current_user),
                 session: AsyncSession = Depends(get_session)):
    """Фото чека/документ/голос из мини-аппа."""
    data = await file.read()
    ctype = (file.content_type or "").lower()
    if ctype.startswith("audio/"):
        text = await transcribe(data, file.filename or "voice.webm")
        res = await assistant.run_agent(session, user, text, source="voice")
        return {"transcript": text, "reply": res.text, "actions": [a["tool"] for a in res.actions]}
    if ctype not in ALLOWED_UPLOADS:
        raise HTTPException(415, "Поддерживаются изображения, PDF и аудио")
    if ctype.startswith("image/") and len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Изображение больше 5 МБ")
    res = await assistant.run_agent(session, user, message or "Разбери вложение: если это чек — сохрани его.",
                                    [Attachment(data, ctype, file.filename)], source="receipt")
    return {"reply": res.text, "actions": [a["tool"] for a in res.actions]}
