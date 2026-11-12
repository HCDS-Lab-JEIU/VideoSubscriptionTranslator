"""규칙 분리, 여러 과목의 용어 보존, 잘못된 파일 검증."""

from pathlib import Path
import tempfile
import unittest

from subtitle_app.textbook.document import Textbook


class TextbookTests(unittest.TestCase):
    def test_gpt_prompt_includes_selected_term_spellings_and_no_fabrication_rules(self):
        book = Textbook.parse("[Course]\nAI/ML\n[Terminology]\n꽃잎 = petal\n꽃받침 = sepal\n"
                              "[Course]\n회로\n[Terminology]\n전압 = voltage\n")
        prompt = book.select_course("AI/ML").accurate_transcription_prompt()
        self.assertIn("꽃잎 (petal)", prompt)
        self.assertIn("꽃받침 (sepal)", prompt)
        self.assertNotIn("voltage", prompt)
        self.assertIn("추측해 채우지 마세요", prompt)

    def load(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "textbook.txt"
            path.write_text(content, encoding="utf-8-sig")
            return Textbook.load(path)

    def test_rules_are_routed_and_subject_terms_remain_separate(self):
        book = self.load(
            "# example\n[Common Rules]\nCOMMON\n[Whisper Rules]\nWHISPER\n"
            "[Translation Rules]\nTRANSLATION\n[Course]\n회로\n"
            "[Terminology]\n소스 = source terminal\n[Course]\n프로그래밍\n"
            "[Terminology]\n소스 = source code\n"
        )
        self.assertEqual([c.name for c in book.courses], ["회로", "프로그래밍"])
        self.assertEqual(book.courses[0].terminology["소스"], "source terminal")
        self.assertEqual(book.courses[1].terminology["소스"], "source code")
        selected = book.select_course("회로")
        whisper = selected.transcription_prompt()
        translation = selected.translation_prompt()
        for prompt in (whisper, translation):
            self.assertIn("COMMON", prompt)
            self.assertIn("회로", prompt)
            self.assertNotIn("프로그래밍", prompt)
        self.assertIn("WHISPER", whisper)
        self.assertTrue(whisper.endswith("WHISPER"))
        self.assertNotIn("TRANSLATION", whisper)
        self.assertNotIn("source terminal", whisper)
        self.assertNotIn("source code", whisper)
        self.assertIn("TRANSLATION", translation)
        self.assertNotIn("WHISPER", translation)
        self.assertIn("Course: 회로\n\nTerminology:\n소스 = source terminal", translation)
        self.assertNotIn("source code", translation)
        self.assertIn("source code", book.select_course("프로그래밍").translation_prompt())
        with self.assertRaises(ValueError):
            _ = book.terminology

    def test_course_selection_rejects_missing_unknown_and_ambiguous_names(self):
        book = Textbook.parse("[Course]\nAI Basics\n[Terminology]\n기초 = basics\n"
                              "[Course]\nAI Advanced\n[Terminology]\n심화 = advanced\n")
        for selector in (None, "", "AI", "missing", "0", "3", "-1"):
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                book.select_course(selector)
        self.assertEqual(book.select_course("2").course, "AI Advanced")
        self.assertEqual(book.select_course("basics").course, "AI Basics")
        self.assertEqual(book.select_course(" AI BASICs ").course, "AI Basics")
        for method in (book.transcription_prompt, book.translation_prompt):
            with self.assertRaises(ValueError):
                method()
        selected = book.select_course("1")
        selected.terminology["새 단어"] = "new"
        self.assertNotIn("새 단어", book.courses[0].terminology)

    def test_legacy_format_and_case_insensitive_headers(self):
        book = self.load("[course]\n회로\n[TERMINOLOGY]\n전압 = voltage\n"
                         "[Translation instructions]\nTranslate.\n")
        self.assertEqual(book.course, "회로")
        self.assertEqual(book.terminology, {"전압": "voltage"})
        self.assertEqual(book.transcription_prompt(), "회로 강의. 전압.")
        self.assertEqual(book.translation_instructions, "Translate.")
        self.assertTrue(book.translation_prompt().startswith("Translate."))

    def test_translation_requires_its_own_rules(self):
        book = self.load("[Common Rules]\nCommon\n[Course]\n회로\n[Terminology]\n전압 = voltage")
        self.assertIn("전압", book.transcription_prompt())
        with self.assertRaisesRegex(ValueError, "Translation Rules"):
            book.translation_prompt()

    def test_invalid_structure_is_rejected(self):
        valid = "[Course]\n회로\n[Terminology]\n전압 = voltage\n"
        cases = [
            "", "unsectioned text", "[Unknown]\nvalue", "[Terminology]\n전압 = voltage",
            "[Course]\n[Terminology]\n전압 = voltage",
            valid + "[Course]\n프로그래밍\n",
            "[Course]\n빈 과목\n" + valid,
            valid + valid,
            valid + "전압 = V",
            valid + "invalid term",
            valid + " = empty",
            valid + "빈 값 = ",
            "[Common Rules]\na\n[Common Rules]\nb\n" + valid,
            "[Translation Rules]\na\n[Translation instructions]\nb\n" + valid,
        ]
        for content in cases:
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.load(content)


if __name__ == "__main__":
    unittest.main()
