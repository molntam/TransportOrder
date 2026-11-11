from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from .domain import active_sources
from .local_time import local_to_utc, display_time

LIMITS = {"S1": 4, "I1": 4, "S2": 2, "I8": 2, "S4": 0, "I2": 0}


def changed_at(day, clock):
    day, clock = str(day if day is not None else "").strip(), str(clock if clock is not None else "").strip()
    if not day or not clock:
        return None
    try:
        if len(day) == 8 and day.isdigit():
            raise InvalidOperation
        number = Decimal(day)
        if not number.is_finite() or not 1 <= number <= 2958465:
            return None
        date = datetime(1899, 12, 30) + timedelta(days=float(number))
    except (InvalidOperation, OverflowError):
        date = None
        for pattern in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y%m%d"):
            try:
                date = datetime.strptime(day, pattern)
                break
            except ValueError:
                pass
        if date is None:
            return None
    try:
        fraction = Decimal(clock)
        if fraction.is_finite() and 0 <= fraction < 1:
            seconds = round(float(fraction) * 86400)
            if seconds >= 86400:
                seconds = 86399
            time = (datetime.min + timedelta(seconds=seconds)).time()
        else:
            time = datetime.strptime(clock.zfill(6), "%H%M%S").time()
    except (InvalidOperation, ValueError):
        time = None
        for pattern in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
            try:
                time = datetime.strptime(clock, pattern).time()
                break
            except ValueError:
                pass
        if time is None:
            return None
    return local_to_utc(datetime.combine(date.date(), time))


def fifo_status(state, moment=None):
    moment = moment or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    collected = {p["id"] for p in state["pallets"] if p.get("collectedAt")}
    departed = {l.get("hu") for f in state["forms"] if f.get("palletId") in collected for l in f["lines"]}
    assigned = {l.get("hu") for f in state['forms'] if f.get('palletId') and not f.get('removedAt') for l in f['lines']}
    latest = {}
    for row in (active_sources(state).get("shipto") or {}).get("rows", []):
        condition, bin_name = str(row.get("condition", "")).strip().upper(), str(row.get("bin", "")).strip().upper()
        if row.get("hu") in departed:
            continue
        at = changed_at(row.get("changedOn"), row.get("changedAt"))
        key = (row.get("hu"), row.get("dn"), bin_name)
        previous = latest.get(key)
        if previous is None or (at and (previous[1] is None or at > previous[1])):
            latest[key] = (row, at)
    alerts, pending, missing, not_counted = [], [], [], []
    for row, at in latest.values():
        condition = str(row.get('condition', '')).strip().upper()
        limit = LIMITS.get(condition)
        monitored = limit is not None and str(row.get('bin', '')).strip().upper() in ({'PS_READY-INT','INTER-IN'} if limit == 0 else {'PS_READY-INT'})
        if not monitored and row.get('hu') in assigned:
            continue
        age = max(0, (moment - at).total_seconds() / 3600) if at else None
        item = {"dn": row.get("dn", ""), "hu": row.get("hu", ""), "bin": row.get("bin", ""),
                "condition": row["condition"], "limitHours": limit, "ageHours": round(age, 2) if age is not None else None,
                "changedAt": at.isoformat() if at else None, "changedDisplay": display_time(at.isoformat()) if at else "Missing SAP timestamp",
                "shipTo": row.get('shipTo', ''), "emergency": monitored and limit == 0}
        if not monitored:
            item.update(ageHours=None, limitHours=None)
            not_counted.append(item)
        elif limit == 0 or (age is not None and age >= limit):
            alerts.append(item)
        elif at is None:
            missing.append(item)
        else:
            pending.append(item)
    alerts.sort(key=lambda x: (not x["emergency"], -(x["ageHours"] or 0), x["dn"]))
    messages = []
    for limit in (0, 2, 4):
        dns = sorted({r["dn"] or "HU " + r["hu"] for r in alerts if r["limitHours"] == limit})
        if dns:
            text = (f"There is an emergency order(s) {', '.join(dns)}. Please process ASAP." if limit == 0 else
                    f"Warning, these deliveries {', '.join(dns)} are stagnant for more than {limit} hours on PS_READY-INT. Please take action.")
            messages.append({"emergency": limit == 0, "text": text, "dns": dns})
    return {"alerts": alerts, "pending": pending, "missing": missing, "notCounted": not_counted, "messages": messages,
            "checkedAt": moment.isoformat(), "timeBasis": "SAP Changed On / Changed At · Europe/Amsterdam"}
