"""Check public launch commands and resource locations after package moves."""

import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from subtitle_app.common.app_paths import app_directory
from subtitle_app.common.app_version import __version__
from subtitle_app.textbook.document import DEFAULT_TEXTBOOK_PATH

ROOT = Path(__file__).resolve().parents[1]


class EntryPointTests(unittest.TestCase):
    def run_command(self, *args, cwd=ROOT):
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", QT_QPA_PLATFORM="offscreen")
        result = subprocess.run([sys.executable, *map(str, args)], cwd=cwd,
                                env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_source_data_paths_stay_at_project_root(self):
        self.assertEqual(app_directory(), ROOT)
        self.assertEqual(DEFAULT_TEXTBOOK_PATH, ROOT / "secrets/textbook.txt")

    def test_frozen_data_paths_use_executable_folder(self):
        executable = ROOT / "test-bundle/VideoSubtitleTranslator.exe"
        with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(executable)):
            self.assertEqual(app_directory(), executable.parent)

    def test_cli_module_and_original_file_command(self):
        self.assertIn(__version__, self.run_command("-m", "subtitle_app", "--version"))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn(__version__, self.run_command(ROOT / "__main__.py", "--version", cwd=folder))

    def test_gui_compatibility_entry_points_delegate_to_current_app(self):
        app = importlib.import_module("subtitle_app.ui.app")
        self.assertIs(importlib.import_module("qtTest.app").main, app.main)
        editor = importlib.import_module("subtitle_app.ui.textbook_editor.app")
        self.assertIs(importlib.import_module("qtTest.textbook_app").main, editor.main)
        self.assertIs(importlib.import_module("qtTest.textbook_editor.app").main, editor.main)

    def test_editor_module_and_original_file_command(self):
        self.assertIn("--textbook-file", self.run_command("-m", "subtitle_app.ui.textbook_editor", "--help"))
        self.assertIn("--textbook-file", self.run_command("-m", "qtTest.textbook_editor", "--help"))
        with tempfile.TemporaryDirectory() as folder:
            self.assertIn("--textbook-file", self.run_command(ROOT / "qtTest/textbook_editor/app.py", "--help", cwd=folder))
