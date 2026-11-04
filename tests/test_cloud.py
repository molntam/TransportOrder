import copy
import tempfile
import time
import unittest
from unittest.mock import patch

from transport_order.cloud import Cloud, SITE
from transport_order.domain import apply_action, InputError
from transport_order.printing import document_model
from transport_order.storage import Store
from test_workflow import loaded_state, form


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.store.state = loaded_state()
        self.pid = apply_action(self.store.state, 'save_form', form(intent='finalise'))['palletId']
        self.lid = apply_action(self.store.state, 'create_load', {'building': 'Building 21'})['loadId']
        self.cloud = Cloud()
        self.records = []
        self.memberships = []
        self.docs = []
        self.manifests = []
        self.token = 'a' * 64
        self.calls = []

    def rows(self, table, **filters):
        return {'to_pallets': self.records, 'to_manifest_pallets': self.memberships, 'to_documents': self.docs, 'to_manifests': self.manifests}[table]

    def rpc(self, action, payload):
        self.calls.append(action)
        if action == 'save_pallet':
            self.records.append({**payload['pallet'], 'collected_at': None})
            self.docs.append({'snapshot': {'forms': payload['forms']}})
            return {}
        if action == 'create_manifest':
            self.memberships.append({'manifest_id': 'LOAD-CLOUD', 'pallet_id': self.pid, 'released_at': None})
            self.manifests.append({'row_version': 1})
        return {'id': 'LOAD-CLOUD', 'driverToken': self.token}

    def publish(self):
        with patch.object(self.cloud, 'rows', side_effect=self.rows), patch.object(self.cloud, 'rpc', side_effect=self.rpc):
            return self.cloud.publish(self.store, self.lid)

    def test_publish_persists_link_and_both_print_paths_use_it(self):
        result = self.publish()
        self.assertEqual(result['url'], SITE + '#' + self.token)
        with patch('transport_order.printing.matrix', return_value=[]) as qr:
            document_model(self.store.snapshot(), 'load', self.lid, 1, 'http://127.0.0.1:8765')
            qr.assert_called_once_with(result['url'])
        self.assertEqual(self.publish(), result)
        self.assertEqual(self.calls.count('create_manifest'), 1)
        restored = Store(self.tmp.name).snapshot()
        self.assertEqual(restored['loads'][0]['online']['url'], result['url'])
        with self.assertRaisesRegex(InputError, 'online'):
            apply_action(restored, 'cancel_load', {'id': self.lid, 'reason': 'test'})

    def test_lost_response_reconciles_without_duplicate_manifest(self):
        original = self.rpc
        def lost(action, payload):
            result = original(action, payload)
            if action == 'create_manifest':
                raise InputError('response lost')
            return result
        with patch.object(self.cloud, 'rows', side_effect=self.rows), patch.object(self.cloud, 'rpc', side_effect=lost):
            with self.assertRaises(InputError):
                self.cloud.publish(self.store, self.lid)
        self.publish()
        self.assertEqual(self.calls.count('create_manifest'), 1)
        self.assertIn('rotate_driver_link', self.calls)

    def test_other_ready_pallets_are_excluded_from_selected_manifest(self):
        self.records.append({'id': 'P-OTHER', 'status': 'finalised', 'destination': {'building': 'Building 21'}})
        self.publish()
        self.assertIn('create_manifest', self.calls)
        self.assertEqual({r['pallet_id'] for r in self.memberships}, {self.pid})

    def test_refresh_records_partial_pickup_without_collecting_leftovers(self):
        self.publish()
        result = {'status': 'partial', 'pallets': [{'id': self.pid, 'scannedAt': 'scan', 'collectedAt': 'pickup'}]}
        with patch.object(self.cloud, 'request', return_value=result):
            self.cloud.refresh(self.store, self.lid)
        self.assertEqual(self.store.state['loads'][0]['status'], 'partial')
        self.assertEqual(self.store.state['pallets'][0]['collectedAt'], 'pickup')

    def test_pairing_is_verified_and_persisted_without_login(self):
        self.cloud = Cloud(self.tmp.name)
        with patch.object(self.cloud, 'request', return_value=[]) as request:
            self.cloud.pair('b' * 64)
            self.assertEqual(request.call_args.args[1]['p_action'], 'read_records')
        self.assertEqual(Cloud(self.tmp.name).device_token, 'b' * 64)
        with self.assertRaisesRegex(InputError, '64-character'):
            self.cloud.pair('bad')
        with self.assertRaisesRegex(InputError, 'Sign in under Settings'):
            Cloud().rpc('create_manifest', {})

    def test_local_scan_and_reopened_revision_cannot_be_published(self):
        self.store.state['loads'][0]['pallets'][0]['revision'] = 2
        with self.assertRaisesRegex(InputError, 'revision 1'):
            self.publish()
        self.store.state['loads'][0]['scans'] = [{'palletId': self.pid}]
        with self.assertRaisesRegex(InputError, 'unscanned'):
            self.publish()
