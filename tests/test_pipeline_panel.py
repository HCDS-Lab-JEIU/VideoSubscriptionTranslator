"""GUI 실행·선택·비동기 로그를 검증합니다. 실제 전사 API는 호출하지 않습니다."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QProcess, QTimer
from PyQt6.QtWidgets import QApplication
from qtTest.pipeline_panel import PipelinePanel


BOOK = ("[Translation Rules]\nTranslate to English.\n[Course]\nAI/ML Applications\n"
        "[Terminology]\n꽃잎 = petal\n[Course]\n회로\n[Terminology]\n전압 = voltage\n")


class PipelinePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book = self.root / "강의 단어장.txt"
        self.book.write_text(BOOK, encoding="utf-8")
        self.video = self.root / "한국어 강의.mp4"
        self.video.write_bytes(b"test")
        self.key = self.root / "key.txt"
        self.key.write_text("fake-key", encoding="utf-8")
        self.panel = PipelinePanel()
        self.addCleanup(self.panel.deleteLater)
        self.panel.load_textbook(self.book)
        self.panel.set_video(self.video)
        self.panel.key_field.setText(str(self.key))

    def test_multiple_courses_require_explicit_selection(self):
        self.assertEqual(self.panel.course_combo.count(), 3)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.panel.course_combo.setCurrentIndex(1)
        self.assertTrue(self.panel.run_button.isEnabled())
        self.assertEqual(self.panel.course_combo.currentData(), "AI/ML Applications")
        self.book.write_text(BOOK.split("[Course]\n회로")[0], encoding="utf-8")
        self.panel.load_textbook(self.book)
        self.assertEqual(self.panel.course_combo.count(), 1)
        self.assertTrue(self.panel.run_button.isEnabled())

    def test_invalid_book_keeps_previous_valid_selection(self):
        self.panel.course_combo.setCurrentIndex(2)
        self.panel.load_textbook(self.root / "missing.txt")
        self.assertEqual(self.panel.textbook_path, self.book)
        self.assertEqual(self.panel.course_combo.currentData(), "회로")

    def test_launch_uses_selected_course_and_immutable_snapshot_and_blocks_double_click(self):
        self.panel.course_combo.setCurrentIndex(1)
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
            self.panel.start_pipeline()
        self.assertEqual(start.call_count, 1)
        args = start.call_args.args[1]
        self.assertEqual(args[args.index("--course") + 1], "AI/ML Applications")
        snapshot = Path(args[args.index("--textbook-file") + 1])
        self.book.write_text("changed", encoding="utf-8")
        self.assertEqual(snapshot.read_text(encoding="utf-8"), BOOK)
        self.assertNotIn("fake-key", " ".join(args))
        self.assertTrue(self.panel.busy)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertFalse(self.panel.inputs.isEnabled())
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertFalse(self.panel.busy)
        self.assertFalse(snapshot.exists())

    def test_preflight_rejects_missing_rules_or_key_before_process(self):
        self.panel.course_combo.setCurrentIndex(1)
        with patch.object(self.panel.process, "start") as start:
            self.book.write_text(BOOK.replace("[Translation Rules]\nTranslate to English.\n", ""), encoding="utf-8")
            self.panel.start_pipeline()
            self.assertIn("실행 준비 실패", self.panel.status.text())
            self.book.write_text(BOOK, encoding="utf-8")
            self.panel.key_field.setText(str(self.root / "missing-key.txt"))
            self.panel.start_pipeline()
            start.assert_not_called()
        self.assertFalse(self.panel.busy)

    def test_frozen_app_launches_bundled_cli_without_python_arguments(self):
        self.panel.course_combo.setCurrentIndex(1)
        with patch("sys.frozen", True, create=True), patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        program, args = start.call_args.args
        self.assertEqual(Path(program), self.panel.PROJECT_DIR / "VideoSubtitleTranslator-CLI.exe")
        self.assertEqual(args[0], str(self.video))
        self.assertNotIn("-u", args)
        self.assertNotIn(str(self.panel.PROJECT_DIR / "__main__.py"), args)
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)

    def test_split_utf8_logs_and_failure_restore_controls(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel._set_busy(True)
        encoded = "결과 폴더: D:/테스트 폴더\n[2/5] 한국어 전사\n작업 실패: 테스트 오류\n".encode("utf-8")
        for byte in encoded:
            self.panel._consume(self.panel._decoder.decode(bytes([byte])))
        self.assertEqual(self.panel.result_folder, Path("D:/테스트 폴더"))
        self.assertEqual(self.panel.progress.value(), 1)
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertEqual(self.panel.status.text(), "작업 실패: 테스트 오류")
        self.assertTrue(self.panel.run_button.isEnabled())
        self.assertTrue(self.panel.folder_button.isEnabled())

    def test_failed_start_restores_controls(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel._set_busy(True)
        self.panel._process_error(QProcess.ProcessError.FailedToStart)
        self.assertFalse(self.panel.busy)
        self.assertTrue(self.panel.run_button.isEnabled())

    def test_real_child_process_completes_without_blocking_qt(self):
        # 실제 API 대신 출력만 하는 짧은 CLI를 별도 프로세스에서 실행합니다.
        script = self.root / "__main__.py"
        script.write_text("print('[1/5] 오디오 추출', flush=True)\n"
                          "print('전체 파이프라인 완료: 테스트 결과.mp4', flush=True)\n", encoding="utf-8")
        self.panel.PROJECT_DIR = self.root
        self.panel.course_combo.setCurrentIndex(1)
        loop = QEventLoop()
        self.panel.process.finished.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(10000)
        self.panel.start_pipeline()
        loop.exec()
        timer.stop()
        if self.panel.process.state() != QProcess.ProcessState.NotRunning:
            self.panel.process.kill()
            self.panel.process.waitForFinished(1000)
            self.fail("child process did not finish")
        self.assertFalse(self.panel.busy)
        self.assertEqual(self.panel.progress.value(), 5)
        self.assertIn("테스트 결과.mp4", self.panel.status.text())

