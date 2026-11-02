import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from transport_order.archive import local_day
from transport_order.storage import Store
from transport_order.cloud import Cloud
from test_workflow import loaded_state, form


class ArchiveTests(unittest.TestCase):
    def test_calendar_day_uses_netherlands_midnight(self):
        self.assertEqual(local_day('2026-11-01T23:05:00+00:00'), '2026-11-02')
        self.assertEqual(local_day('2026-07-01T22:05:00+00:00'), '2026-07-02')

    def test_new_day_archives_before_reset_and_keeps_preferences_and_outbox(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state = loaded_state()
            result = store.apply('save_form', form(intent='finalise'), store.state['revision'])
            self.assertTrue(list((Path(directory)/'archive/documents').glob('*.html')))
            self.assertTrue(list((Path(directory)/'archive/outbox').glob('*.json')))
            store.state['workspaceDay'] = '2026-10-30'
            store.state['settings']['preparedBy'] = 'Operator'
            with patch('transport_order.storage.local_day', return_value='2026-11-02'):
                today = store.snapshot()
            self.assertFalse(today['forms'])
            self.assertFalse(today['pallets'])
            self.assertFalse(today['loads'])
            self.assertIsNone(today['sources']['shipto'])
            self.assertEqual(today['settings']['preparedBy'], 'Operator')
            saved = json.loads(next((Path(directory)/'archive/workspaces').glob('*.json')).read_text())
            self.assertEqual(saved['forms'][0]['id'], result['formId'])
            self.assertTrue(list((Path(directory)/'archive/outbox').glob('*.json')))

    def test_archive_failure_does_not_erase_yesterdays_work(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state = loaded_state()
            store.state['workspaceDay'] = '2026-10-30'
            before = store.state.copy()
            with patch.object(Path,'mkdir',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    store.snapshot()
            self.assertEqual(store.state, before)

    def test_offline_documents_remain_queued_until_upload_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.state = loaded_state()
            store.apply('save_form', form(intent='keep_open'), store.state['revision'])
            cloud = Cloud()
            pending = list((Path(directory)/'archive/outbox').glob('*.json'))
            with patch.object(cloud,'rpc',side_effect=OSError('offline')):
                with self.assertRaises(OSError):cloud.flush_archive(directory)
            self.assertTrue(pending[0].exists())
            with patch.object(cloud,'rpc',return_value={'archived':True}):cloud.flush_archive(directory)
            self.assertFalse(pending[0].exists())
            self.assertTrue((Path(directory)/'archive/uploaded'/pending[0].name).exists())
