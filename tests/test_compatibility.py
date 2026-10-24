import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from compatibility import compatibility_state, host_version


class CompatibilityTests(unittest.TestCase):
    def test_inclusive_range_and_numeric_versions(self):
        data = {'range': '2024.1~2026.3', 'testedVersions': ['2026.3']}
        self.assertEqual(compatibility_state(data, '2024.1'), 'declared')
        self.assertEqual(compatibility_state(data, '2026.3'), 'tested')
        self.assertEqual(compatibility_state(data, '2026.4'), 'incompatible')
        self.assertGreater(host_version('2024.10'), host_version('2024.2'))
        self.assertEqual(compatibility_state(None, '2026.3'), 'unverified')

    def test_reject_invalid_ranges(self):
        for value in ('2026.3~2024.1', '../other', '2026.3'):
            with self.assertRaises(ValueError):
                compatibility_state({'range': value}, '2026.3')
