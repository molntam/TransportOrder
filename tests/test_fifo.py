import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from transport_order.domain import initial_state
from transport_order.fifo import fifo_status, changed_at
from transport_order.local_time import display_time


class FifoTests(unittest.TestCase):
    def state(self, **row):
        state = initial_state()
        state['sources']['shipto'] = {'rows': [{'hu':'0001', 'dn':'000123', 'bin':'PS_READY-INT', 'condition':'S1', 'changedOn':'11.11.2026', 'changedAt':'08:00:00', **row}]}
        return state

    def test_four_hour_limit_amsterdam(self):
        moment = datetime(2026, 11, 11, 11, tzinfo=timezone.utc)
        result = fifo_status(self.state(), moment)
        self.assertEqual(result['alerts'][0]['ageHours'], 4)
        self.assertIn('000123', result['messages'][0]['text'])
        self.assertIn('4 hours on PS_READY-INT', result['messages'][0]['text'])
        self.assertFalse(fifo_status(self.state(), moment.replace(hour=10))['alerts'])

    def test_two_hour_conditions(self):
        moment = datetime(2026, 11, 11, 9, tzinfo=timezone.utc)
        for condition in ('S2', 'I8'):
            result = fifo_status(self.state(condition=condition), moment)
            self.assertEqual(result['alerts'][0]['limitHours'], 2)

    def test_emergencies_both_allowed_bins_even_without_timestamp(self):
        for condition in ('S4', 'I2'):
            for bin_name in ('PS_READY-INT', 'INTER-IN'):
                result = fifo_status(self.state(condition=condition, bin=bin_name, changedOn='', changedAt=''))
                self.assertTrue(result['alerts'][0]['emergency'])
                self.assertIn('please process ASAP', result['messages'][0]['text'].replace('Please', 'please'))

    def test_other_bins_and_conditions_ignored(self):
        for row in ({'bin':'INTER-IN'}, {'bin':'PRE-STAGING'}, {'bin':'PS_READY-INT-OTHER'}, {'condition':'S9'}):
            self.assertEqual(fifo_status(self.state(**row))['alerts'], [])
            result=fifo_status(self.state(**row))
            self.assertEqual(len(result['notCounted']), 1)
            self.assertIsNone(result['notCounted'][0]['ageHours'])
            self.assertIsNone(result['notCounted'][0]['limitHours'])

    def test_missing_and_future_timestamp(self):
        result = fifo_status(self.state(changedAt='broken'))
        self.assertEqual(len(result['missing']), 1)
        result = fifo_status(self.state(changedOn='11.11.2099'))
        self.assertFalse(result['alerts'])
        self.assertEqual(result['pending'][0]['ageHours'], 0)

    def test_collected_material_excluded_but_prepared_material_monitored(self):
        state = self.state(condition='S4')
        state['pallets'] = [{'id':'P-A'}]
        state['forms'] = [{'palletId':'P-A','lines':[{'hu':'0001'}]}]
        self.assertEqual(len(fifo_status(state)['alerts']), 1)
        state['pallets'][0]['collectedAt'] = 'now'
        self.assertEqual(fifo_status(state)['alerts'], [])

    def test_excel_serial_dates_and_fractional_time(self):
        self.assertEqual(changed_at('46337', '0.5'), changed_at('11.11.2026', '12:00:00'))
        self.assertEqual(changed_at('11/11/2026', '080000'), changed_at('2026-11-11', '08:00'))
        self.assertEqual(changed_at('20261111', '08:00'), changed_at('11.11.2026', '08:00'))
        self.assertIsNone(changed_at('invalid', '08:00'))
        self.assertIsNone(changed_at('11.11.2026', '25:00'))

    def test_summer_time_and_windows_fallback(self):
        self.assertEqual(changed_at('01.07.2026', '12:00').hour, 10)
        self.assertEqual(display_time('2026-11-11T11:35:40Z'), '11/11/2026 12:35:40')
        with patch('zoneinfo.ZoneInfo', side_effect=KeyError('No tzdata')):
            self.assertEqual(changed_at('01.07.2026', '12:00').hour, 10)
            self.assertEqual(changed_at('11.11.2026', '12:00').hour, 11)
