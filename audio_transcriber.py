"""Whisper의 한국어 구간 전사와 원본 응답 보관."""

import math
from pathlib import Path

from openai import APIConnectionError, APIError, APIStatusError, OpenAI

from api_config import load_api_key
from console_status import waiting_for_response
from media_file import MediaFile, SubscriptFile
from subtitle import SubscriptLine, TimeStamp
from transcript_writer import TranscriptWriter
from textbook import DEFAULT_TEXTBOOK_PATH, Textbook


class AudioTranscriptionError(RuntimeError):
    """전사 요청 또는 응답 처리 실패. 키와 서버 응답 본문은 출력하지 않습니다."""


class AudioTranscriber:
    MODEL = "whisper-1"
    MAX_FILE_BYTES = 25_000_000

    def __init__(self, api_key_path: str | Path, output_dir: str | Path,
                 textbook_path: str | Path = DEFAULT_TEXTBOOK_PATH):
        self.api_key_path = Path(api_key_path)
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.textbook_path = Path(textbook_path)

    @staticmethod
    def _timestamp(seconds: float) -> TimeStamp:
        if not math.isfinite(seconds) or seconds < 0:
            raise AudioTranscriptionError("응답에 유효하지 않은 타임스탬프가 있습니다.")
        return TimeStamp.from_milliseconds(round(seconds * 1000))

    def transcribe(self, audio: MediaFile) -> SubscriptFile:
        path = audio.file_path
        if not path.is_file():
            raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
        if path.suffix.lower() != ".mp3":
            raise ValueError("전사 입력은 MP3 파일이어야 합니다.")
        if not 0 < path.stat().st_size < self.MAX_FILE_BYTES:
            raise ValueError("전사 입력은 0바이트 초과, 25MB 미만이어야 합니다. 큰 파일은 먼저 나눠주세요.")

        transcript = SubscriptFile(self.output_dir / f"{path.stem}.txt")
        response_path = transcript.file_path.with_suffix(".json")
        for destination in (transcript.file_path, response_path):
            if destination.exists():
                raise FileExistsError(f"전사 결과가 이미 존재합니다: {destination}")

        prompt = Textbook.load(self.textbook_path).transcription_prompt()
        api_key = load_api_key(self.api_key_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 명시적 주소로 키를 공식 API에만 전달하고 자동 재시도에 따른 중복 요청을 막습니다.
            with OpenAI(
                api_key=api_key, base_url="https://api.openai.com/v1",
                timeout=600.0, max_retries=0,
            ) as client, path.open("rb") as source, waiting_for_response():
                response = client.audio.transcriptions.create(
                    model=self.MODEL,
                    file=(path.name, source, "audio/mpeg"),
                    language="ko",
                    prompt=prompt,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    temperature=0,
                )
        except APIConnectionError:
            raise AudioTranscriptionError(
                "OpenAI API 연결 또는 응답 대기에 실패했습니다. 네트워크를 확인하세요."
            ) from None
        except APIStatusError as exc:
            messages = {
                401: "API 키 인증에 실패했습니다.",
                403: "API 접근 권한을 확인하세요.",
                429: "API 사용 한도 또는 요청 한도를 확인하세요.",
            }
            message = messages.get(exc.status_code, "전사 요청을 처리하지 못했습니다.")
            raise AudioTranscriptionError(f"{message} (HTTP {exc.status_code})") from None
        except APIError:
            raise AudioTranscriptionError("OpenAI API 요청에 실패했습니다.") from None

        # 유료 요청의 응답을 먼저 보관하여 텍스트 재가공 시 재요청 없이 사용할 수 있습니다.
        with response_path.open("x", encoding="utf-8") as output:
            output.write(response.model_dump_json(indent=2))
        if response.segments is None:
            raise AudioTranscriptionError("응답에 구간 정보가 없습니다. 저장된 JSON을 확인하세요.")
        for segment in response.segments:
            start = self._timestamp(segment.start)
            end = self._timestamp(segment.end)
            if segment.end < segment.start:
                raise AudioTranscriptionError("응답에 종료 시간이 시작 시간보다 이른 구간이 있습니다.")
            text = segment.text.strip()
            if text:
                transcript.add_subscript_line(SubscriptLine(text, start, end))
        if not transcript.subscript_lines:
            raise AudioTranscriptionError("인식된 음성 구간이 없습니다. 저장된 JSON을 확인하세요.")
        TranscriptWriter().write(transcript)
        audio.subscript_lines = list(transcript.subscript_lines)
        return transcript
