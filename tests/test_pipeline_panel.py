"""GUI 실행·선택·비동기 로그를 검증합니다. 실제 전사 API는 호출하지 않습니다."""

import os
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QProcess, QTimer
from PyQt6.QtWidgets import QApplication
from qtTest.pipeline_panel import PipelinePanel
from pipeline_events import SUBTITLE_READY_PREFIX


BOOK = ("[Translation Rules]\nTranslate to English.\n[Course]\nAI/ML Applications\n"
        "[Terminology]\n꽃잎 = petal\n[Course]\n회로\n[Terminology]\n전압 = voltage\n")
MODELS = [{"model": "chosen-model", "displayName": "Chosen Model", "isDefault": True,
           "defaultReasoningEffort": "low", "supportedReasoningEfforts": [
               {"reasoningEffort": "low"}, {"reasoningEffort": "high"}]},
          {"model": "other-model", "displayName": "Other Model", "isDefault": False,
           "defaultReasoningEffort": "medium", "supportedReasoningEfforts": [{"reasoningEffort": "medium"}]}]


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
        self.panel._apply_codex_models(MODELS)
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

    def test_local_choice_reaches_cli_and_is_locked_during_run(self):
        self.assertEqual(self.panel.transcription_backend_combo.currentData(), "openai")
        self.assertFalse(self.panel.local_model_combo.isEnabled())
        self.panel.course_combo.setCurrentIndex(1)
        self.panel.transcription_backend_combo.setCurrentIndex(1)
        self.assertTrue(self.panel.local_model_combo.isEnabled())
        self.panel.local_model_combo.setCurrentIndex(1)
        self.panel.local_device_combo.setCurrentIndex(1)
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        args = start.call_args.args[1]
        for flag, value in (("--transcription-backend", "local"), ("--local-model", "medium"),
                            ("--local-device", "cpu")):
            self.assertEqual(args[args.index(flag) + 1], value)
        self.assertFalse(self.panel.transcription_backend_combo.isEnabled())
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertTrue(self.panel.local_model_combo.isEnabled())
        self.panel.transcription_backend_combo.setCurrentIndex(0)
        self.assertFalse(self.panel.local_model_combo.isEnabled())

    def test_local_pipeline_still_requires_key_for_translation(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel.transcription_backend_combo.setCurrentIndex(1)
        self.panel.key_field.setText(str(self.root / "missing-key.txt"))
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        start.assert_not_called()
        self.assertIn("실행 준비 실패", self.panel.status.text())

    def test_local_and_codex_launch_without_api_key_and_pass_model(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel.transcription_backend_combo.setCurrentIndex(1)
        self.panel.translation_backend_combo.setCurrentIndex(1)
        self.panel.codex_reasoning_combo.setCurrentIndex(1)
        self.panel.key_field.setText(str(self.root / "missing-key.txt"))
        self.assertFalse(self.panel.key_row.isEnabled())
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        args = start.call_args.args[1]
        self.assertEqual(args[args.index("--translation-backend") + 1], "codex")
        self.assertEqual(args[args.index("--codex-model") + 1], "chosen-model")
        self.assertEqual(args[args.index("--codex-reasoning") + 1], "high")
        self.assertFalse(self.panel.translation_backend_combo.isEnabled())
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.panel.transcription_backend_combo.setCurrentIndex(0)
        self.assertTrue(self.panel.key_row.isEnabled())
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        start.assert_not_called()

    def test_model_change_shows_only_supported_efforts_and_explicit_selection(self):
        self.panel.translation_backend_combo.setCurrentIndex(1)
        self.assertEqual(self.panel.codex_model_combo.currentData(), "chosen-model")
        self.assertEqual(self.panel.codex_reasoning_combo.currentData(), "low")
        self.panel.codex_model_combo.setCurrentIndex(1)
        self.assertEqual(self.panel.codex_reasoning_combo.count(), 1)
        self.assertEqual(self.panel.codex_reasoning_combo.currentData(), "medium")
        self.assertIn("other-model / 추론 medium", self.panel.codex_selection_note.text())

    def test_refresh_keeps_existing_model_and_effort(self):
        self.panel.codex_reasoning_combo.setCurrentIndex(1)
        self.panel._apply_codex_models(MODELS)
        self.assertEqual(self.panel.codex_reasoning_combo.currentData(), "high")

    def test_failed_initial_load_disables_run_until_catalog_arrives(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel._codex_models = {}
        self.panel.codex_model_combo.clear()
        with patch("qtTest.pipeline_panel.QThreadPool.globalInstance"):
            self.panel.translation_backend_combo.setCurrentIndex(1)
        self.assertTrue(self.panel._models_loading)
        self.assertFalse(self.panel.run_button.isEnabled())
        self.panel._codex_models_failed("load failed")
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertTrue(self.panel.codex_refresh_button.isEnabled())
        self.panel._apply_codex_models(MODELS)
        self.assertTrue(self.panel.run_button.isEnabled())


    def test_launch_uses_selected_course_and_immutable_snapshot_and_blocks_double_click(self):
        self.panel.course_combo.setCurrentIndex(1)
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
            self.panel.start_pipeline()
        self.assertEqual(start.call_count, 1)
        args = start.call_args.args[1]
        self.assertFalse(self.panel.parallel_render_checkbox.isChecked())
        self.assertNotIn("--parallel-render", args)
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

    def test_checked_parallel_option_reaches_cli_and_is_locked_during_run(self):
        self.panel.course_combo.setCurrentIndex(1)
        self.panel.parallel_render_checkbox.setChecked(True)
        with patch.object(self.panel.process, "start") as start:
            self.panel.start_pipeline()
        self.assertIn("--parallel-render", start.call_args.args[1])
        self.assertFalse(self.panel.parallel_render_checkbox.isEnabled())
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertTrue(self.panel.parallel_render_checkbox.isEnabled())

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

    def test_subtitle_notification_survives_split_utf8_and_precedes_completion(self):
        self.panel._set_busy(True)
        self.panel.result_folder = self.root
        received = []
        self.panel.subtitles_ready.connect(lambda *args: received.append(args))
        path = self.root / "영어 자막.srt"
        line = SUBTITLE_READY_PREFIX + json.dumps(
            {"video": str(self.video), "srt": str(path)}, ensure_ascii=False) + "\n"
        for byte in line.encode("utf-8"):
            self.panel._consume(self.panel._decoder.decode(bytes([byte])))
        self.assertEqual(received, [(str(self.video.resolve()), str(path.resolve()))])
        self.assertTrue(self.panel.busy)
        self.panel._finished(1, QProcess.ExitStatus.NormalExit)
        self.assertEqual(len(received), 1)

    def test_invalid_or_unrelated_subtitle_events_do_not_change_preview(self):
        self.panel._set_busy(True)
        self.panel.result_folder = self.root
        received = []
        self.panel.subtitles_ready.connect(lambda *args: received.append(args))
        for event in ("{", "[]", json.dumps({"video": str(self.video), "srt": None}),
                      json.dumps({"video": str(self.video), "srt": str(self.root.parent / 'other.srt')}),
                      json.dumps({"video": str(self.root / 'other.mp4'), "srt": str(self.root / 'a.srt')})):
            self.panel._handle_line(SUBTITLE_READY_PREFIX + event)
        self.assertEqual(received, [])
        self.panel._set_busy(False)

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

