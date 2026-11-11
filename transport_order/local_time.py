from datetime import datetime, timedelta, timezone


def amsterdam(moment):
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo("Europe/Amsterdam"))
    except (ImportError, KeyError):
        utc = moment.astimezone(timezone.utc)
        def transition(month):
            end = datetime(utc.year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
            return (end - timedelta(days=(end.weekday() + 1) % 7)).replace(hour=1)
        offset = 2 if transition(3) <= utc < transition(10) else 1
        return utc.astimezone(timezone(timedelta(hours=offset)))


def local_to_utc(moment):
    try:
        from zoneinfo import ZoneInfo
        return moment.replace(tzinfo=ZoneInfo("Europe/Amsterdam")).astimezone(timezone.utc)
    except (ImportError, KeyError):
        candidate = moment.replace(tzinfo=timezone.utc) - timedelta(hours=1)
        return moment.replace(tzinfo=amsterdam(candidate).tzinfo).astimezone(timezone.utc)


def display_time(value):
    if not value:
        return ""
    try:
        return amsterdam(datetime.fromisoformat(value.replace("Z", "+00:00"))).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, AttributeError):
        return str(value)
