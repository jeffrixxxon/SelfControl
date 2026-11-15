import asyncio
import logging
from collections.abc import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings

log = logging.getLogger(__name__)

_url = make_url(settings.db_url)
connect_args = {}
if _url.drivername.startswith("postgresql") and _url.host in ("db", "localhost", "127.0.0.1"):
    connect_args["ssl"] = False  # внутри docker-сети SSL не нужен
engine = create_async_engine(_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db(attempts: int = 30, delay: float = 2.0) -> None:
    from . import models  # noqa: F401  регистрирует таблицы

    where = f"{_url.drivername}://{_url.host or ''}:{_url.port or ''}/{_url.database}"
    for i in range(1, attempts + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("База подключена: %s", where)
            return
        except Exception as e:  # noqa: BLE001
            if i == attempts:
                log.error("Не удалось подключиться к базе %s: %s", where, e)
                raise
            log.warning("База %s недоступна (%s), попытка %d/%d…", where, e.__class__.__name__, i, attempts)
            await asyncio.sleep(delay)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
