from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Reminder, User


def tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except Exception:
        return ZoneInfo("Europe/Moscow")


def aware(dt: datetime | None) -> datetime | None:
    """SQLite возвращает naive datetime — считаем его UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def now_local(user: User) -> datetime:
    return datetime.now(tz(user))


def local_day_bounds(user: User, day: date | None = None) -> tuple[datetime, datetime]:
    """Начало и конец суток пользователя в UTC."""
    z = tz(user)
    day = day or now_local(user).date()
    start = datetime.combine(day, time.min, tzinfo=z)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def local_month_bounds(user: User, year: int | None = None, month: int | None = None) -> tuple[datetime, datetime]:
    z = tz(user)
    today = now_local(user)
    y, m = year or today.year, month or today.month
    start = datetime(y, m, 1, tzinfo=z)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=z)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def parse_local(user: User, value: str | None) -> datetime:
    """'2026-11-15 14:30' / ISO-строка / None → UTC datetime. Без зоны — время пользователя."""
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz(user))
    return dt.astimezone(timezone.utc)


def compute_next_run(reminder: Reminder, user: User, after: datetime | None = None) -> datetime | None:
    """Следующий момент срабатывания напоминания (UTC) или None, если больше не сработает."""
    after = aware(after) or datetime.now(timezone.utc)
    if reminder.run_at and not reminder.time_of_day:
        run_at = aware(reminder.run_at)
        return run_at if run_at > after else None
    if not reminder.time_of_day:
        return None
    z = tz(user)
    hh, mm = (int(x) for x in reminder.time_of_day.split(":"))
    local_after = after.astimezone(z)
    days = set(reminder.days_of_week or [])
    for offset in range(0, 8):
        d = local_after.date() + timedelta(days=offset)
        if days and d.weekday() not in days:
            continue
        candidate = datetime.combine(d, time(hh, mm), tzinfo=z)
        if candidate > local_after:
            return candidate.astimezone(timezone.utc)
    return None
