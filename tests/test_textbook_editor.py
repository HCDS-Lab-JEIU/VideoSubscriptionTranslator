"""실제 API 없이 편집/저장/Qt 동작을 검증합니다."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLineEdit, QMessageBox

from textbook import Textbook
from qtTest.textbook_editor.data import TextbookRepository
from qtTest.textbook_editor.editor import TextbookEditor


SOURCE = ("[Common Rules]\nCommon\n[Whisper Rules]\nWhisper\n"
          "[Translation Rules]\nTranslate\n[Course]\n회로\n[Terminology]\n전압 = voltage\n")


class EditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "book.txt"
        self.path.write_text(SOURCE, encoding="utf-8")
        self.repository = TextbookRepository(self.path)

    def test_round_trip_preserves_rules_and_separate_courses(self):
        document = self.repository.load()
        index = document.add_course("프로그래밍")
        document.courses[index].rows = [["전압", "another meaning"]]
        document.courses[0].rows[0][1] = "electric potential"
        self.repository.save(document)
        book = Textbook.load(self.path)
        self.assertEqual((book.common_rules, book.whisper_rules, book.translation_rules),
                         ("Common", "Whisper", "Translate"))
        self.assertEqual(book.courses[0].terminology["전압"], "electric potential")
        self.assertEqual(book.courses[1].terminology["전압"], "another meaning")
        self.assertFalse(document.dirty)

    def test_invalid_or_conflicting_save_preserves_original(self):
        for rows in ([["", "empty"]], [["전압", ""]], [["전압", "v"], ["전압", "V"]],
                     [["bad=key", "value"]], [["#comment", "value"]], []):
            with self.subTest(rows=rows):
                document = self.repository.load()
                document.courses[0].rows = rows
                with self.assertRaises(ValueError):
                    self.repository.save(document)
                self.assertEqual(self.path.read_text(encoding="utf-8"), SOURCE)
        document = self.repository.load()
        self.path.write_text(SOURCE + "# external edit\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "다른 프로그램"):
            self.repository.save(document)
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("# external edit\n"))

    def test_atomic_replace_failure_preserves_file(self):
        document = self.repository.load()
        document.courses[0].rows[0][1] = "edited"
        with patch("qtTest.textbook_editor.data.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                self.repository.save(document)
        self.assertEqual(self.path.read_text(encoding="utf-8"), SOURCE)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_new_file_and_duplicate_course(self):
        repository = TextbookRepository(self.path.parent / "new.txt")
        document = repository.load()
        document.add_course("회로")
        with self.assertRaises(ValueError):
            document.add_course(" 회로 ")
        document.courses[0].rows = [["전압", "voltage"]]
        repository.save(document)
        self.assertEqual(Textbook.load(repository.path).course, "회로")

    def test_table_edit_switch_add_remove_save_and_scroll(self):
        widget = TextbookEditor(self.repository)
        widget.resize(640, 400)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()
        model = widget.model
        model.setData(model.index(0, 1), "edited voltage")
        with patch("qtTest.textbook_editor.editor.QInputDialog.getText", return_value=("프로그래밍", True)):
            widget.add_course_button.click()
        model.setData(model.index(0, 0), "반복문")
        model.setData(model.index(0, 1), "loop")
        widget.course_selector.setCurrentIndex(0)
        self.assertEqual(model.data(model.index(0, 1)), "edited voltage")
        for i in range(100):
            model.append_row()
            model.setData(model.index(i + 1, 0), f"단어{i}")
            model.setData(model.index(i + 1, 1), f"term{i}")
        model.remove_rows([100])
        self.app.processEvents()
        self.assertGreater(widget.table.verticalScrollBar().maximum(), 0)
        self.assertLessEqual(widget.table.height(), widget.height())
        self.assertEqual(widget.height(), 400)
        self.assertTrue(widget.save())
        book = Textbook.load(self.path)
        self.assertEqual(len(book.courses[0].terminology), 100)
        self.assertEqual(book.courses[1].terminology, {"반복문": "loop"})

    def test_active_cell_committed_on_save_and_close_can_cancel(self):
        widget = TextbookEditor(self.repository)
        widget.show()
        self.addCleanup(widget.close)
        self.app.processEvents()
        widget.table.setFocus()
        widget.table.edit(widget.model.index(0, 1))
        self.app.processEvents()
        editor = widget.table.findChild(QLineEdit)
        self.assertIsNotNone(editor)
        editor.setText("active edit")
        self.assertTrue(widget.save())
        self.assertEqual(Textbook.load(self.path).terminology["전압"], "active edit")
        widget.model.setData(widget.model.index(0, 1), "unsaved")
        with patch("qtTest.textbook_editor.editor.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(widget.confirm_close())

    def test_open_and_edit_all_rules(self):
        widget = TextbookEditor()
        self.addCleanup(widget.close)
        with patch("qtTest.textbook_editor.editor.QFileDialog.getOpenFileName", return_value=(str(self.path), "")):
            self.assertTrue(widget.open_file())
        self.assertFalse(widget.document.dirty)
        for name, editor in widget.rule_editors.items():
            editor.setPlainText(f"Edited {name}\nSecond line")
        self.assertTrue(widget.document.dirty)
        self.assertTrue(widget.save())
        book = Textbook.load(self.path)
        for name in widget.rule_editors:
            self.assertEqual(getattr(book, name), f"Edited {name}\nSecond line")

    def test_open_cancel_discard_and_failure_preserve_document(self):
        widget = TextbookEditor(self.repository)
        self.addCleanup(widget.close)
        widget.rule_editors["common_rules"].setPlainText("Unsaved")
        original = widget.document
        other = self.path.parent / "other.txt"
        other.write_text(SOURCE.replace("\nCommon\n", "\nNew common\n"), encoding="utf-8")
        with patch("qtTest.textbook_editor.editor.QFileDialog.getOpenFileName", return_value=(str(other), "")), \
             patch("qtTest.textbook_editor.editor.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(widget.open_file())
        self.assertIs(widget.document, original)
        other.write_text("invalid file", encoding="utf-8")
        with patch("qtTest.textbook_editor.editor.QFileDialog.getOpenFileName", return_value=(str(other), "")), \
             patch("qtTest.textbook_editor.editor.QMessageBox.warning"):
            self.assertFalse(widget.open_file())
        self.assertIs(widget.document, original)
        other.write_text(SOURCE, encoding="utf-8")
        with patch("qtTest.textbook_editor.editor.QFileDialog.getOpenFileName", return_value=(str(other), "")), \
             patch("qtTest.textbook_editor.editor.QMessageBox.question", return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(widget.open_file())
        self.assertEqual(widget.rule_editors["common_rules"].toPlainText(), "Common")
        self.assertFalse(widget.document.dirty)
        self.assertEqual(widget.repository.path, other)

    def test_open_same_file_after_save_reads_latest_rules(self):
        widget = TextbookEditor(self.repository)
        self.addCleanup(widget.close)
        widget.rule_editors["common_rules"].setPlainText("Saved before open")
        with patch("qtTest.textbook_editor.editor.QFileDialog.getOpenFileName", return_value=(str(self.path), "")), \
             patch("qtTest.textbook_editor.editor.QMessageBox.question", return_value=QMessageBox.StandardButton.Save):
            self.assertTrue(widget.open_file())
        self.assertEqual(widget.rule_editors["common_rules"].toPlainText(), "Saved before open")

    def test_new_document_uses_save_dialog(self):
        widget = TextbookEditor()
        self.addCleanup(widget.close)
        with patch("qtTest.textbook_editor.editor.QInputDialog.getText", return_value=("새 과목", True)):
            widget.add_course_button.click()
        widget.model.setData(widget.model.index(0, 0), "단어")
        widget.model.setData(widget.model.index(0, 1), "term")
        widget.rule_editors["translation_rules"].setPlainText("Translate")
        target = self.path.parent / "new.txt"
        with patch("qtTest.textbook_editor.editor.QFileDialog.getSaveFileName", return_value=(str(target), "")):
            self.assertTrue(widget.save())
        self.assertEqual(Textbook.load(target).translation_rules, "Translate")
        self.assertEqual(widget.repository.path, target)

    def test_rule_section_injection_does_not_overwrite_file(self):
        document = self.repository.load()
        document.set_rule("common_rules", "[Course]\ninjected")
        with self.assertRaises(ValueError):
            self.repository.save(document)
        self.assertEqual(self.path.read_text(encoding="utf-8"), SOURCE)


if __name__ == "__main__":
    unittest.main()
