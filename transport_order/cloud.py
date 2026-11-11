import copy
import json
import re
import os
from pathlib import Path
import threading
import time
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .device_key import protect
from .domain import InputError, find, event

URL = 'https://cwwpuapvgwoelhpwserm.supabase.co'
KEY = 'sb_publishable_vrv6VwGmtlhnSqX2q2F20g_HO4vdj2R'
WORKSPACE = '111fb839-a913-4c34-ae02-1c1228f35f9c'
SITE = 'https://molntam.github.io/TransportOrder/'


class Cloud:
    def __init__(self, directory=None):
        self.key_path = Path(directory) / "publisher-key" if directory else None
        self.device_token = protect(self.key_path.read_text().strip(), decrypt=True) if self.key_path and self.key_path.exists() else None
        self.session = None
        self.lock = threading.RLock()

    def request(self, path, body=None, authenticated=True, access_token=None):
        headers = {'apikey': KEY, 'Content-Type': 'application/json'}
        if access_token:
            headers['Authorization'] = 'Bearer ' + access_token
        elif authenticated:
            raise InputError('Use workstation pairing from the tracking website, then Settings → Pair workstation.')
        request = Request(URL + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise InputError('Online access denied. Check your sign-in and workspace operator membership.') from None
            raise InputError('The online operation was rejected. Refresh online status before retrying; check that these pallets are not already reserved.') from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise InputError('Online response could not be confirmed. No automatic retry was made. Retry publishing to reconcile the saved cloud records.') from None

    def login(self, email, password):
        session = self.request('/auth/v1/token?grant_type=password',
                               {'email': email.strip(), 'password': password}, False)
        device = self.request('/rest/v1/rpc/transport_pair_device',
                              {'p_workspace': WORKSPACE, 'p_label': 'TransportOrder desktop'},
                              access_token=session['access_token'])
        return self.pair(device['token'])

    def pair(self, token):
        token = str(token).strip()
        if not re.fullmatch('[a-f0-9]{64}', token):
            raise InputError('Paste the 64-character workstation code from the tracking website.')
        with self.lock:
            self.request('/rest/v1/rpc/transport_device', {'p_token':token,'p_action':'read_records','p_payload':{'table':'to_pallets','filters':{},'offset':0}}, False)
            if self.key_path:
                descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(descriptor, 'w') as handle:
                    handle.write(protect(token))
            self.device_token = token
        return {'paired': True}

    def rpc(self, action, payload):
        if not self.device_token:
            raise InputError('Sign in under Settings → Online shipments.')
        return self.request('/rest/v1/rpc/transport_device', {'p_token':self.device_token,'p_action':action,'p_payload':payload}, False)

    def rows(self, table, **filters):
        result = []
        while True:
            page = self.rpc('read_records', {'table':table,'filters':filters,'offset':len(result)})
            result.extend(page)
            if len(page) < 1000:
                return result

    def flush_archive(self, directory):
        folder = Path(directory) / 'archive'
        uploaded = folder / 'uploaded'
        uploaded.mkdir(parents=True, exist_ok=True)
        for path in sorted((folder / 'outbox').glob('*.json'))[:20]:
            self.rpc('archive_document', json.loads(path.read_text(encoding='utf-8')))
            path.replace(uploaded / path.name)

    def publish(self, store, load_id):
        from .archive import public_snapshot
        with self.lock, store.lock:
            state = copy.deepcopy(store.state)
            load = find(state, 'loads', load_id)
            if load.get('online'):
                return {'url': load['online']['url']}
            if load['status'] != 'ready' or load['scans']:
                raise InputError('Publish an unscanned ready manifest. Local scans cannot be merged into an online pickup.')
            if any(p['revision'] != 1 for p in load['pallets']):
                raise InputError('This first online test supports newly finalised pallets at revision 1. Use fresh pallets; reopened local revisions need history migration.')
            expected = {p['id'] for p in load['pallets']}
            cloud_pallets = {p['id']: p for p in self.rows('to_pallets')}
            for pallet in load['pallets']:
                existing = cloud_pallets.get(pallet['id'])
                if existing and existing['status'] == 'open' and existing['revision'] == pallet['revision'] - 1:
                    self.rpc('save_pallet', {'pallet': {**pallet, 'status': 'finalised'}, 'forms': pallet['forms'], 'expectedRowVersion': existing['row_version']})
                    existing = None
                    continue
                if existing:
                    if existing['revision'] != pallet['revision'] or existing['status'] != 'finalised':
                        raise InputError('An online pallet conflicts with this local revision. Do not overwrite it.')
                    docs = self.rows('to_documents', kind='pallet', reference_id=pallet['id'], revision=pallet['revision'])
                    if not docs or public_snapshot(docs[0]['snapshot']['forms']) != public_snapshot(pallet['forms']):
                        raise InputError('Online pallet contents differ. Resolve this conflict before publishing.')
                else:
                    self.rpc('save_pallet', {'pallet': {**pallet, 'status': 'finalised'}, 'forms': pallet['forms'], 'expectedRowVersion': 0})
            links = self.rows('to_manifest_pallets')
            active = [r for r in links if not r.get('released_at')]
            overlaps = {r['manifest_id'] for r in active if r['pallet_id'] in expected}
            if overlaps:
                if len(overlaps) != 1:
                    raise InputError('These pallets are reserved by different online manifests.')
                mid = overlaps.pop()
                assigned = {r['pallet_id'] for r in links if r['manifest_id'] == mid}
                if assigned != expected:
                    raise InputError('An existing online manifest has different contents. Review it before continuing.')
                manifest = self.rows('to_manifests', id=mid)[0]
                result = self.rpc('rotate_driver_link', {'id': mid, 'expectedRowVersion': manifest['row_version']})
                result['id'] = mid
            else:
                reserved = {r['pallet_id'] for r in active}
                available = {p['id'] for p in self.rows('to_pallets') if p['status'] == 'finalised' and not p.get('collected_at') and p['id'] not in reserved and ' '.join(p['destination']['building'].split()).casefold() == ' '.join(load['building'].split()).casefold()}
                if not expected.issubset(available):
                    raise InputError('Some selected pallets are no longer available online. Refresh the shipment status before publishing.')
                result = self.rpc('create_manifest', {'building': load['building'], 'palletIds':sorted(expected)})
            token = result['driverToken']
            if not re.fullmatch('[a-f0-9]{64}', token):
                raise InputError('Online service returned an invalid link.')
            load['online'] = {'id': result['id'], 'url': SITE + '#' + token}
            event(state, 'Manifest published online', load_id, result['id'])
            state['revision'] += 1
            store._write(state)
            store.state = state
            from .archive import archive_document
            archive_document(store, state, {'kind':'load','id':load_id,'revision':load['revision']})
            return {'url': load['online']['url']}

    def refresh(self, store, load_id):
        with self.lock:
            original = find(store.snapshot(), 'loads', load_id)
            token = original['online']['url'].split('#')[1]
            result = self.request('/rest/v1/rpc/transport_driver', {'p_token': token, 'p_action': 'get', 'p_payload': {}}, False)
        with store.lock:
            state = copy.deepcopy(store.state)
            load = find(state, 'loads', load_id)
            if load.get('online') != original.get('online'):
                return {'status': load['status']}
            load['status'] = result['status']
            load['scans'] = [{'palletId': p['id'], 'at': p['scannedAt']} for p in result['pallets'] if p.get('scannedAt')]
            for key in ('driver', 'vehicle', 'reason', 'receiver', 'collectedAt', 'deliveredAt', 'releasedPallets', 'leftBehindCount'):
                if key in result:
                    load[key] = copy.deepcopy(result[key])
            if result.get('collectedAt'):
                load['completedAt'] = result['collectedAt']
            for p in result['pallets']:
                if p.get('collectedAt'):
                    local = next((item for item in state['pallets'] if item['id'] == p['id']), None)
                    if local is None:
                        continue
                    local['collectedAt'] = p['collectedAt']
                    local['collectedLoadId'] = load_id
                    if p.get('deliveredAt'):
                        local.update(deliveredAt=p['deliveredAt'], receiver=result.get('receiver', ''))
            for p in result.get('releasedPallets', []):
                local = next((item for item in state['pallets'] if item['id'] == p['id']), None)
                if local and not local.get('collectedAt'):
                    local.update(releaseReason=p.get('reason', result.get('reason', '')), releasedAt=p.get('releasedAt'), releasedFrom=load_id)
            load['online']['status'] = result['status']
            if state != store.state:
                state['revision'] += 1
                store._write(state, source_only=True)
                store.state = state
            return {'status': result['status']}

    def publish_department(self, store, form_id):
        from .archive import public_snapshot, archive_document
        with self.lock, store.lock:
            state = copy.deepcopy(store.state)
            form = find(state, 'forms', form_id)
            if not form.get('handoffToken') or form.get('handoffPublished'):
                return
            self.rpc('publish_department_order', {'token': form['handoffToken'], 'form': public_snapshot(form['versions'][0])})
            form['handoffPublished'] = True
            state['revision'] += 1
            store._write(state)
            store.state = state
            archive_document(store, state, {'kind': 'form', 'id': form_id, 'revision': 1})

    @staticmethod
    def handoff_token(value):
        from urllib.parse import urlsplit, parse_qs
        value = str(value).strip()
        if value.startswith('TO:HANDOFF:'):
            value = value.removeprefix('TO:HANDOFF:')
        elif value.startswith('https://'):
            url = urlsplit(value)
            if (url.hostname, url.path) != ('molntam.github.io', '/TransportOrder/'):
                raise InputError('Scan a TransportOrder department handover QR.')
            value = parse_qs(url.fragment).get('handoff', [''])[0]
        if not re.fullmatch('[a-f0-9]{64}', value):
            raise InputError('Scan a department transport order QR, not a pallet or manifest.')
        return value

    def handoff_preview(self, value):
        return self.rpc('get_department_order', {'token': self.handoff_token(value)})

    def receive_department(self, store, value, mode):
        from .domain import uid, now, route_key
        from .archive import archive_document
        token = self.handoff_token(value)
        if mode not in ('open', 'finalised'):
            raise InputError('Choose Open Pallet or Finalised Pallet.')
        with self.lock:
            preview = self.handoff_preview(value)
            with store.lock:
                store.rollover()
                if store.state['settings'].get('departmentMode', 'delivery_ops') != 'delivery_ops':
                    raise InputError('Only Delivery Operations can receive department transport orders.')
                source = preview['form']
                received = next((f for f in store.state['forms'] if f['id'] == source['id'] and f.get('handoffSourceId')), None)
                if received:
                    return {'palletId': received['palletId'], 'alreadyReceived': True}
                if preview.get('receivedAt') and source['id'] not in store.state.get('pendingHandoffs', {}):
                    raise InputError('This order has already been received on ' + preview['palletId'] + '. Use that workstation to continue the pallet.')
                incoming = {l['hu'] for l in source['lines'] if l.get('hu')}
                existing = {l['hu'] for f in store.state['forms'] if f['id'] != source['id'] and not f.get('removedAt') for l in f['lines'] if l.get('hu')}
                if incoming & existing:
                    raise InputError('These HUs are already assigned here: ' + ', '.join(sorted(incoming & existing)))
                state = copy.deepcopy(store.state)
                pending = state.setdefault('pendingHandoffs', {}).setdefault(source['id'], {'requestId': secrets.token_hex(16), 'palletId': uid('P'), 'mode': mode, 'origin': copy.deepcopy(state['settings']['origin']), 'hus': sorted(incoming)})
                if route_key(pending['origin']) != route_key(state['settings']['origin']):
                    raise InputError('Restore the receiving origin used for this pending handover before retrying.')
                state['revision'] += 1
                store._write(state)
                store.state = state
                request = copy.deepcopy(pending)
            result = self.rpc('receive_department_order', {'token': token, **{key: val for key, val in request.items() if key != 'hus'}})
            with store.lock:
                store.rollover()
                state = copy.deepcopy(store.state)
                form, pallet = copy.deepcopy(result['receivedForm']), result['pallet']
                prior = next((f for f in state['forms'] if f['id'] == form['id']), None)
                form['versions'] = copy.deepcopy(prior.get('versions', [])) if prior else [copy.deepcopy(source)]
                form['versions'].append(copy.deepcopy(result['receivedForm']))
                if prior:
                    state['forms'].remove(prior)
                state['forms'].append(form)
                local = {'id': pallet['id'], 'status': pallet['status'], 'revision': pallet['revision'], 'destination': pallet['destination'],
                         'createdAt': pallet['created_at'], 'updatedAt': pallet['updated_at'], 'versions': [], 'handoffSourceId': form['id']}
                document = None
                if pallet['status'] == 'finalised':
                    local.update(finalisedAt=pallet['finalised_at'])
                    local['versions'].append({'revision': 1, 'at': now(), 'destination': copy.deepcopy(pallet['destination']), 'forms': [copy.deepcopy(form)]})
                    document = {'kind': 'pallet', 'id': pallet['id'], 'revision': 1}
                state['pallets'].append(local)
                state.get('pendingHandoffs', {}).pop(form['id'], None)
                event(state, 'Department handover received', form['id'], source['sourceDepartment']['name'] + ' → ' + pallet['id'])
                state['revision'] += 1
                store._write(state)
                store.state = state
                if document:
                    archive_document(store, state, document)
                return {'palletId': pallet['id'], 'print': document}
