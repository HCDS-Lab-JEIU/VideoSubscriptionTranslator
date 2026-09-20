"""외부 요청 없이 전체 단계 연결과 실패 시 중단을 검증합니다."""

import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_file import MediaFile
from pipeline import run_pipeline


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

    def run_pipeline(self):
        return run_pipeline(self.video, self.root / "runs", self.key, self.book)

    def test_stage_handoff_srt_and_unique_runs(self):
        def extract(extractor, video):
            self.assertEqual(video.file_path, self.video)
            path = extractor.output_dir / f"{video.file_path.stem}.mp3"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"audio")
            return MediaFile(path)

        def transcribe(transcriber, audio):
            self.assertEqual(audio.file_path.read_bytes(), b"audio")
            path = transcriber.output_dir / f"{audio.file_path.stem}.txt"
            path.parent.mkdir(parents=True)
            path.write_text("[00:00:00.000, 00:00:01.000] 전압\n", encoding="utf-8")
            return MediaFile(path)

        def translate(translator, source):
            self.assertIn("전압", source.read_text(encoding="utf-8"))
            path = translator._output_path(source)
            path.write_text("[00:00:00.000, 00:00:01.000] Voltage\n", encoding="utf-8")
            return path

        def render(renderer, video, srt, output):
            self.assertEqual(video, self.video)
            self.assertEqual(srt.read_text(encoding="utf-8"),
                             "1\n00:00:00,000 --> 00:00:01,000\nVoltage\n\n")
            output.write_bytes(b"rendered")
            return output

        with patch("pipeline.AudioExtractor.extract", autospec=True, side_effect=extract), \
             patch("pipeline.AudioTranscriber.transcribe", autospec=True, side_effect=transcribe), \
             patch("pipeline.SubtitleTranslator.translate", autospec=True, side_effect=translate), \
             patch("pipeline.VideoSubtitler.render", autospec=True, side_effect=render):
            first = self.run_pipeline()
            second = self.run_pipeline()
        self.assertNotEqual(first, second)
        self.assertEqual(first.name, "강의_en.mp4")
        self.assertEqual(first.read_bytes(), b"rendered")
        self.assertEqual(self.video.read_bytes(), b"video")

    def test_failure_stops_downstream_stages(self):
        with patch("pipeline.AudioExtractor.extract", side_effect=RuntimeError("추출 실패")), \
             patch("pipeline.AudioTranscriber.transcribe") as transcribe, \
             patch("pipeline.SubtitleTranslator.translate") as translate, \
             patch("pipeline.VideoSubtitler.render") as render:
            with self.assertRaisesRegex(RuntimeError, "추출 실패"):
                self.run_pipeline()
            transcribe.assert_not_called()
            translate.assert_not_called()
            render.assert_not_called()

    def test_missing_input_or_config_stops_before_extraction(self):
        with patch("pipeline.AudioExtractor.extract") as extract:
            self.key.unlink()
            with self.assertRaises(ValueError):
                self.run_pipeline()
            self.video.unlink()
            with self.assertRaises(FileNotFoundError):
                self.run_pipeline()
            extract.assert_not_called()
        self.assertFalse((self.root / "runs").exists())

    def test_cli_defaults_to_pipeline_and_reports_failure(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", str(self.video)]), \
             patch("pipeline.run_pipeline", return_value=self.root / "final.mp4") as run:
            self.assertEqual(cli.main(), 0)
            self.assertEqual(run.call_args.args[0], self.video)
        with patch("sys.argv", ["__main__.py", str(self.video), "--pipeline"]), \
             patch("pipeline.run_pipeline", side_effect=RuntimeError("번역 실패")), \
             contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(cli.main(), 1)
        self.assertIn("번역 실패", error.getvalue())


if __name__ == "__main__":
    unittest.main()
