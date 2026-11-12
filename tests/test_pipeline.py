"""외부 요청 없이 전체 단계 연결과 실패 시 중단을 검증합니다."""

import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from subtitle_app.media.media_file import MediaFile
from subtitle_app.pipeline.runner import run_pipeline
from subtitle_app.pipeline.events import SUBTITLE_READY_PREFIX


class PipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.video = self.root / "강의_kr.mp4"
        self.video.write_bytes(b"video")
        self.key = self.root / "key.txt"
        self.key.write_text("test-key", encoding="utf-8")
        self.book = self.root / "book.txt"
        self.book.write_text("[Course]\n회로\n[Terminology]\n전압 = voltage\n", encoding="utf-8")

    def run_pipeline(self, **options):
        return run_pipeline(self.video, self.root / "runs", self.key, self.book, **options)

    def test_stage_handoff_srt_and_unique_runs(self):
        render_modes = []
        logs = io.StringIO()
        def extract(extractor, video):
            self.assertEqual(video.file_path, self.video)
            path = extractor.output_dir / f"{video.file_path.stem}.mp3"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"audio")
            return MediaFile(path)

        def transcribe(transcriber, audio):
            self.assertEqual(transcriber.course, "회로")
            self.assertEqual(audio.file_path.read_bytes(), b"audio")
            path = transcriber.output_dir / f"{audio.file_path.stem}.txt"
            path.parent.mkdir(parents=True)
            path.write_text("[00:00:00.000, 00:00:01.000] 전압\n", encoding="utf-8")
            return MediaFile(path)

        def translate(translator, source):
            self.assertEqual(translator.course, "회로")
            self.assertIn("전압", source.read_text(encoding="utf-8"))
            path = translator._output_path(source)
            path.write_text("[00:00:00.000, 00:00:01.000] Voltage\n", encoding="utf-8")
            return path

        def render(renderer, video, srt, output, *, parallel=False):
            render_modes.append(parallel)
            # The complete file and flushed notification must exist before encoding.
            import json
            event = [line for line in logs.getvalue().splitlines()
                     if line.startswith(SUBTITLE_READY_PREFIX)][-1]
            self.assertEqual(json.loads(event.removeprefix(SUBTITLE_READY_PREFIX)),
                             {"video": str(video.resolve()), "srt": str(srt.resolve())})
            self.assertEqual(video, self.video)
            self.assertEqual(srt.read_text(encoding="utf-8"),
                             "1\n00:00:00,000 --> 00:00:01,000\nVoltage\n\n")
            output.write_bytes(b"rendered")
            return output

        with contextlib.redirect_stdout(logs), \
             patch("subtitle_app.pipeline.runner.AudioExtractor.extract", autospec=True, side_effect=extract), \
             patch("subtitle_app.pipeline.runner.AudioTranscriber.transcribe", autospec=True, side_effect=transcribe), \
             patch("subtitle_app.pipeline.runner.SubtitleTranslator.translate", autospec=True, side_effect=translate), \
             patch("subtitle_app.pipeline.runner.VideoSubtitler.render", autospec=True, side_effect=render):
            first = self.run_pipeline()
            second = self.run_pipeline()
            self.run_pipeline(parallel_render=True)
        self.assertEqual(render_modes, [False, False, True])
        self.assertNotEqual(first, second)
        self.assertEqual(first.name, "강의_en.mp4")
        self.assertEqual(first.read_bytes(), b"rendered")
        self.assertEqual(self.video.read_bytes(), b"video")

    def test_failure_stops_downstream_stages(self):
        with patch("subtitle_app.pipeline.runner.AudioExtractor.extract", side_effect=RuntimeError("추출 실패")), \
             patch("subtitle_app.pipeline.runner.AudioTranscriber.transcribe") as transcribe, \
             patch("subtitle_app.pipeline.runner.SubtitleTranslator.translate") as translate, \
             patch("subtitle_app.pipeline.runner.VideoSubtitler.render") as render:
            with self.assertRaisesRegex(RuntimeError, "추출 실패"):
                self.run_pipeline()
            transcribe.assert_not_called()
            translate.assert_not_called()
            render.assert_not_called()

    def test_empty_transcription_skips_translation_and_render(self):
        empty = self.root / "empty.txt"
        empty.write_text("", encoding="utf-8")
        with patch("subtitle_app.pipeline.runner.AudioExtractor.extract", return_value=MediaFile(self.video)), \
             patch("subtitle_app.pipeline.runner.AudioTranscriber.transcribe", return_value=MediaFile(empty)), \
             patch("subtitle_app.pipeline.runner.SubtitleTranslator.translate") as translate, \
             patch("subtitle_app.pipeline.runner.VideoSubtitler.render") as render:
            self.assertEqual(self.run_pipeline(), self.video)
        translate.assert_not_called()
        render.assert_not_called()

    def test_local_backend_routes_without_openai_transcription(self):
        empty = self.root / "empty.txt"
        empty.write_text("", encoding="utf-8")
        with patch("subtitle_app.pipeline.runner.AudioExtractor.extract", return_value=MediaFile(self.video)), \
             patch("subtitle_app.pipeline.runner.AudioTranscriber") as api, \
             patch("subtitle_app.pipeline.runner.LocalTranscriber") as local:
            local.return_value.transcribe.return_value = MediaFile(empty)
            self.run_pipeline(transcription_backend="local", local_model="medium", local_device="cpu")
        api.assert_not_called()
        self.assertEqual(local.call_args.kwargs["model"], "medium")
        self.assertEqual(local.call_args.kwargs["device"], "cpu")

    def test_missing_input_or_config_stops_before_extraction(self):
        with patch("subtitle_app.pipeline.runner.AudioExtractor.extract") as extract:
            self.key.unlink()
            with self.assertRaises(ValueError):
                self.run_pipeline()
            self.video.unlink()
            with self.assertRaises(FileNotFoundError):
                self.run_pipeline()
            extract.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_local_and_codex_pipeline_needs_no_api_key(self):
        self.key.unlink()
        transcript = self.root / "speech_kr.txt"
        transcript.write_text("[00:00:00.000, 00:00:01.000] 전압\n", encoding="utf-8")
        translated = self.root / "speech_en.txt"
        translated.write_text("[00:00:00.000, 00:00:01.000] Voltage\n", encoding="utf-8")
        with patch("subtitle_app.pipeline.runner.check_codex_login") as login, \
             patch("subtitle_app.pipeline.runner.load_api_key") as key, \
             patch("subtitle_app.pipeline.runner.AudioExtractor.extract", return_value=MediaFile(self.video)), \
             patch("subtitle_app.pipeline.runner.LocalTranscriber.transcribe", return_value=MediaFile(transcript)), \
             patch("subtitle_app.pipeline.runner.CodexSubtitleTranslator") as codex, \
             patch("subtitle_app.pipeline.runner.SubtitleTranslator") as api, \
             patch("subtitle_app.pipeline.runner.VideoSubtitler.render", return_value=self.root / "final.mp4"):
            codex.return_value.translate.return_value = translated
            self.run_pipeline(transcription_backend="local", translation_backend="codex", codex_model="chosen-model")
        login.assert_called_once()
        key.assert_not_called()
        api.assert_not_called()
        self.assertEqual(codex.call_args.kwargs["model"], "chosen-model")

    def test_codex_login_failure_stops_before_extraction(self):
        with patch("subtitle_app.pipeline.runner.check_codex_login", side_effect=RuntimeError("login required")), \
             patch("subtitle_app.pipeline.runner.AudioExtractor.extract") as extract, self.assertRaisesRegex(RuntimeError, "login"):
            self.run_pipeline(transcription_backend="local", translation_backend="codex")
        extract.assert_not_called()

    def test_cli_defaults_to_pipeline_and_reports_failure(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", str(self.video), "--textbook-file", str(self.book)]), \
             patch("subtitle_app.pipeline.runner.run_pipeline", return_value=self.root / "final.mp4") as run:
            self.assertEqual(cli.main(), 0)
            self.assertEqual(run.call_args.args[0], self.video)
            self.assertFalse(run.call_args.kwargs["parallel_render"])
        with patch("sys.argv", ["__main__.py", str(self.video), "--parallel-render",
                                "--textbook-file", str(self.book)]), \
             patch("subtitle_app.pipeline.runner.run_pipeline", return_value=self.root / "final.mp4") as run:
            self.assertEqual(cli.main(), 0)
            self.assertTrue(run.call_args.kwargs["parallel_render"])
        with patch("sys.argv", ["__main__.py", str(self.video), "--pipeline", "--textbook-file", str(self.book)]), \
             patch("subtitle_app.pipeline.runner.run_pipeline", side_effect=RuntimeError("번역 실패")), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(cli.main(), 1)
        self.assertIn("번역 실패", error.getvalue())

    def test_multicourse_requires_selection_before_extraction(self):
        with self.book.open("a", encoding="utf-8") as output:
            output.write("[Course]\nAI/ML\n[Terminology]\n텐서 = tensor\n")
        with patch("subtitle_app.pipeline.runner.AudioExtractor.extract") as extract:
            with self.assertRaisesRegex(ValueError, "--course"):
                self.run_pipeline()
            extract.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_cli_lists_courses_without_input_or_api_key(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", "--list-courses", "--textbook-file", str(self.book),
                                "--api-key-file", str(self.root / "missing-key")]), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 0)
        self.assertIn("1. 회로", output.getvalue())


if __name__ == "__main__":
    unittest.main()
