import base64
import copy
import csv
import io
import json
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from transport_order.domain import DEFAULT_ORIGIN, active_sources, apply_action, initial_state, resolve
from transport_order.integrations.sap import InputError
from transport_order.integrations.spotfire import DEFAULT_REPORT_URL, parse_export, report_url
from transport_order.server import create_server
from transport_order.storage import ConflictError, Store


HEADERS = ['Handling unit', 'Original_ERP_Document', 'Ship_To_Party_Description',
           'Quantity', 'Document_Number', 'ERP_Shipping_Condition', 'Storage bin', 'DHL KPI DateTime']


def export(rows, delimiter='\t'):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return output.getvalue().encode('utf-16')


def sample(destination='CLE21-CABN'):
    return export([
        ['00001', '000901', destination, '2.5', '000801', 'S1', 'BIN-A', '2026-11-06 08:00'],
        ['00001', '000901', destination, '2.5', '000801', 'S4', 'BIN-B', '2026-11-06 08:00'],
        ['00002', '000902', destination, '1', '000802', 'S1', 'BIN-C', '2026-11-06 09:00'],
    ])


def loaded(content=None):
    state = initial_state()
    parsed = parse_export(sample() if content is None else content)
    for source in parsed['sources'].values():
        source['importedAt'] = '2026-11-07T08:00:00+00:00'
    state['sources']['spotfire'] = parsed
    return state


class CollectorDiagnosticsTests(unittest.TestCase):
    def test_browser_failure_reports_the_step_without_exposing_browser_trace(self):
        from transport_order.integrations.spotfire_browser import collection_failure
        message = collection_failure('export_menu', RuntimeError('private URL and session in browser trace'))
        self.assertIn('Export table menu', message)
        self.assertNotIn('private URL', message)
        self.assertIn('last valid data', message)

    def test_validation_failure_keeps_the_actual_validation_reason(self):
        from transport_order.integrations.spotfire_browser import collection_failure
        self.assertIn('row 2', collection_failure('data_validation', InputError('Invalid quantity at row 2')))


class ExportTests(unittest.TestCase):
    def test_utf16_item_rows_preserve_identifiers_and_sum_quantities(self):
        state = loaded()
        source = state['sources']['spotfire']
        self.assertEqual((source['rowCount'], source['uniqueHus']), (3, 2))
        result = resolve(state, [{'hu': '00001'}])
        self.assertTrue(result['valid'])
        self.assertEqual(result['lines'][0]['dn'], '000901')
        self.assertEqual(result['lines'][0]['qty'], '5.0')
        self.assertEqual(result['lines'][0]['quantityRecords'], 2)
        self.assertEqual(result['destination']['building'], 'Building 21')
        self.assertTrue(result['emergency'])
        ship = active_sources(state)['shipto']['rows'][0]
        self.assertEqual(ship['document'], '000801')
        self.assertEqual(ship['bin'], 'BIN-A / BIN-B')
        self.assertEqual(ship['changedOn'], '')
        self.assertTrue(ship['fifoAt'])

    def test_semicolon_and_utf8_are_supported(self):
        content = export([['H1', 'D1', 'WH 21 MPS', '3', '', 'S1', '', '']], ';')
        result = parse_export(content.decode('utf-16').encode('utf-8-sig'))
        self.assertEqual(result['sources']['shipto']['rows'][0]['shipTo'], 'WH21-MPSC')
        self.assertEqual(result['sources']['quantities']['rows'][0]['document'], 'D1')

    def test_known_descriptions_map_to_existing_routes(self):
        for description, code in [('ASML Bld 9, DESK9', 'DESK9C'), ('DHL.TOOLS', 'DHL.TOOLSC')]:
            result = parse_export(sample(description))
            self.assertEqual(result['sources']['shipto']['rows'][0]['shipTo'], code)
            self.assertFalse(result['warnings'])

    def test_generic_description_requires_explicit_destination_review(self):
        state = loaded(sample('ASML Netherlands BV'))
        self.assertTrue(state['sources']['spotfire']['warnings'])
        self.assertFalse(resolve(state, [{'hu': '00001'}])['valid'])
        chosen = {'building': 'Building 17', 'department': 'Checked department', 'shipTo': 'Checked dock'}
        result = resolve(state, [{'hu': '00001'}], chosen_destination=chosen, override_reason='Address confirmed')
        self.assertTrue(result['valid'])
        self.assertEqual(result['destination'], chosen)

    def test_conflicting_dn_or_destination_rejects_the_entire_export(self):
        for dn, destination in [('D2', 'CLE21-CABN'), ('D1', 'NL10C')]:
            with self.subTest(dn=dn, destination=destination), self.assertRaisesRegex(InputError, 'HU H1'):
                parse_export(export([['H1', 'D1', 'CLE21-CABN', '1', '', '', '', ''],
                                     ['H1', dn, destination, '2', '', '', '', '']]))

    def test_missing_columns_and_bad_quantities_are_rejected(self):
        with self.assertRaisesRegex(InputError, 'columns'):
            parse_export('Handling unit;Quantity\nH1;1')
        with self.assertRaisesRegex(InputError, 'row 2'):
            parse_export(export([['H1', 'D1', 'CLE21-CABN', 'unknown', '', '', '', '']]))

    def test_empty_valid_export_clears_open_orders(self):
        self.assertEqual(parse_export(export([]))['uniqueHus'], 0)

    def test_emergency_description_is_recognised(self):
        content = 'Handling unit;Original_ERP_Document;Ship_To_Party_Description;Quantity;Shipping Conditions\nH1;D1;CLE21-CABN;1;Emergency'
        result = parse_export(content)
        self.assertEqual(result['sources']['shipto']['rows'][0]['condition'], 'S4')

    def test_full_report_url_discards_session_identifiers(self):
        url = report_url(DEFAULT_REPORT_URL + '&waid=private-session&wavid=0')
        self.assertNotIn('waid', url)
        self.assertIn('FIFO+Monitor+DHL+Shipping', url)
        for invalid in ['http://spotfire.asml.com/spotfire/wp/analysis?file=x',
                        'https://example.com/spotfire/wp/analysis?file=x',
                        'https://spotfire.asml.com/spotfire/wp/analysis?file=LO%20O…']:
            with self.subTest(url=invalid), self.assertRaises(InputError):
                report_url(invalid)


