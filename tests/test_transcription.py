"""실제 API 호출 없이 SDK 요청과 파일 결과를 검증합니다."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from openai import OpenAI

from api_config import load_api_key
from audio_transcriber import AudioTranscriber, AudioTranscriptionError
from media_file import MediaFile
from textbook import Textbook


class TranscriptionTests(unittest.TestCase):
    def setUp(self):
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
            for item in (b'whisper-1', b'verbose_json', b'timestamp_granularities[]', b'segment', b'ko'):
                self.assertIn(item, body)
            self.assertIn(b'name="prompt"', body)
            self.assertIn("반도체 회로 강의. 전압, 직렬저항회로.".encode("utf-8"), body)
            self.assertNotIn(b'Output only the English translation.', body)
            self.assertNotIn(b'voltage', body)
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
        with self.client_patch(handler):
            transcript = self.transcriber.transcribe(audio)
        self.assertEqual(transcript.file_path.read_text(encoding="utf-8"),
                         "[00:00:00.120, 00:00:01.234] 안녕하세요. 다음 구간입니다.\n"
                         "[00:01:00.000, 00:01:01.500] 분 경계\n")
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

    def test_textbook_edits_are_loaded_on_each_read(self):
        textbook = Textbook.load(self.textbook)
        self.assertEqual(textbook.terminology["전압"], "voltage")
        self.assertIn("English translation", textbook.translation_instructions)
        self.textbook.write_text("[Course]\n전자 회로\n[Terminology]\n전류 = current\n", encoding="utf-8")
        self.assertEqual(Textbook.load(self.textbook).transcription_prompt(), "전자 회로 강의. 전류.")

    def test_invalid_textbook_stops_before_api_call(self):
        for content in ("", "[Course]\n회로\n[Terminology]\n전압 voltage",
                        "[Unknown]\nvalue", "[Course]\n회로\n[Terminology]\n전압 = voltage\n전압 = V"):
            self.textbook.write_text(content, encoding="utf-8")
            with patch("audio_transcriber.OpenAI") as client:
                with self.assertRaises(ValueError):
                    self.transcriber.transcribe(MediaFile(self.mp3))
                client.assert_not_called()

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
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
