"""Local routing, resource limits and retries without model downloads or API calls."""

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from local_transcriber import LocalTranscriber, gpu_free_memory_mib
from media_file import MediaFile


class LocalTranscriberTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.book = self.root / "book.txt"
        self.book.write_text("[Course]\n회로\n[Terminology]\n전압 = voltage\n", encoding="utf-8")
        self.audio = self.root / "lecture.mp3"
        self.audio.write_bytes(b"audio")
        self.output = self.root / "out"
        self.transcriber = LocalTranscriber(self.output, self.book)
        self.model = Mock()
        self.model.transcribe.return_value = (
            iter([SimpleNamespace(start=1.25, end=3.5, text=" 전압입니다. ")]),
            SimpleNamespace(duration=5),
        )
        self.factory = Mock(return_value=self.model)
        self.addCleanup(patch.stopall)
        patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=self.factory)}).start()
        patch("local_transcriber.gpu_free_memory_mib", return_value=5000).start()
        self.api = patch("audio_transcriber.OpenAI", side_effect=AssertionError("No API allowed")).start()

    def test_gpu_quantization_timestamps_and_cleanup(self):
        audio = MediaFile(self.audio)
        transcript = self.transcriber.transcribe(audio)
        self.assertEqual(transcript.file_path.read_text(encoding="utf-8"),
                         "[00:00:01.250, 00:00:03.500] 전압입니다.\n")
        options = self.factory.call_args.kwargs
        self.assertEqual(options["compute_type"], "int8_float16")
        self.assertEqual(options["num_workers"], 1)
        self.assertEqual(options["device_index"], 0)
        decode = self.model.transcribe.call_args.kwargs
        self.assertEqual(decode["beam_size"], 1)
        self.assertFalse(decode["condition_on_previous_text"])
        self.assertTrue(decode["vad_filter"])
        self.assertIn("전압", decode["initial_prompt"])
        self.assertEqual(decode["language"], "ko")
        self.model.model.unload_model.assert_called_once()
        self.assertEqual(len(audio.subscript_lines), 1)
        raw = json.loads((self.output / "lecture.json").read_text(encoding="utf-8"))
        self.assertTrue(raw["complete"])
        self.assertEqual(raw["model"], "large-v2")
        self.api.assert_not_called()

    def test_low_or_unknown_gpu_memory_uses_cpu(self):
        for free in (3000, None):
            with self.subTest(free=free), patch("local_transcriber.gpu_free_memory_mib", return_value=free):
                self.assertEqual(self.transcriber._select_device(), "cpu")

    def test_explicit_cpu_never_queries_gpu(self):
        with patch("local_transcriber.gpu_free_memory_mib") as query:
            LocalTranscriber(self.output, self.book, device="cpu").transcribe(MediaFile(self.audio))
        query.assert_not_called()
        self.assertEqual(self.factory.call_args.kwargs["compute_type"], "int8")

    def test_load_oom_retries_once_on_cpu(self):
        self.factory.side_effect = [RuntimeError("CUDA out of memory"), self.model]
        self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual([c.kwargs["device"] for c in self.factory.call_args_list], ["cuda", "cpu"])

    def test_lazy_generator_oom_discards_partial_results_before_cpu_retry(self):
        def failing_stream():
            yield SimpleNamespace(start=0, end=1, text="partial GPU")
            raise RuntimeError("CUDA out of memory")
        gpu_model = Mock()
        gpu_model.transcribe.return_value = (failing_stream(), SimpleNamespace(duration=5))
        self.factory.side_effect = [gpu_model, self.model]
        transcript = self.transcriber.transcribe(MediaFile(self.audio))
        self.assertNotIn("partial", transcript.file_path.read_text(encoding="utf-8"))
        raw = json.loads((self.output / "lecture.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["device"], "cpu")
        self.assertEqual(len(raw["segments"]), 1)
        gpu_model.model.unload_model.assert_called_once()

    def test_missing_cuda_dll_retries_locally(self):
        self.factory.side_effect = [RuntimeError("Library cublas64_12.dll is not found"), self.model]
        self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual(self.factory.call_args.kwargs["device"], "cpu")

    def test_unrelated_error_does_not_retry_or_write_completed_transcript(self):
        self.model.transcribe.side_effect = RuntimeError("corrupt audio")
        with self.assertRaisesRegex(RuntimeError, "corrupt audio"):
            self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual(self.factory.call_count, 1)
        self.assertFalse((self.output / "lecture.txt").exists())
        self.assertFalse(json.loads((self.output / "lecture.json").read_text())["complete"])
        self.model.model.unload_model.assert_called_once()

    def test_cpu_failure_is_not_retried(self):
        self.factory.side_effect = RuntimeError("CUDA out of memory")
        with self.assertRaises(RuntimeError):
            self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual(self.factory.call_count, 2)

    def test_empty_speech_writes_empty_transcript(self):
        self.model.transcribe.return_value = (iter([]), SimpleNamespace(duration=5))
        transcript = self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual(transcript.file_path.read_text(), "")

    def test_invalid_timestamp_fails_and_releases_model(self):
        self.model.transcribe.return_value = (
            iter([SimpleNamespace(start=float("nan"), end=2, text="bad")]), SimpleNamespace(duration=5))
        with self.assertRaises(ValueError):
            self.transcriber.transcribe(MediaFile(self.audio))
        self.model.model.unload_model.assert_called_once()
        self.assertFalse((self.output / "lecture.txt").exists())

    def test_existing_results_are_not_overwritten(self):
        self.output.mkdir()
        saved = self.output / "lecture.json"
        saved.write_text("original")
        with self.assertRaises(FileExistsError):
            self.transcriber.transcribe(MediaFile(self.audio))
        self.assertEqual(saved.read_text(), "original")
        self.factory.assert_not_called()

    def test_segment_cannot_extend_past_audio_duration(self):
        self.model.transcribe.return_value = (
            iter([SimpleNamespace(start=4, end=5.8, text="tail"),
                  SimpleNamespace(start=6, end=7, text="outside")]), SimpleNamespace(duration=5))
        self.transcriber.transcribe(MediaFile(self.audio))
        raw = json.loads((self.output / "lecture.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["segments"], [{"start": 4, "end": 5, "text": "tail"}])

    def test_missing_optional_dependency_has_install_instructions(self):
        with patch.dict(sys.modules, {"faster_whisper": None}), self.assertRaisesRegex(RuntimeError, "requirements-local"):
            self.transcriber.transcribe(MediaFile(self.audio))

    def test_gpu_probe_fails_closed(self):
        with patch("local_transcriber.subprocess.run", side_effect=FileNotFoundError):
            self.assertIsNone(gpu_free_memory_mib())
        with patch("local_transcriber.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="4200\n")):
            self.assertEqual(gpu_free_memory_mib(), 4200)

    def test_cli_local_transcription_requires_no_api_key(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", str(self.audio), "--transcribe", "--transcription-backend", "local",
                                "--textbook-file", str(self.book), "--transcript-output-dir", str(self.output),
                                "--api-key-file", str(self.root / "missing-key")]):
            self.assertEqual(cli.main(), 0)
        self.api.assert_not_called()

    def test_local_response_recovery_rejected_before_any_model_call(self):
        spec = importlib.util.spec_from_file_location("video_cli", Path(__file__).resolve().parents[1] / "__main__.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch("sys.argv", ["__main__.py", str(self.audio), "--transcribe", "--transcription-backend", "local",
                                "--transcription-response", "old.json"]), self.assertRaises(SystemExit):
            cli.main()
        self.factory.assert_not_called()
