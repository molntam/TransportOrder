import copy
import json
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from transport_order.domain import apply_action
from transport_order.integrations.sap import InputError
from transport_order.loads import dock_reminders, ready_pallets, scan_identity, validate_slots
from transport_order.printing import document_model, render_document
from transport_order.storage import Store
from test_workflow import loaded_state, form


class LoadingTests(unittest.TestCase):
    def setUp(self):
        self.state = loaded_state()
        self.first = apply_action(self.state, 'save_form', form(intent='finalise'))['palletId']
        self.second = apply_action(self.state, 'save_form', form(hu='HU2', intent='finalise'))['palletId']
        self.other = apply_action(self.state, 'save_form', form(hu='HU3', intent='finalise'))['palletId']

    def create(self):
        result = apply_action(self.state, 'create_load', {'building': 'Building 21'})
        return result['loadId']

    def scan(self, load, pallet, revision=1):
        return apply_action(self.state, 'scan_load', {'id': load, 'code': f'TO:PALLET:{pallet}:{revision}'})

    def test_manifest_reserves_only_building_ready_pallets_and_snapshots_all_content(self):
        load = self.create()
        self.assertEqual(ready_pallets(self.state, 'Building 21'), [])
        self.assertEqual(len(ready_pallets(self.state, self.state['pallets'][2]['destination']['building'])), 1)
        model = document_model(self.state, 'load', load, 1, 'http://127.0.0.1:8765')
        self.assertEqual(len(model['rows']), 2)
        self.assertIn(self.first, model['rows'][0])
        self.assertIn('HU1', str(model['rows']))
        self.assertIn('DN2', str(model['rows']))
        self.assertIn('TO-', str(model['rows']))
        self.assertTrue(model['qr'])
        self.assertLess(render_document(self.state, 'load', load, 1).index('<svg'), render_document(self.state, 'load', load, 1).index('</header>'))
        with self.assertRaises(InputError):
            self.create()
        with self.assertRaises(InputError):
            apply_action(self.state, 'reopen_pallet', {'id': self.first, 'reason': 'Correction'})

    def test_wrong_building_and_old_qr_are_rejected_without_progress(self):
        load = self.create()
        with self.assertRaisesRegex(InputError, 'Wrong destination'):
            self.scan(load, self.other)
        with self.assertRaisesRegex(InputError, 'Superseded'):
            self.scan(load, self.first, 99)
        self.assertEqual(self.state['loads'][0]['scans'], [])

    def test_same_building_but_not_on_manifest_is_rejected(self):
        load = self.create()
        manual = form(mode='manual', intent='finalise', destination={'building':'Building 21','department':'Other','shipTo':'OTHER'}, lines=[{'hu':'NEW','dn':'NEWDN','qty':'1'}])
        pallet = apply_action(self.state, 'save_form', manual)['palletId']
        with self.assertRaisesRegex(InputError, 'not included'):
            self.scan(load, pallet)

    def test_duplicate_scan_does_not_increment(self):
        load = self.create()
        self.assertEqual(self.scan(load, self.first)['count'], 1)
        self.assertTrue(self.scan(load, self.first)['duplicate'])
        self.assertEqual(len(self.state['loads'][0]['scans']), 1)

    def test_partial_pickup_releases_only_unscanned_pallets(self):
        load = self.create()
        self.scan(load, self.first)
        payload = {'id': load, 'driver': 'Test driver', 'vehicle': 'TEST-01'}
        with self.assertRaisesRegex(InputError, 'partial pickup'):
            apply_action(self.state, 'complete_load', payload)
        apply_action(self.state, 'complete_load', {**payload, 'reason': 'Truck full'})
        self.assertEqual(self.state['loads'][0]['status'], 'partial')
        self.assertEqual([p['id'] for p in ready_pallets(self.state, 'Building 21')], [self.second])
        next_load = self.create()
        self.assertEqual([p['id'] for p in self.state['loads'][1]['pallets']], [self.second])
        with self.assertRaises(InputError):
            self.scan(load, self.second)
        with self.assertRaises(InputError):
            apply_action(self.state, 'reopen_pallet', {'id': self.first, 'reason': 'Change'})
        self.assertNotEqual(next_load, load)
        self.assertEqual(len(document_model(self.state, 'load', load, 1)['rows']), 2)

    def test_full_pickup_and_remove_scan_require_real_progress_and_identity(self):
        load = self.create()
        payload = {'id':load,'driver':'Driver','vehicle':'TEST-02'}
        with self.assertRaisesRegex(InputError, 'at least one'):
            apply_action(self.state, 'complete_load', payload)
        self.scan(load, self.first)
        apply_action(self.state, 'unscan_load', {'id':load,'palletId':self.first,'reason':'Does not fit'})
        self.assertEqual(len(self.state['loads'][0]['scans']), 0)
        self.scan(load, self.first)
        self.scan(load, self.second)
        with self.assertRaisesRegex(InputError, 'driver name'):
            apply_action(self.state, 'complete_load', {**payload,'driver':''})
        apply_action(self.state, 'complete_load', payload)
        self.assertEqual(self.state['loads'][0]['status'], 'collected')
        self.assertFalse(ready_pallets(self.state, 'Building 21'))
        self.assertTrue(any(e['action']=='Load pickup confirmed' for e in self.state['events']))

    def test_cancellation_releases_pallets_and_preserves_superseded_manifest(self):
        load = self.create()
        apply_action(self.state, 'cancel_load', {'id':load,'reason':'Truck cancelled'})
        self.assertEqual(len(ready_pallets(self.state, 'Building 21')), 2)
        self.assertTrue(document_model(self.state, 'load', load, 1)['obsolete'])
        apply_action(self.state, 'reopen_pallet', {'id':self.first,'reason':'Fix'})
        apply_action(self.state, 'finalise_pallet', {'id':self.first})
        new = self.create()
        with self.assertRaisesRegex(InputError, 'Superseded'):
            self.scan(new, self.first)
        self.scan(new, self.first, 2)

    def test_legacy_state_migrates_without_losing_records(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            legacy = copy.deepcopy(self.state)
            legacy.pop('loads')
            legacy['settings'].pop('dockSlots')
            legacy['settings'].pop('manifestCopies')
            store.path.write_text(json.dumps(legacy))
            reopened = Store(directory).snapshot()
            self.assertEqual(reopened['forms'], legacy['forms'])
            self.assertEqual(reopened['loads'], [])
            self.assertEqual(reopened['settings']['manifestCopies'], 1)


    def test_manifest_native_print_defaults_to_one_copy(self):
        from transport_order.native_print import PrintService
        load = self.create()
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state = self.state
            with patch('transport_order.native_print.run_native', return_value={'status':'submitted','printer':'Queue','copies':1}) as native:
                PrintService('http://127.0.0.1:9999').submit(store, {'kind':'load','id':load,'revision':1,'requestId':'manifest-test-001'})
            job = native.call_args.args[1]
            self.assertEqual(job['copies'], 1)
            self.assertTrue(job['document']['qr'])
            self.assertEqual(job['document']['title'], 'Loading manifest')

    def test_scan_url_and_invalid_codes(self):
        self.assertEqual(scan_identity('http://127.0.0.1:8765/#scan=TO:LOAD:LOAD-123:1'), ('LOAD','LOAD-123',1))
        for code in ('HU1', 'TO:PALLET:P-123:bad', 'https://example.com/'):
            with self.assertRaises(InputError):
                scan_identity(code)


class DockSlotTests(unittest.TestCase):
    def test_twenty_minute_boundary_weekends_and_no_schedule(self):
        state = loaded_state()
        apply_action(state, 'save_form', form())
        self.assertEqual(dock_reminders(state, datetime(2026,11,2,8,40)), [])
        state['settings']['dockSlots'] = validate_slots([{'id':'B21','building':'Building 21','days':[0,1,2,3,4],'start':'09:00','end':'09:30'}])
        self.assertFalse(dock_reminders(state, datetime(2026,11,2,8,39,59)))
        self.assertEqual(dock_reminders(state, datetime(2026,11,2,8,40))[0]['open'], 1)
        self.assertTrue(dock_reminders(state, datetime(2026,11,2,9,15)))
        self.assertFalse(dock_reminders(state, datetime(2026,11,2,9,31)))
        self.assertFalse(dock_reminders(state, datetime(2026,11,7,8,50)))

    def test_validation_and_no_work_no_reminder(self):
        for slot in ({'building':'A','days':[5],'start':'09:00','end':'10:00'}, {'building':'A','days':[0],'start':'bad','end':'10:00'}, {'building':'A','days':[0],'start':'11:00','end':'10:00'}):
            with self.assertRaises(InputError):
                validate_slots([slot])
        state = loaded_state()
        apply_action(state, 'settings', {'dockSlots':[{'building':'Building 21','days':[0],'start':'09:00','end':'09:30'}]})
        self.assertFalse(dock_reminders(state, datetime(2026,11,2,8,50)))
