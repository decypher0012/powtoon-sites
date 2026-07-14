import unittest

from work_launcher.config import validate_config_data


class ValidationTests(unittest.TestCase):
    def test_unsupported_scheme_rejected(self):
        with self.assertRaises(ValueError):
            validate_config_data({"websites": [{"name": "X", "url": "file:///tmp/x"}]})

