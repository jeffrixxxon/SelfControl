"""Авторизация мини-аппа по Telegram initData (HMAC-подпись токеном бота)."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import get_session
from .models import User

INIT_DATA_TTL = 24 * 3600


def validate_init_data(init_data: str, bot_token: str) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("no hash")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise ValueError("bad hash")
    if time.time() - int(pairs.get("auth_date", 0)) > INIT_DATA_TTL:
        raise ValueError("expired")
    return json.loads(pairs.get("user", "{}"))


async def get_or_create_user(
    session: AsyncSession, tg_id: int, first_name: str | None = None, username: str | None = None
) -> User:
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if user is None:
        user = User(
            tg_id=tg_id,
            first_name=first_name,
            username=username,
            timezone=settings.default_timezone,
            currency=settings.default_currency,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    elif first_name and (user.first_name != first_name or user.username != username):
        user.first_name, user.username = first_name, username
        await session.commit()
    return user


def is_allowed(tg_id: int) -> bool:
    return not settings.allowed_ids or tg_id in settings.allowed_ids


async def current_user(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not x_telegram_init_data:
        if settings.debug and settings.dev_tg_id:
            return await get_or_create_user(session, settings.dev_tg_id, "Dev")
        raise HTTPException(401, "Откройте приложение из Telegram")
    try:
        tg_user = validate_init_data(x_telegram_init_data, settings.bot_token)
    except ValueError as e:
        raise HTTPException(401, f"initData: {e}")
    tg_id = int(tg_user["id"])
    if not is_allowed(tg_id):
        raise HTTPException(403, "Доступ закрыт")
    return await get_or_create_user(session, tg_id, tg_user.get("first_name"), tg_user.get("username"))
