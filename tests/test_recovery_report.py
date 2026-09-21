import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from recovery_report import RecoveryReportWriter


class RecoveryReportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "lecture.recovery.json"
        self.writer = RecoveryReportWriter(self.path)

    def test_transient_lock_retries_and_preserves_valid_json(self):
        replace = Path.replace
        calls = []
        def locked_once(source, target):
            calls.append(target)
            if len(calls) == 1:
                raise PermissionError(13, "locked")
            return replace(source, target)
        with patch.object(Path, "replace", locked_once), patch("recovery_report.time.sleep"):
            self.writer([{"status": "recovered"}])
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.writer.latest_path, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["events"], [{"status": "recovered"}])
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_persistent_lock_keeps_old_report_and_new_snapshots(self):
        self.path.write_text('{"events": []}', encoding="utf-8")
        with patch.object(Path, "replace", side_effect=PermissionError(13, "locked")) as replace, \
             patch("recovery_report.time.sleep"):
            first = self.writer([{"status": "retry"}])
            second = self.writer([{"status": "recovered"}])
        self.assertEqual(replace.call_count, 4)
        self.assertNotEqual(first, second)
        self.assertEqual(json.loads(first.read_text(encoding="utf-8"))["events"][0]["status"], "retry")
        self.assertEqual(json.loads(second.read_text(encoding="utf-8"))["events"][0]["status"], "recovered")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"events": []})

    def test_non_permission_errors_are_not_hidden(self):
        with patch.object(Path, "replace", side_effect=OSError(28, "disk full")):
            with self.assertRaises(OSError):
                self.writer([])
        self.assertTrue(self.writer.latest_path.exists())
