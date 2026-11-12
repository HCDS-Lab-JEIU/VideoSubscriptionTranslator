"""메인 창과 텍스트북 편집창의 수명 및 종료 처리를 검증합니다."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from subtitle_app.ui.main_window import MyApp


class PlayerStub(QWidget):
    error_occurred = pyqtSignal(str)

    def clear_subtitles(self):
        pass


class MainEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch("subtitle_app.ui.main_window.QVideoPlayer", PlayerStub):
            self.window = MyApp()
        self.window.show()
        self.app.processEvents()
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.window.close()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_menu_reuses_editor_and_reopens_after_close(self):
        self.window.textbook_action.trigger()
        editor_window = self.window.textbook_window
        self.assertTrue(editor_window.isWindow())
        self.assertTrue(editor_window.isVisible())
        self.assertIs(editor_window.parent(), self.window)
        editor_window.editor.rule_editors["common_rules"].setPlainText("draft")
        self.window.textbook_action.trigger()
        self.assertIs(self.window.textbook_window, editor_window)
        self.assertEqual(editor_window.editor.document.rules["common_rules"], "draft")
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(editor_window.close())
        self.assertTrue(editor_window.isVisible())
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(editor_window.close())
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertIsNone(self.window.textbook_window)
        self.window.textbook_action.trigger()
        self.assertIsNot(self.window.textbook_window, editor_window)

    def test_main_close_respects_cancel_and_failed_save(self):
        self.window.open_textbook_editor()
        editor = self.window.textbook_window.editor
        editor.rule_editors["whisper_rules"].setPlainText("unsaved")
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.textbook_window.isVisible())
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Save), \
             patch.object(editor, "save", return_value=False):
            self.assertFalse(self.window.close())
        self.assertEqual(editor.document.rules["whisper_rules"], "unsaved")
        with patch("subtitle_app.ui.textbook_editor.editor.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.close())
        self.assertFalse(self.window.isVisible())

    def test_main_stays_open_while_pipeline_is_running(self):
        self.window.pipeline_panel._set_busy(True)
        self.assertFalse(self.window.close())
        self.assertTrue(self.window.isVisible())
        self.window.pipeline_panel._set_busy(False)
        self.assertTrue(self.window.close())


if __name__ == "__main__":
    unittest.main()
