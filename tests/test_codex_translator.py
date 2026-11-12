"""Codex transport, shared checkpoints, CLI routing; no real model requests."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from codex_translator import CodexSubtitleTranslator, check_codex_login, codex_command
from subtitle_translator import SubtitleTranslationError, SubtitleTranslator
from transcript_reader import TranscriptReader


class CodexTranslatorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.book = self.root / "book.txt"
        self.book.write_text("[Translation Rules]\nTranslate faithfully.\n[Course]\n회로\n"
                             "[Terminology]\n전압 = voltage\n", encoding="utf-8")
        self.source = self.root / "lecture_kr.txt"
        self.source.write_text("[00:00:01.000, 00:00:02.000] 전압입니다.\n"
                               "[00:00:02.000, 00:00:04.000] 저항입니다.\n", encoding="utf-8")
        self.addCleanup(patch.stopall)
        patch("codex_models.list_codex_models", return_value=[{
            "model": "chosen-model", "isDefault": True, "defaultReasoningEffort": "medium",
            "supportedReasoningEfforts": [{"reasoningEffort": "medium"}, {"reasoningEffort": "high"}],
        }]).start()
        self.translator = CodexSubtitleTranslator(self.book)
        patch("codex_translator.check_codex_login", return_value=["fake-codex.exe"]).start()
        self.api = patch("subtitle_translator.OpenAI", side_effect=AssertionError("No API allowed")).start()
        self.key = patch("subtitle_translator.load_api_key", side_effect=AssertionError("No key needed")).start()

    @staticmethod
    def reply(args, **kwargs):
        schema = json.loads(Path(args[args.index("--output-schema") + 1]).read_text())
        result = {key: f"English {key}" for key in schema["required"]}
        Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result), encoding="utf-8")
        return SimpleNamespace(returncode=0, stderr=b"", stdout=b"ignored log output")

    def test_transport_preserves_timestamps_and_uses_stdin_and_saved_login(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "private-key", "CODEX_API_KEY": "private-key"}), \
             patch("codex_translator.subprocess.run", side_effect=self.reply) as run:
            output = self.translator.translate(self.source)
        self.assertEqual(output.read_text(encoding="utf-8"),
                         "[00:00:01.000, 00:00:02.000] English 0\n[00:00:02.000, 00:00:04.000] English 1\n")
        args, options = run.call_args.args[0], run.call_args.kwargs
        self.assertEqual(args[-1], "-")
        self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
        self.assertIn("--ignore-user-config", args)
        self.assertIn("--ephemeral", args)
        self.assertEqual(args[args.index("--model") + 1], "chosen-model")
        self.assertIn('model_reasoning_effort="medium"', args)
        self.assertNotIn("전압", " ".join(args))
        self.assertIn("전압 = voltage", options["input"].decode("utf-8"))
        self.assertNotIn("OPENAI_API_KEY", options["env"])
        self.assertNotIn("CODEX_API_KEY", options["env"])
        self.assertNotIn("shell", options)
        self.assertFalse(Path(options["cwd"]).exists())
        self.api.assert_not_called()
        self.key.assert_not_called()

    def test_requested_model_is_passed_exactly_and_changes_checkpoint_identity(self):
        self.translator = CodexSubtitleTranslator(self.book, model="chosen-model")
        with patch("codex_translator.subprocess.run", side_effect=self.reply) as run:
            output = self.translator.translate(self.source)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--model") + 1], "chosen-model")
        state = json.loads(output.with_suffix(".translation.json").read_text())
        self.assertEqual(state["model"], "codex-cli/chosen-model/reasoning=medium")

    def test_explicit_reasoning_reaches_cli_and_checkpoint(self):
        translator = CodexSubtitleTranslator(self.book, model="chosen-model", reasoning="high")
        with patch("codex_translator.subprocess.run", side_effect=self.reply) as run:
            output = translator.translate(self.source)
        self.assertIn('model_reasoning_effort="high"', run.call_args.args[0])
        output.unlink()
        with self.assertRaisesRegex(ValueError, "이전 번역"):
            self.translator.translate(self.source)

    def test_timeout_is_actionable_and_creates_no_completed_output(self):
        with patch("codex_translator.subprocess.run", side_effect=subprocess.TimeoutExpired("codex", 600)), \
             self.assertRaisesRegex(SubtitleTranslationError, "대기 시간"):
            self.translator.translate(self.source)
        self.assertFalse((self.root / "lecture_en.txt").exists())

    def test_failed_cli_does_not_expose_raw_diagnostics(self):
        with patch("codex_translator.subprocess.run", return_value=SimpleNamespace(
                returncode=1, stderr=b"quota exceeded private-key private-lecture")), \
             self.assertRaises(SubtitleTranslationError) as caught:
            self.translator.translate(self.source)
        self.assertIn("사용 한도", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))

    def test_missing_and_malformed_response_are_rejected(self):
        with patch("codex_translator.subprocess.run", return_value=SimpleNamespace(returncode=0)), \
             self.assertRaisesRegex(SubtitleTranslationError, "최종 번역"):
            self.translator.translate(self.source)
        def malformed(args, **kwargs):
            Path(args[args.index("--output-last-message") + 1]).write_text("not JSON")
            return SimpleNamespace(returncode=0)
        with patch("codex_translator.subprocess.run", side_effect=malformed), \
             self.assertRaisesRegex(SubtitleTranslationError, "JSON"):
            self.translator.translate(self.source)

    def test_ids_and_types_must_match_exactly(self):
        for response in ({"0": "one"}, {"0": "one", "1": 2}, ["one", "two"]):
            def respond(args, **kwargs):
                Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(response))
                return SimpleNamespace(returncode=0)
            with self.subTest(response=response), patch("codex_translator.subprocess.run", side_effect=respond), \
                 self.assertRaises(SubtitleTranslationError):
                self.translator.translate(self.source)

    def test_empty_translation_retries_only_missing_id(self):
        with patch.object(self.translator, "_request_translations", side_effect=[
            {"0": "Voltage", "1": ""}, {"1": "Resistance"},
        ]) as request:
            result = self.translator.translate(self.source)
        self.assertEqual(request.call_args_list[1].args[-1], [1])
        self.assertIn("Resistance", result.read_text())

    def test_failed_later_batch_resumes_only_unfinished_segments(self):
        self.translator.BATCH_SIZE = 1
        with patch.object(self.translator, "_request_translations", side_effect=[
                {"0": "Voltage"}, SubtitleTranslationError("offline")]), self.assertRaises(SubtitleTranslationError):
            self.translator.translate(self.source)
        checkpoint = self.root / "lecture_en.translation.json"
        self.assertEqual(len(json.loads(checkpoint.read_text())["segments"]), 1)
        with patch.object(self.translator, "_request_translations", return_value={"1": "Resistance"}) as request:
            self.translator.translate(self.source)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[-1], [1])

    def test_api_checkpoint_cannot_be_reused_as_codex(self):
        with patch.object(self.translator, "_request_translations", side_effect=SubtitleTranslationError("stop")), \
             self.assertRaises(SubtitleTranslationError):
            self.translator.translate(self.source)
        # Complete Codex translation, then remove only final output to exercise checkpoint comparison.
        with patch("codex_translator.subprocess.run", side_effect=self.reply):
            output = self.translator.translate(self.source)
        output.unlink()
        api = SubtitleTranslator(self.root / "missing-key", self.book)
        with self.assertRaisesRegex(ValueError, "이전 번역"):
            api.translate(self.source)

    def test_context_is_included_without_timestamp_rewrites(self):
        lines = TranscriptReader().read(self.source)
        with patch("codex_translator.subprocess.run", side_effect=self.reply) as run:
            self.translator._request_translations(["fake.exe"], "Translate", lines, [1])
        prompt = run.call_args.kwargs["input"].decode("utf-8")
        self.assertIn('"context_before": ["전압입니다."]', prompt)

    def test_login_failure_does_not_echo_diagnostics(self):
        with patch("codex_translator.codex_command", return_value=["fake.exe"]), \
             patch("codex_translator.subprocess.run", return_value=SimpleNamespace(returncode=1)), \
             self.assertRaisesRegex(SubtitleTranslationError, "로그인"):
            check_codex_login()

    def test_explicit_missing_cli_is_rejected(self):
        with self.assertRaisesRegex(SubtitleTranslationError, "실행 파일"):
            codex_command(self.root / "missing.exe")

    def test_cli_codex_translation_requires_no_api_key(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", str(self.source), "--translate", "--translation-backend", "codex",
                                "--textbook-file", str(self.book), "--api-key-file", str(self.root / "missing-key")]), \
             patch("codex_translator.subprocess.run", side_effect=self.reply):
            self.assertEqual(cli.main(), 0)
