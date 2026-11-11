import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .printing import render_document


def public_snapshot(value):
    if isinstance(value, list):
        return [public_snapshot(item) for item in value]
    if isinstance(value, dict):
        return {key: public_snapshot(item) for key, item in value.items()
                if key not in {"handoffToken", "handoffPublished", "driverToken", "url", "versions"}}
    return value


def local_day(value=None):
    moment = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        return moment.astimezone(ZoneInfo('Europe/Amsterdam')).date().isoformat()
    except Exception:
        def transition(month):
            end = datetime(moment.year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
            return (end - timedelta(days=(end.weekday()+1)%7)).replace(hour=1)
        summer = transition(3) <= moment.astimezone(timezone.utc) < transition(10)
        return (moment.astimezone(timezone.utc)+timedelta(hours=2 if summer else 1)).date().isoformat()


def archive_document(store, state, document):
    kind, identifier, revision = document['kind'], document['id'], document['revision']
    record = next(r for r in state[{'form':'forms','pallet':'pallets','load':'loads'}[kind]] if r['id']==identifier)
    version = next(v for v in record['versions'] if v['revision']==revision)
    snapshot = copy.deepcopy(version)
    snapshot.update({'id': identifier, 'revision': revision})
    if record.get('online'):
        snapshot['online'] = copy.deepcopy(record['online'])
    snapshot = public_snapshot(snapshot)
    folder = store.directory / 'archive' / 'documents'
    folder.mkdir(parents=True, exist_ok=True)
    stem = f'{kind}-{identifier}-r{revision}' + ('-online' if record.get('online') else '')
    html = folder / (stem+'.html')
    if not html.exists():
        html.write_text(render_document(state,kind,identifier,revision),encoding='utf-8')
    outbox = store.directory / 'archive' / 'outbox'
    outbox.mkdir(parents=True,exist_ok=True)
    target = outbox / (stem+'.json')
    completed = store.directory / 'archive' / 'uploaded' / target.name
    if not completed.exists():
        temporary = target.with_suffix('.tmp')
        temporary.write_text(json.dumps({'kind':kind,'id':identifier,'revision':revision,'snapshot':snapshot}),encoding='utf-8')
        temporary.replace(target)
