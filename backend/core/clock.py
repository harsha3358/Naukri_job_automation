from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC. SQLite drops tzinfo, so everything is stored and compared as naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def start_of_local_day_utc() -> datetime:
    """Midnight today in the PC's timezone, as naive UTC. Daily caps reset at local midnight."""
    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)


def to_local(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone()
