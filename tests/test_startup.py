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
            mock_entry.return_value = path
            set_startup_enabled(True, Path("C:/WorkLauncher/WorkLauncher.exe"))
            self.assertTrue(path.exists())
            set_startup_enabled(False, Path("C:/WorkLauncher/WorkLauncher.exe"))
            self.assertFalse(path.exists())

