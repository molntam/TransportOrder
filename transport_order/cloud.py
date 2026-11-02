import copy
import json
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .domain import InputError, find, event

URL = 'https://cwwpuapvgwoelhpwserm.supabase.co'
KEY = 'sb_publishable_vrv6VwGmtlhnSqX2q2F20g_HO4vdj2R'
WORKSPACE = '111fb839-a913-4c34-ae02-1c1228f35f9c'
SITE = 'https://transportorder-driver.chicaron.chatgpt.site/'


class Cloud:
    def __init__(self):
        self.session = None
        self.lock = threading.RLock()

    def request(self, path, body=None, authenticated=True):
        headers = {'apikey': KEY, 'Content-Type': 'application/json'}
        if authenticated:
            if not self.session or self.session['expires_at'] <= time.time():
                raise InputError('Sign in under Settings → Online shipments. Your session lasts until expiry or app restart.')
            headers['Authorization'] = 'Bearer ' + self.session['access_token']
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
        with self.lock:
            self.session = None
            result = self.request('/auth/v1/token?grant_type=password', {'email': email, 'password': password}, False)
            self.session = {'access_token': result['access_token'], 'expires_at': time.time() + result['expires_in']}
            members = self.rows('to_members', user_id=result['user']['id'])
            if not any(m['role'] in ('admin', 'operator') for m in members):
                self.session = None
                raise InputError('This account needs operator membership. Complete supabase/bootstrap_operator.sql first.')
            return {'connected': True}

    def rpc(self, action, payload):
        return self.request('/rest/v1/rpc/transport_operator', {'p_workspace': WORKSPACE, 'p_action': action, 'p_payload': payload})

    def rows(self, table, **filters):
        query = {'workspace_id': 'eq.' + WORKSPACE, **{k: 'eq.' + str(v) for k, v in filters.items()}}
        result = []
        while True:
            page = self.request('/rest/v1/' + table + '?' + urlencode({**query, 'limit': 1000, 'offset': len(result)}))
            result.extend(page)
            if len(page) < 1000:
                return result

    def publish(self, store, load_id):
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
                if existing:
                    if existing['revision'] != pallet['revision'] or existing['status'] != 'finalised':
                        raise InputError('An online pallet conflicts with this local revision. Do not overwrite it.')
                    docs = self.rows('to_documents', kind='pallet', reference_id=pallet['id'], revision=pallet['revision'])
                    if not docs or docs[0]['snapshot']['forms'] != pallet['forms']:
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
                if available != expected:
                    raise InputError('Other online pallets are ready for this building. This test requires the online and selected local manifest contents to match exactly.')
                result = self.rpc('create_manifest', {'building': load['building']})
            token = result['driverToken']
            if not re.fullmatch('[a-f0-9]{64}', token):
                raise InputError('Online service returned an invalid link.')
            load['online'] = {'id': result['id'], 'url': SITE + '#' + token}
            event(state, 'Manifest published online', load_id, result['id'])
            state['revision'] += 1
            store._write(state)
            store.state = state
            return {'url': load['online']['url']}

    def refresh(self, store, load_id):
        with self.lock, store.lock:
            state = copy.deepcopy(store.state)
            load = find(state, 'loads', load_id)
            token = load['online']['url'].split('#')[1]
            result = self.request('/rest/v1/rpc/transport_driver', {'p_token': token, 'p_action': 'get', 'p_payload': {}}, False)
            load['status'] = result['status']
            load['scans'] = [{'palletId': p['id'], 'at': p['scannedAt']} for p in result['pallets'] if p.get('scannedAt')]
            for p in result['pallets']:
                if p.get('collectedAt'):
                    local = find(state, 'pallets', p['id'])
                    local['collectedAt'] = p['collectedAt']
            load['online']['status'] = result['status']
            state['revision'] += 1
            store._write(state)
            store.state = state
            return {'status': result['status']}
