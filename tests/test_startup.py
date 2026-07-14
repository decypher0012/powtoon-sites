import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from work_launcher.startup import get_startup_entry_path, set_startup_enabled


class StartupTests(unittest.TestCase):
    @patch("work_launcher.startup.get_startup_entry_path")
    def test_creation_and_removal(self, mock_entry):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "WorkLauncher.cmd"
            executable=Path(tmp)/"WorkLauncher.exe"; executable.touch()
            mock_entry.return_value = path
            set_startup_enabled(True, executable)
            self.assertTrue(path.exists())
            first=path.read_text(); set_startup_enabled(True,executable); self.assertEqual(path.read_text(),first)
            set_startup_enabled(False, executable)
            self.assertFalse(path.exists())

    @patch("work_launcher.startup.get_startup_entry_path")
    def test_missing_executable_reports_startup_specific_failure(self,mock_entry):
        with tempfile.TemporaryDirectory() as tmp:
            mock_entry.return_value=Path(tmp)/"WorkLauncher.cmd"
            with self.assertRaisesRegex(OSError,"executable does not exist"):
                set_startup_enabled(True,Path(tmp)/"missing.exe")
