import copy
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from .domain import InputError, event, find, now, uid, route_key


def building_key(value):
    return ' '.join(str(value).split()).casefold()


def reserved_ids(state):
    return {p['id'] for load in state.get('loads', []) if load['status'] == 'ready'
            for p in load['pallets']}


def ready_pallets(state, building):
    reserved = reserved_ids(state)
    return [p for p in state['pallets'] if p['status'] == 'finalised'
            and not p.get('collectedAt') and p['id'] not in reserved
            and building_key(p['destination']['building']) == building_key(building)]


def validate_slots(slots):
    if not isinstance(slots, list) or len(slots) > 200:
        raise InputError('Use at most 200 dock slots.')
    result = []
    for slot in slots:
        building = str(slot.get('building', '')).strip()[:300]
        days = slot.get('days', [])
        start, end = str(slot.get('start', '')), str(slot.get('end', ''))
        if not building or not days or any(type(d) is not int or d not in range(5) for d in days):
            raise InputError('Choose a building and at least one weekday for each slot.')
        if not all(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in (start, end)) or end <= start:
            raise InputError('Dock slots need start/end times on the same day, with end after start.')
        result.append({'id': str(slot.get('id') or uid('DOCK'))[:100], 'building': building,
                       'days': sorted(set(days)), 'start': start, 'end': end})
    return result


def dock_reminders(state, local_time):
    reminders = []
    for slot in state['settings'].get('dockSlots', []):
        if local_time.weekday() not in slot['days']:
            continue
        start = local_time.replace(hour=int(slot['start'][:2]), minute=int(slot['start'][3:]), second=0, microsecond=0)
        end = local_time.replace(hour=int(slot['end'][:2]), minute=int(slot['end'][3:]), second=0, microsecond=0)
        if not start - timedelta(minutes=20) <= local_time <= end:
            continue
        building = slot['building']
        open_count = sum(p['status'] == 'open' and building_key(p['destination']['building']) == building_key(building) for p in state['pallets'])
        ready_count = len(ready_pallets(state, building))
        if open_count or ready_count:
            reminders.append({**slot, 'key': f"{slot['id']}:{local_time.date()}",
                              'open': open_count, 'ready': ready_count})
    return reminders


def scan_identity(value):
    value = str(value).strip()
    if len(value) > 2000:
        raise InputError('Unrecognised QR code.')
    if '://' in value:
        value = parse_qs(urlsplit(value).fragment).get('scan', [''])[0]
    match = re.fullmatch(r'TO:(PALLET|LOAD):([A-Z0-9-]+):(\d+)', value)
    if not match:
        raise InputError('Scan a TransportOrder pallet or loading manifest QR code.')
    return match[1], match[2], int(match[3])


def apply_load_action(state, action, payload):
    state.setdefault('loads', [])
    if action == 'create_load':
        building = str(payload.get('building', '')).strip()
        pallets = ready_pallets(state, building)
        if not pallets:
            raise InputError('No unassigned ready pallets for this building. Finalise the pallets first.')
        origins = {route_key(p['versions'][-1]['forms'][0]['origin']) for p in pallets}
        if len(origins) > 1:
            raise InputError('These pallets have different origins. Prepare separate loads before combining them.')
        timestamp = now()
        load = {'id': uid('LOAD'), 'revision': 1, 'status': 'ready', 'building': pallets[0]['destination']['building'],
                'createdAt': timestamp, 'updatedAt': timestamp, 'preparedBy': state['settings']['preparedBy'],
                'pallets': [{'id': p['id'], 'revision': p['revision'], 'destination': copy.deepcopy(p['destination']),
                            'forms': copy.deepcopy(p['versions'][-1]['forms'])} for p in pallets],
                'scans': [], 'driver': '', 'vehicle': '', 'reason': '', 'versions': []}
        load['versions'].append(copy.deepcopy({k: v for k, v in load.items() if k != 'versions'}))
        state['loads'].append(load)
        event(state, 'Loading manifest created', load['id'], f"{load['building']}; {len(pallets)} pallets")
        return {'loadId': load['id'], 'print': {'kind': 'load', 'id': load['id'], 'revision': 1}}
    load = find(state, 'loads', payload.get('id'))
    if load['status'] != 'ready':
        raise InputError('This load is already closed. Its loading record is read-only.')
    if action == 'scan_load':
        kind, pallet_id, revision = scan_identity(payload.get('code', ''))
        if kind != 'PALLET':
            raise InputError('The manifest is open. Now scan a pallet QR code.')
        pallet = find(state, 'pallets', pallet_id)
        if building_key(pallet['destination']['building']) != building_key(load['building']):
            raise InputError(f"Wrong destination: {pallet_id} is for {pallet['destination']['building']}, not {load['building']}.")
        expected = next((p for p in load['pallets'] if p['id'] == pallet_id), None)
        if not expected:
            raise InputError('This pallet is not included in this manifest. Use the correct load.')
        if revision != expected['revision'] or revision != pallet['revision'] or pallet['status'] != 'finalised':
            raise InputError('Superseded pallet QR. Use the current finalised document.')
        if any(s['palletId'] == pallet_id for s in load['scans']):
            return {'duplicate': True, 'count': len(load['scans'])}
        load['scans'].append({'palletId': pallet_id, 'at': now()})
        load['updatedAt'] = now()
        event(state, 'Pallet scanned for loading', load['id'], pallet_id)
        return {'count': len(load['scans'])}
    if action == 'unscan_load':
        pallet_id = payload.get('palletId')
        reason = str(payload.get('reason', '')).strip()[:1000]
        if not reason or not any(s['palletId'] == pallet_id for s in load['scans']):
            raise InputError('Choose a scanned pallet and explain why it is being unloaded.')
        load['scans'] = [s for s in load['scans'] if s['palletId'] != pallet_id]
        load['updatedAt'] = now()
        event(state, 'Pallet removed from loading', load['id'], pallet_id + ': ' + reason)
        return {}
    reason = str(payload.get('reason', '')).strip()[:1000]
    if action == 'cancel_load':
        if not reason:
            raise InputError('Enter a reason to cancel this manifest.')
        load.update(status='cancelled', updatedAt=now(), reason=reason)
        event(state, 'Loading manifest cancelled', load['id'], reason)
        return {}
    if action == 'complete_load':
        scanned = {s['palletId'] for s in load['scans']}
        driver, vehicle = (str(payload.get(k, '')).strip()[:200] for k in ('driver', 'vehicle'))
        if not driver or not vehicle:
            raise InputError('Enter driver name and vehicle registration for traceability.')
        if not scanned:
            raise InputError('Scan at least one pallet, or cancel the manifest.')
        if len(scanned) < len(load['pallets']) and not reason:
            raise InputError('Explain why this is a partial pickup.')
        for item in load['pallets']:
            if item['id'] in scanned:
                pallet = find(state, 'pallets', item['id'])
                if pallet['status'] != 'finalised' or pallet['revision'] != item['revision'] or pallet.get('collectedAt'):
                    raise InputError('A scanned pallet has changed. Refresh and check the load.')
                pallet.update(collectedAt=now(), collectedLoadId=load['id'], updatedAt=now())
        load.update(status='collected' if len(scanned) == len(load['pallets']) else 'partial',
                    updatedAt=now(), completedAt=now(), driver=driver, vehicle=vehicle, reason=reason)
        event(state, 'Load pickup confirmed', load['id'], f"{len(scanned)}/{len(load['pallets'])} pallets; {driver}; {vehicle}; {reason}")
        return {}
    raise InputError('Unknown loading action.')
