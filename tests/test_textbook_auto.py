"""PPT extraction, provider requests, cancellation and non-destructive review."""

import json
import os
from pathlib import Path
from threading import Event
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from zipfile import ZipFile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtCore import QEventLoop, QMimeData, QPointF, Qt, QTimer, QUrl
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QDialog

from subtitle_app.textbook.presentation_text import read_presentation, SlideText
from subtitle_app.textbook.document import Textbook
from subtitle_app.textbook.auto import generate_terms, GenerationCancelled, TermCandidate
from subtitle_app.ui.textbook_editor.auto_dialog import AutoTextbookDialog
from subtitle_app.ui.textbook_editor.data import TextbookDocument, TextbookRepository
from subtitle_app.ui.textbook_editor.editor import TextbookEditor


def write_pptx(path, texts, order=None):
    order = order or list(range(1, len(texts) + 1))
    with ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml", '<p:presentation xmlns:p="urn:p" xmlns:r="urn:r"><p:sldIdLst>'
                         + ''.join(f'<p:sldId id="{i}" r:id="r{i}"/>' for i in order)
                         + '</p:sldIdLst></p:presentation>')
        archive.writestr("ppt/_rels/presentation.xml.rels", '<Relationships>' + ''.join(
            f'<Relationship Id="r{i}" Type="urn/slide" Target="slides/slide{i}.xml"/>'
            for i in range(1, len(texts) + 1)) + '</Relationships>')
        for i, text in enumerate(texts, 1):
            archive.writestr(f"ppt/slides/slide{i}.xml", '<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><p:spTree>'
                             + ''.join(f'<a:p><a:r><a:t>{escape(line)}</a:t></a:r></a:p>' for line in text.splitlines())
                             + '</p:spTree></p:sld>')


SOURCE = "[Common Rules]\nKeep terms\n[Translation Rules]\nTranslate English\n[Course]\n회로\n[Terminology]\n전압 = voltage\n"


class AutoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ppt = self.root / "강의.pptx"
        write_pptx(self.ppt, ["Voltage 전압\nCurrent 전류", "Resistance 저항", ""])
        self.key = self.root / "key.txt"
        self.key.write_text("fake-key", encoding="utf-8")
        self.doc = TextbookDocument(Textbook.parse(SOURCE))

    def options(self, **kwargs):
        return dict(paths=[self.ppt], course="회로", rules=self.doc.rules, existing={"전압": "voltage"},
                    backend="codex", model="chosen-model", reasoning="low", **kwargs)

    def dialog(self):
        dialog = AutoTextbookDialog(self.doc, 0)
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_slide_order_multiline_and_empty_slide_preserved(self):
        write_pptx(self.ppt, ["First\nTable text", "Second", ""], [2, 1, 3])
        slides = read_presentation(self.ppt)
        self.assertEqual([slide.text for slide in slides], ["Second", "First\nTable text", ""])
        self.assertEqual([slide.number for slide in slides], [1, 2, 3])

    def test_legacy_ppt_converts_temporary_copy_preserving_source(self):
        old = self.root / "legacy.ppt"
        old.write_bytes(b"original")
        def convert(source, target):
            self.assertEqual(source, old)
            write_pptx(target, ["Old presentation"])
        with patch("subtitle_app.textbook.presentation_text._convert_ppt", side_effect=convert):
            self.assertEqual(read_presentation(old)[0].file, "legacy.ppt")
        self.assertEqual(old.read_bytes(), b"original")

    def test_malformed_ppt_fails_before_generation(self):
        self.ppt.write_bytes(b"broken")
        with patch("subtitle_app.textbook.auto.check_codex_login"), patch("subtitle_app.textbook.auto.request_codex_json") as request:
            with self.assertRaisesRegex(ValueError, "PPT"):
                generate_terms(**self.options())
            request.assert_not_called()

    def test_codex_uses_all_files_rules_and_selected_model_without_api_key(self):
        second = self.root / "second.pptx"
        write_pptx(second, ["Current 전류"])
        options = self.options()
        options["paths"].append(second)
        response = {"terms": [{"korean": "전류", "english": "current", "source_ids": [1, 3]}]}
        with patch("subtitle_app.textbook.auto.check_codex_login", return_value=["codex.exe"]), \
             patch("subtitle_app.textbook.auto.load_api_key") as key, \
             patch("subtitle_app.textbook.auto.request_codex_json", return_value=response) as request:
            result = generate_terms(**options)
        key.assert_not_called()
        self.assertEqual(result[0].korean, "전류")
        self.assertIn("second.pptx", result[0].sources)
        self.assertIn("Keep terms", request.call_args.args[1])
        self.assertIn("Resistance", request.call_args.args[1])
        self.assertEqual(request.call_args.kwargs["model"], "chosen-model")
        self.assertEqual(request.call_args.kwargs["reasoning"], "low")

    def test_api_uses_structured_output_and_rejects_incomplete_response(self):
        options = self.options()
        options.update(backend="openai", api_key_path=self.key)
        response = SimpleNamespace(status="completed", output_text=json.dumps(
            {"terms": [{"korean": "저항", "english": "resistance", "source_ids": [2]}]}))
        with patch("subtitle_app.textbook.auto.OpenAI") as api:
            client = api.return_value.__enter__.return_value
            client.responses.create.return_value = response
            self.assertEqual(generate_terms(**options)[0].english, "resistance")
            args = client.responses.create.call_args.kwargs
            self.assertEqual(args["text"]["format"]["type"], "json_schema")
            self.assertFalse(args["store"])
            response.status = "incomplete"
            with self.assertRaisesRegex(RuntimeError, "완료된"):
                generate_terms(**options)

    def test_invalid_terms_sources_and_cancel_never_return_partial_results(self):
        for item in ({"korean": "[Course]", "english": "bad", "source_ids": [1]},
                     {"korean": "전류", "english": "current", "source_ids": [99]},
                     {"korean": "전류", "english": "current", "source_ids": [True]}):
            with patch("subtitle_app.textbook.auto.check_codex_login"), \
                 patch("subtitle_app.textbook.auto.request_codex_json", return_value={"terms": [item]}):
                with self.assertRaises(ValueError):
                    generate_terms(**self.options())
        cancel = Event()
        def response(*args, **kwargs):
            cancel.set()
            return {"terms": []}
        with patch("subtitle_app.textbook.auto.check_codex_login"), \
             patch("subtitle_app.textbook.auto.request_codex_json", side_effect=response):
            with self.assertRaises(GenerationCancelled):
                generate_terms(**self.options(cancel=cancel))

    def test_long_slide_is_chunked_without_discarding_text(self):
        slide = SlideText("large.pptx", 1, "X" * 40000)
        with patch("subtitle_app.textbook.auto.check_codex_login"), \
             patch("subtitle_app.textbook.auto.read_presentation", return_value=[slide]), \
             patch("subtitle_app.textbook.auto.request_codex_json", return_value={"terms": []}) as request:
            generate_terms(**self.options())
        chunks = [json.loads(call.args[1].split("\nSlide data:\n")[1]) for call in request.call_args_list]
        self.assertEqual(sum(len(record["text"]) for chunk in chunks for record in chunk), 40000)
        self.assertGreater(len(chunks), 1)

    def test_open_and_drop_multiple_files_deduplicate_and_reject_non_ppt(self):
        dialog = self.dialog()
        second = self.root / "other.ppt"
        second.write_bytes(b"test")
        with patch("subtitle_app.ui.textbook_editor.auto_dialog.QFileDialog.getOpenFileNames",
                   return_value=([str(self.ppt), str(second)], "")):
            dialog.open_files()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.ppt)), QUrl.fromLocalFile(str(self.key))])
        event = QDropEvent(QPointF(1, 1), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        dialog.files.dropEvent(event)
        self.assertEqual(dialog.files.count(), 2)
        self.assertIn("제외", dialog.status.text())

    def test_review_disables_existing_and_conflicting_terms_and_validates_edits(self):
        dialog = self.dialog()
        dialog.target_course = "회로"
        dialog._show_candidates([TermCandidate("전압", "potential", "slide 1"),
                                 TermCandidate("전류", "current", "slide 2"),
                                 TermCandidate("전류", "amperage", "slide 3")])
        self.assertEqual(dialog.table.item(0, 0).checkState(), Qt.CheckState.Unchecked)
        self.assertEqual(dialog.table.item(2, 0).checkState(), Qt.CheckState.Unchecked)
        dialog.table.item(1, 2).setText("")
        dialog.apply_selection()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.table.item(1, 2).setText("electric current")
        dialog.apply_selection()
        self.assertEqual(dialog.selected_terms, [("전류", "electric current")])
        self.assertFalse(self.doc.dirty)

    def test_merge_preserves_rules_and_is_atomic_on_conflicts(self):
        before = self.doc.to_textbook()
        with self.assertRaises(ValueError):
            self.doc.add_generated_terms("회로", [("전류", "current"), ("전압", "changed")])
        self.assertEqual(self.doc.to_textbook(), before)
        self.assertFalse(self.doc.dirty)
        index, count = self.doc.add_generated_terms("회로", [("전류", "current")])
        self.assertEqual((index, count), (0, 1))
        self.assertEqual(self.doc.rules["common_rules"], "Keep terms")
        self.assertEqual(self.doc.to_textbook().terminology["전압"], "voltage")
        self.doc.add_course("새 과목")
        self.doc.add_generated_terms("새 과목", [("저항", "resistance")])
        self.assertEqual(self.doc.courses[1].rows, [["저항", "resistance"]])

    def test_auto_button_merges_reviewed_terms_without_saving(self):
        path = self.root / "book.txt"
        path.write_text(SOURCE, encoding="utf-8")
        editor = TextbookEditor(TextbookRepository(path))
        self.addCleanup(editor.deleteLater)
        with patch("subtitle_app.ui.textbook_editor.editor.AutoTextbookDialog") as factory:
            dialog = factory.return_value
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.target_course = "회로"
            dialog.selected_terms = [("전류", "current")]
            editor.auto_button.click()
        self.assertEqual(editor.model.rowCount(), 2)
        self.assertTrue(editor.document.dirty)
        self.assertEqual(path.read_text(encoding="utf-8"), SOURCE)

    def test_real_worker_does_not_block_ui_and_cancel_restores_controls(self):
        dialog = self.dialog()
        dialog.add_files([self.ppt])
        entered, release = Event(), Event()
        def generation(**options):
            entered.set()
            release.wait(3)
            return [TermCandidate("전류", "current", "slide 1")]
        loop = QEventLoop()
        heartbeat = []
        def tick():
            heartbeat.append(True)
            if entered.is_set():
                dialog.reject()
                release.set()
            if not dialog.busy:
                loop.quit()
        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(10)
        with patch("subtitle_app.ui.textbook_editor.auto_dialog.generate_terms", side_effect=generation):
            dialog.start_generation()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
        timer.stop()
        release.set()
        if dialog.worker:
            dialog.worker.wait(5000)
            self.app.processEvents()
        self.assertTrue(heartbeat)
        self.assertFalse(dialog.busy)
        self.assertTrue(dialog.close_button.isEnabled())
        self.assertFalse(dialog.apply_button.isEnabled())
        self.assertFalse(self.doc.dirty)
