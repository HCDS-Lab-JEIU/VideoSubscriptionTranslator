"""실제 API 호출 없이 SDK 요청과 파일 결과를 검증합니다."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    import httpx2 as httpx
except ImportError:
    import httpx
from openai import OpenAI

from api_config import load_api_key
from audio_transcriber import AudioTranscriber, AudioTranscriptionError
from audio_activity import AudioActivity
from media_file import MediaFile
from textbook import Textbook


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        activity = patch("audio_transcriber.AudioActivity.analyze", return_value=AudioActivity(5, []))
        activity.start()
        self.addCleanup(activity.stop)
        extract = patch("transcription_recovery.extract_clip",
                        side_effect=lambda source, target, start, end: target.write_bytes(b"mock-clip"))
        extract.start()
        self.addCleanup(extract.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="transcription-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.key = self.folder / "key.txt"
        self.key.write_text("\ufefftest-key-not-a-real-secret\n", encoding="utf-8")
        self.mp3 = self.folder / "한국어 강의.mp3"
        self.mp3.write_bytes(b"mock-audio")
        self.output = self.folder / "output"
        self.textbook = self.folder / "textbook.txt"
        self.textbook.write_text(
            "\ufeff# 강의 단어장\n[Course]\n반도체 회로\n[Terminology]\n"
            "전압 = voltage\n직렬저항회로 = series resistor circuit\n"
            "[Translation instructions]\nOutput only the English translation.\n",
            encoding="utf-8",
        )
        self.transcriber = AudioTranscriber(self.key, self.output, self.textbook)

    def client_patch(self, handler):
        def factory(**kwargs):
            kwargs["http_client"] = httpx.Client(transport=httpx.MockTransport(handler))
            return OpenAI(**kwargs)
        return patch("audio_transcriber.OpenAI", side_effect=factory)

    def test_request_and_timestamped_utf8_output(self):
        def handler(request):
            self.assertEqual(str(request.url), "https://api.openai.com/v1/audio/transcriptions")
            body = request.read()
            for item in (b'gpt-transcribe', b'languages', b'ko'):
                self.assertIn(item, body)
            self.assertNotIn(b'timestamp_granularities', body)
            self.assertNotIn(b'verbose_json', body)
            self.assertIn(b'name="prompt"', body)
            self.assertIn("과목: 반도체 회로".encode("utf-8"), body)
            self.assertNotIn(b'Output only the English translation.', body)
            self.assertIn(b'voltage', body)
            return httpx.Response(200, json={
                "text": "안녕하세요. 다음 구간입니다.", "language": "korean", "duration": 62.0,
                "segments": [
                    {"id": 0, "seek": 0, "start": 0.12, "end": 1.234,
                     "text": " 안녕하세요.\n다음 구간입니다. ", "tokens": [], "temperature": 0,
                     "avg_logprob": 0, "compression_ratio": 1, "no_speech_prob": 0},
                    {"id": 1, "seek": 0, "start": 59.9998, "end": 61.5,
                     "text": "분 경계", "tokens": [], "temperature": 0,
                     "avg_logprob": 0, "compression_ratio": 1, "no_speech_prob": 0},
                ],
            })
        audio = MediaFile(self.mp3)
        with self.client_patch(handler), \
             patch("audio_transcriber.AudioActivity.analyze", return_value=AudioActivity(62, [(0, 0.12), (1.234, 59.9998), (61.5, 62)])):
            transcript = self.transcriber.transcribe(audio)
        self.assertEqual(transcript.file_path.read_text(encoding="utf-8"),
                         "[00:00:00.120, 00:00:01.234] 안녕하세요. 다음 구간입니다.\n"
                         "[00:01:00.000, 00:01:01.500] 안녕하세요. 다음 구간입니다.\n")
        self.assertEqual(len(audio.subscript_lines), 2)
        raw = transcript.file_path.with_suffix(".json").read_text(encoding="utf-8")
        self.assertEqual(json.loads(raw)["language"], "korean")
        self.assertNotIn("test-key-not-a-real-secret", raw)
        with patch("audio_transcriber.OpenAI") as client:
            with self.assertRaises(FileExistsError):
                self.transcriber.transcribe(audio)
            client.assert_not_called()

    def test_key_bom_empty_and_missing(self):
        self.assertEqual(load_api_key(self.key), "test-key-not-a-real-secret")
        for value in ('api_key = "test-key-not-a-real-secret"',
                      'key = "test-key-not-a-real-secret"',
                      "OPENAI_API_KEY='test-key-not-a-real-secret'"):
            self.key.write_text(value, encoding="utf-8")
            self.assertEqual(load_api_key(self.key), "test-key-not-a-real-secret")
        self.key.write_text(" \n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_api_key(self.key)
        with self.assertRaises(ValueError):
            load_api_key(self.folder / "missing.txt")

    def test_full_silence_never_opens_api_client(self):
        with patch("audio_transcriber.AudioActivity.analyze", return_value=AudioActivity(30, [(0, 30)])), \
             patch("audio_transcriber.OpenAI") as client:
            result = self.transcriber.transcribe(MediaFile(self.mp3))
        client.assert_not_called()
        self.assertEqual(result.file_path.read_text(encoding="utf-8"), "")
        report = json.loads(result.file_path.with_suffix(".recovery.json").read_text(encoding="utf-8"))
        self.assertEqual(report["events"][0]["reason"], "silence")

    def test_later_speech_written_after_early_failure_and_exhausted_budget(self):
        from transcription_recovery import TranscriptionRecovery
        calls = []
        def handler(request):
            body = request.read()
            calls.append(body)
            text = "" if b"0000000000-" in body else "후반부 정상 문장입니다."
            return httpx.Response(200, json={"text": text})
        def factory(*args, **kwargs):
            return TranscriptionRecovery(*args, **kwargs, max_requests=0)
        with self.client_patch(handler), \
             patch("audio_transcriber.AudioActivity.analyze", return_value=AudioActivity(130, [(10, 60), (70, 120)])), \
             patch("audio_transcriber.TranscriptionRecovery", side_effect=factory):
            result = self.transcriber.transcribe(MediaFile(self.mp3))
        text = result.file_path.read_text(encoding="utf-8")
        self.assertIn("[00:01:00.000, 00:01:10.000]", text)
        self.assertIn("[00:02:00.000, 00:02:10.000]", text)
        self.assertEqual(len(calls), 3)
        merged = json.loads(result.file_path.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertTrue(merged["processing_complete"])
        self.assertFalse(merged["complete"])
        self.assertGreater(merged["needs_review"], 0)
        self.assertEqual(merged["processed_until"], 130)

    def test_initial_prompt_echo_recovers_without_sending_instructions_again(self):
        calls = []
        phrase = "전문용어의 정확한 표기"
        with self.textbook.open("a", encoding="utf-8") as output:
            output.write("[Whisper Rules]\n" + phrase)
        def handler(request):
            body = request.read().decode("utf-8")
            calls.append(body)
            text = phrase if len(calls) == 1 else "전압을 측정합니다."
            return httpx.Response(200, json={"duration": 5, "text": text, "language": "korean",
                "segments": [{"start": 0 if len(calls) == 1 else 1.5,
                              "end": 5 if len(calls) == 1 else 2.5, "text": text}]})
        def extract(source, target, start, end):
            target.write_bytes(b"mock-audio")
        with self.client_patch(handler), patch("transcription_recovery.extract_clip", side_effect=extract):
            result = self.transcriber.transcribe(MediaFile(self.mp3))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(phrase not in body for body in calls[1:]))
        self.assertNotIn(phrase, result.file_path.read_text(encoding="utf-8"))

    def test_repetition_preserves_raw_response_and_recovers_txt(self):
        repeated = "배틀링스의 width가 1.75보다 작은 날에 비교를 해서"
        segments = [
            {"id": i, "seek": 0, "start": 1789 + i * 3, "end": 1792 + i * 3,
             "text": repeated, "tokens": [], "temperature": 0,
             "avg_logprob": -0.1, "compression_ratio": 7.52, "no_speech_prob": 0.1}
            for i in range(14)
        ]
        segments.insert(0, {"start": 0, "end": 1789, "text": "정상 앞 문장"})
        segments.append({"start": 1831, "end": 1900, "text": "정상 뒤 문장"})
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={
                "text": "petal width를 비교합니다.", "language": "korean", "duration": 33,
                "segments": [{"start": 1.5, "end": 31.5 if len(calls) == 1 else 13.5,
                              "text": "petal width를 비교합니다."}],
            })
        saved = self.folder / "original.json"
        saved.write_text(json.dumps({"duration": 1900, "segments": segments}), encoding="utf-8")
        audio = MediaFile(self.mp3)
        def extract(source, target, start, end):
            target.write_bytes(b"mock-clip")
        with self.client_patch(handler), patch("transcription_recovery.extract_clip", side_effect=extract), \
             patch("audio_transcriber.AudioActivity.analyze", return_value=AudioActivity(1900, [])):
            self.transcriber.transcribe(audio, response_file=saved)
        raw = self.output / f"{self.mp3.stem}.json"
        preserved = json.loads(raw.read_text(encoding="utf-8"))["segments"]
        self.assertEqual([s["text"] for s in preserved], [s["text"] for s in segments])
        text = raw.with_suffix(".txt").read_text(encoding="utf-8")
        self.assertIn("00:29:49.000", text)
        self.assertIn("petal width", text)
        self.assertNotIn(repeated, text)
        self.assertEqual(len(calls), 2)
        self.assertTrue(raw.with_suffix(".recovery.json").exists())

    def test_repetition_ignores_short_or_separated_speech(self):
        for text, count, step in [("네", 10, 3), ("충분히 긴 문장을 다시 설명합니다", 3, 3),
                                  ("충분히 긴 문장을 다시 설명합니다", 10, 30)]:
            with self.subTest(text=text, count=count, step=step):
                AudioTranscriber._check_repetition([
                    SimpleNamespace(text=text, start=i * step, end=i * step + 3)
                    for i in range(count)
                ])

    def test_repetition_normalizes_spacing_and_punctuation(self):
        with self.assertRaises(AudioTranscriptionError):
            AudioTranscriber._check_repetition([
                SimpleNamespace(text=("충분히 긴 문장을 다시 설명합니다." if i % 2 else
                                      "충분히  긴 문장을 다시 설명합니다!"),
                                start=i * 3, end=i * 3 + 3)
                for i in range(5)
            ])

    def test_textbook_edits_are_loaded_on_each_read(self):
        textbook = Textbook.load(self.textbook)
        self.assertEqual(textbook.terminology["전압"], "voltage")
        self.assertIn("English translation", textbook.translation_instructions)
        self.textbook.write_text("[Course]\n전자 회로\n[Terminology]\n전류 = current\n", encoding="utf-8")
        self.assertEqual(Textbook.load(self.textbook).transcription_prompt(), "전자 회로 강의. 전류.")

    def test_saved_response_reused_without_full_audio_request(self):
        saved = self.folder / "saved.json"
        content = {"duration": 5, "segments": [{"start": 0, "end": 5, "text": "정상 전사"}]}
        saved.write_text(json.dumps(content), encoding="utf-8")
        with self.client_patch(lambda request: self.fail("No API needed")):
            result = self.transcriber.transcribe(MediaFile(self.mp3), response_file=saved)
        self.assertIn("정상 전사", result.file_path.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(saved.read_text(encoding="utf-8")), content)

    def test_transient_server_error_is_retried(self):
        attempts = []
        def handler(request):
            attempts.append(request)
            if len(attempts) == 1:
                return httpx.Response(500, json={"error": {"message": "temporary"}})
            return httpx.Response(200, json={"duration": 5, "text": "복구 성공",
                "language": "korean", "segments": [{"start": 1.5, "end": 2.5, "text": "복구 성공"}]})
        with self.client_patch(handler):
            self.transcriber.transcribe(MediaFile(self.mp3))
        self.assertEqual(len(attempts), 2)

    def test_invalid_textbook_stops_before_api_call(self):
        for content in ("", "[Course]\n회로\n[Terminology]\n전압 voltage",
                        "[Unknown]\nvalue", "[Course]\n회로\n[Terminology]\n전압 = voltage\n전압 = V"):
            self.textbook.write_text(content, encoding="utf-8")
            with patch("audio_transcriber.OpenAI") as client:
                with self.assertRaises(ValueError):
                    self.transcriber.transcribe(MediaFile(self.mp3))
                client.assert_not_called()

    def test_selected_course_is_the_only_course_sent_to_transcription(self):
        with self.textbook.open("a", encoding="utf-8") as output:
            output.write("[Course]\nAI/ML Applications\n[Terminology]\n텐서 = tensor\n")
        with patch("audio_transcriber.OpenAI") as client:
            with self.assertRaisesRegex(ValueError, "--course"):
                self.transcriber.transcribe(MediaFile(self.mp3))
            client.assert_not_called()
        def handler(request):
            body = request.read().decode("utf-8")
            self.assertIn("AI/ML Applications", body)
            self.assertIn("텐서", body)
            self.assertNotIn("반도체 회로", body)
            self.assertNotIn("전압", body)
            return httpx.Response(200, json={"duration": 5, "text": "텐서입니다",
                "language": "korean", "segments": [{"start": 0, "end": 5, "text": "텐서입니다"}]})
        self.transcriber.course = "AI/ML"
        with self.client_patch(handler):
            self.transcriber.transcribe(MediaFile(self.mp3))

    def test_selected_course_is_the_only_course_sent_to_translation(self):
        from subtitle_translator import SubtitleTranslator
        with self.textbook.open("a", encoding="utf-8") as output:
            output.write("[Course]\nAI/ML Applications\n[Terminology]\n텐서 = tensor\n")
        source = self.folder / "lecture_kr.txt"
        source.write_text("[00:00:00.000, 00:00:01.000] 텐서입니다\n", encoding="utf-8")
        translator = SubtitleTranslator(self.key, self.textbook, course="AI/ML")
        def request(client, instructions, lines, indices):
            self.assertIn("AI/ML Applications", instructions)
            self.assertIn("텐서 = tensor", instructions)
            self.assertNotIn("반도체 회로", instructions)
            self.assertNotIn("voltage", instructions)
            return {str(i): "This is a tensor." for i in indices}
        with patch("subtitle_translator.OpenAI"), \
             patch.object(translator, "_request_translations", side_effect=request):
            result = translator.translate(source)
        self.assertIn("This is a tensor.", result.read_text(encoding="utf-8"))

    def test_oversized_input_stops_before_api_call(self):
        with self.mp3.open("wb") as output:
            output.truncate(AudioTranscriber.MAX_FILE_BYTES)
        with patch("audio_transcriber.OpenAI") as client:
            with self.assertRaises(ValueError):
                self.transcriber.transcribe(MediaFile(self.mp3))
            client.assert_not_called()

    def test_api_failure_hides_response_body_and_creates_no_results(self):
        def handler(request):
            return httpx.Response(401, json={"error": {"message": "test-key-not-a-real-secret"}})
        with self.client_patch(handler):
            with self.assertRaises(AudioTranscriptionError) as caught:
                self.transcriber.transcribe(MediaFile(self.mp3))
        self.assertIn("401", str(caught.exception))
        self.assertNotIn("test-key-not-a-real-secret", str(caught.exception))
        self.assertFalse(list(self.output.glob("*.txt")))
        self.assertFalse(list(self.output.rglob("*.json")))

    def test_short_audio_400_does_not_stop_later_utterances(self):
        calls = []
        def handler(request):
            calls.append(request)
            if len(calls) <= 2:
                return httpx.Response(400, json={"error": {
                    "code": "audio_too_short",
                    "message": "Audio is too short. test-key-not-a-real-secret",
                }})
            return httpx.Response(200, json={"text": "후반부 실제 발화입니다."})
        with self.client_patch(handler), patch("audio_transcriber.AudioActivity.analyze",
                return_value=AudioActivity(10, [(0.062, 5)])):
            result = self.transcriber.transcribe(MediaFile(self.mp3))
        self.assertEqual(len(calls), 3)
        self.assertIn("후반부 실제 발화입니다.", result.file_path.read_text(encoding="utf-8"))
        records = list(self.output.rglob("*.json"))
        self.assertTrue(any("audio_too_short" in p.read_text(encoding="utf-8") for p in records))
        self.assertTrue(all("test-key-not-a-real-secret" not in p.read_text(encoding="utf-8") for p in records))

    def test_unrelated_bad_request_still_stops_without_retry(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(400, json={"error": {"message": "Invalid prompt"}})
        with self.client_patch(handler), self.assertRaisesRegex(AudioTranscriptionError, "400"):
            self.transcriber.transcribe(MediaFile(self.mp3))
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