class WeertTests(unittest.TestCase):
    def setUp(self):
        self.state = loaded(sample('WH-WEERT1A'))

    def test_choice_is_required_and_cannot_be_bypassed_by_override(self):
        chosen = {'building': 'Weert 1A', 'department': 'SCRAP', 'shipTo': 'WEERT1A SCRAP'}
        result = resolve(self.state, [{'hu': '00001'}], chosen_destination=chosen, override_reason='Checked')
        self.assertTrue(result['requiresWeert1aChoice'])
        self.assertFalse(result['valid'])
        with self.assertRaisesRegex(InputError, 'Choose Scrap or Normal'):
            apply_action(self.state, 'save_form', {'mode': 'automatic', 'origin': DEFAULT_ORIGIN,
                         'destination': chosen, 'overrideReason': 'Checked', 'lines': [{'hu': '00001'}],
                         'intent': 'finalise'})

    def test_each_choice_resolves_and_is_saved_with_its_hus(self):
        for mode, department in [('scrap', 'SCRAP'), ('normal', 'Reverse Logistics / Re-use parts')]:
            with self.subTest(mode=mode):
                state = copy.deepcopy(self.state)
                choice = {'mode': mode, 'hus': ['00001']}
                result = resolve(state, [{'hu': '00001'}], weert1a_choice=choice)
                self.assertTrue(result['valid'])
                self.assertEqual(result['destination']['department'], department)
                apply_action(state, 'save_form', {'mode': 'automatic', 'origin': DEFAULT_ORIGIN,
                             'lines': [{'hu': '00001'}], 'weert1aChoice': choice, 'intent': 'keep_open'})
                self.assertEqual(state['forms'][0]['weert1aChoice'], choice)
                self.assertEqual(state['forms'][0]['sourceProvider'], 'spotfire')

    def test_changed_hus_require_another_choice(self):
        result = resolve(self.state, [{'hu': '00002'}], weert1a_choice={'mode': 'scrap', 'hus': ['00001']})
        self.assertTrue(result['requiresWeert1aChoice'])
        self.assertFalse(result['valid'])

    def test_formatted_hu_uses_canonical_identifier_for_choice(self):
        result = resolve(self.state, [{'hu': "'00001"}], weert1a_choice={'mode': 'normal', 'hus': ['00001']})
        self.assertTrue(result['valid'])


class SourceStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(self.folder.name)

    def test_failed_import_keeps_last_valid_snapshot(self):
        self.store.import_spotfire(sample())
        before = self.store.snapshot()
        with self.assertRaises(InputError):
            self.store.import_spotfire('Broken export')
        self.assertEqual(self.store.snapshot(), before)

    def test_unchanged_export_does_not_create_save_conflicts(self):
        self.store.import_spotfire(sample())
        before = self.store.snapshot()
        self.store.import_spotfire(sample(), automatic=True)
        self.assertEqual(self.store.snapshot(), before)

    def test_background_refresh_allows_save_but_other_operator_edits_still_conflict(self):
        self.store.import_spotfire(sample())
        revision = self.store.snapshot()['revision']
        self.store.import_spotfire(sample('WH21-MPSC'), automatic=True)
        self.store.apply('save_form', {'mode': 'automatic', 'origin': DEFAULT_ORIGIN,
                         'lines': [{'hu': '00001'}], 'intent': 'draft'}, revision)
        self.store.apply('settings', {'preparedBy': 'Other operator'}, self.store.snapshot()['revision'])
        self.store.import_spotfire(sample('NL10C'), automatic=True)
        with self.assertRaises(ConflictError):
            self.store.apply('settings', {'preparedBy': 'Stale window'}, revision)

    def test_sap_import_switches_source_and_auto_checks_cannot_replace_it(self):
        self.store.import_spotfire(sample())
        self.store.apply('import', {'kind': 'quantities', 'text': 'Document\tHandling Unit\tQuantity\nD1\tH1\t8'}, self.store.snapshot()['revision'])
        before = self.store.snapshot()
        self.assertEqual(before['settings']['dataSource'], 'sap')
        self.store.import_spotfire(sample('NL10C'), automatic=True)
        self.assertEqual(self.store.snapshot(), before)
        self.store.import_spotfire(sample())
        self.assertEqual(self.store.snapshot()['settings']['dataSource'], 'spotfire')

    def test_refresh_is_an_atomic_pair_and_completed_form_keeps_snapshot(self):
        self.store.import_spotfire(sample())
        self.store.apply('save_form', {'mode': 'automatic', 'origin': DEFAULT_ORIGIN,
                         'lines': [{'hu': '00001'}], 'intent': 'keep_open'}, self.store.snapshot()['revision'])
        form = self.store.snapshot()['forms'][0]
        self.store.import_spotfire(export([]), automatic=True)
        state = Store(self.folder.name).snapshot()
        self.assertEqual(state['forms'][0], form)
        self.assertEqual(active_sources(state)['shipto']['rows'], [])
        self.assertEqual(active_sources(state)['quantities']['rows'], [])
        self.assertEqual(active_sources(state)['shipto']['importedAt'], active_sources(state)['quantities']['importedAt'])


class SpotfireApiTests(unittest.TestCase):
    def test_import_and_required_choice_work_through_local_api(self):
        with tempfile.TemporaryDirectory() as folder:
            server = create_server(Store(folder), 'spotfire-test', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def post(path, data):
                    request = Request(f'http://127.0.0.1:{server.server_port}/api/{path}',
                                      data=json.dumps(data).encode(),
                                      headers={'X-Session-Token': 'spotfire-test', 'Content-Type': 'application/json'})
                    with urlopen(request) as response:
                        return json.load(response)
                result = post('spotfire-import', {'fileBase64': base64.b64encode(sample('Weert 1A')).decode()})
                self.assertEqual(result['uniqueHus'], 2)
                self.assertTrue(post('resolve', {'lines': [{'hu': '00001'}]})['requiresWeert1aChoice'])
                result = post('resolve', {'lines': [{'hu': '00001'}], 'weert1aChoice': {'mode': 'scrap', 'hus': ['00001']}})
                self.assertTrue(result['valid'])
                self.assertEqual(result['destination']['department'], 'SCRAP')
                with self.assertRaises(HTTPError) as error:
                    post('spotfire-import', {'fileBase64': base64.b64encode(b'invalid').decode()})
                self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
