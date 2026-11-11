import copy
import tempfile
import unittest
from unittest.mock import patch

from transport_order.archive import public_snapshot
from transport_order.cloud import Cloud, SITE
from transport_order.domain import initial_state, apply_action, InputError, DEFAULT_ORIGIN
from transport_order.printing import document_model
from transport_order.storage import Store
from test_workflow import form, loaded_state


class DepartmentTests(unittest.TestCase):
    def setUp(self):
        self.state = initial_state()
        apply_action(self.state, 'settings', {'departmentMode':'other','departmentName':'Stagnation','departmentLocation':'Building 58'})
        self.payload = {'intent':'department_print','mode':'manual','origin':dict(DEFAULT_ORIGIN),
            'destination':{'building':'Building 21','department':'Motion','shipTo':'B21-MOASSY'},
            'lines':[{'hu':'0001','dn':'0002','qty':'3'}],'preparedBy':'Operator'}

    def test_settings_default_and_validation(self):
        self.assertEqual(initial_state()['settings']['departmentMode'], 'delivery_ops')
        with self.assertRaisesRegex(InputError, 'name and location'):
            apply_action(self.state, 'settings', {'departmentName':''})
        with self.assertRaisesRegex(InputError, 'Choose Delivery Operations'):
            apply_action(self.state, 'settings', {'departmentMode':'invalid'})

    def test_single_print_creates_standalone_qr_document(self):
        result = apply_action(self.state, 'save_form', self.payload)
        record = self.state['forms'][0]
        self.assertEqual(result['print']['kind'], 'form')
        self.assertIsNone(record['palletId'])
        self.assertEqual(self.state['pallets'], [])
        self.assertEqual(record['origin']['department'], 'Stagnation')
        self.assertEqual(record['origin']['building'], 'Building 58')
        self.assertEqual(len(record['handoffToken']), 64)
        with patch('transport_order.printing.matrix', return_value=[]) as qr:
            document_model(self.state, 'form', record['id'], 1)
        qr.assert_called_once_with(SITE+'#handoff='+record['handoffToken'])
        self.assertNotIn(record['handoffToken'], str(public_snapshot(record)))

    def test_other_departments_cannot_use_delivery_workflows(self):
        for action in ('create_load','scan_load','import','clear_source','finalise_pallet','reopen_pallet'):
            with self.assertRaisesRegex(InputError, 'Delivery Operations'):
                apply_action(self.state, action, {})
        for intent in ('draft','keep_open','finalise'):
            with self.assertRaisesRegex(InputError, 'Print transport order'):
                apply_action(self.state, 'save_form', {**self.payload,'intent':intent})

    def test_invalid_material_and_duplicate_hu_rejected(self):
        with self.assertRaises(InputError):
            apply_action(self.state, 'save_form', {**self.payload,'lines':[{'hu':'0001','qty':'0'}]})
        apply_action(self.state, 'save_form', self.payload)
        with self.assertRaisesRegex(InputError, 'already used'):
            apply_action(self.state, 'save_form', self.payload)

    def test_handover_documents_cannot_be_overwritten(self):
        result = apply_action(self.state, 'save_form', self.payload)
        with self.assertRaisesRegex(InputError, 'immutable'):
            apply_action(self.state, 'save_form', {**self.payload,'id':result['formId']})

    def test_pending_receipt_reserves_hus(self):
        state = loaded_state()
        state['pendingHandoffs'] = {'TO-A':{'hus':['HU1']}}
        with self.assertRaisesRegex(InputError, 'pending department handover'):
            apply_action(state,'save_form',form())

    def test_public_snapshot_recursively_removes_bearer_tokens(self):
        result=public_snapshot({'online':{'id':'LOAD-A','url':'secret'},'forms':[{'handoffToken':'secret','versions':[{'hidden':'x'}]}]})
        self.assertEqual(result, {'online':{'id':'LOAD-A'},'forms':[{}]})

    def test_handover_qr_origin_and_kind_validation(self):
        token='a'*64
        self.assertEqual(Cloud.handoff_token(SITE+'#handoff='+token),token)
        self.assertEqual(Cloud.handoff_token('TO:HANDOFF:'+token),token)
        for value in ('https://evil.invalid/TransportOrder/#handoff='+token, 'TO:PALLET:P-A:1', SITE+'#'+token):
            with self.assertRaises(InputError):
                Cloud.handoff_token(value)

    def test_publication_failure_and_retry_keep_the_same_document(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.state=copy.deepcopy(self.state)
            result=store.apply('save_form',self.payload,store.state['revision'])
            cloud=Cloud()
            with patch.object(cloud,'rpc',side_effect=InputError('Connection interrupted')):
                with self.assertRaises(InputError):cloud.publish_department(store,result['formId'])
            token=store.state['forms'][0]['handoffToken']
            self.assertFalse(store.state['forms'][0]['handoffPublished'])
            with patch.object(cloud,'rpc',return_value={'published':True}) as rpc:
                cloud.publish_department(store,result['formId'])
                cloud.publish_department(store,result['formId'])
                self.assertEqual(rpc.call_count,1)
                self.assertEqual(rpc.call_args.args[1]['token'],token)
            self.assertTrue(Store(directory).state['forms'][0]['handoffPublished'])

    def test_receiving_failure_keeps_idempotency_request_for_retry(self):
        source={**self.payload,'id':'TO-SOURCE','revision':1,'status':'complete','sourceDepartment':{'name':'Stagnation','location':'Building 58'}}
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.snapshot();cloud=Cloud()
            with patch.object(cloud,'handoff_preview',return_value={'form':source,'receivedAt':None}), patch.object(cloud,'rpc',side_effect=InputError('Lost response')):
                with self.assertRaises(InputError):cloud.receive_department(store,'a'*64,'open')
                pending=copy.deepcopy(store.state['pendingHandoffs']['TO-SOURCE'])
                with self.assertRaises(InputError):cloud.receive_department(store,'a'*64,'finalised')
            self.assertEqual(store.state['pendingHandoffs']['TO-SOURCE'],pending)
            self.assertEqual(pending['mode'],'open')
            self.assertEqual(Store(directory).state['pendingHandoffs']['TO-SOURCE']['requestId'],pending['requestId'])
