"""무음 경계별 한국어 전사와 원본 응답 보관."""

import math
import json
from pathlib import Path

from openai import APIConnectionError, APIError, APIStatusError, OpenAI

from subtitle_app.common.api_config import load_api_key
from subtitle_app.media.audio_activity import AudioActivity
from subtitle_app.transcription.recovery_report import RecoveryReportWriter
from subtitle_app.common.console_status import waiting_for_response
from subtitle_app.media.media_file import MediaFile, SubscriptFile
from subtitle_app.subtitles.subtitle import SubscriptLine, TimeStamp
from subtitle_app.subtitles.transcript_writer import TranscriptWriter
from subtitle_app.textbook.document import DEFAULT_TEXTBOOK_PATH, Textbook
from subtitle_app.transcription.transcription_recovery import TranscriptionRecovery, suspect_ranges


class AudioTranscriptionError(RuntimeError):
    """전사 요청 또는 응답 처리 실패. 키와 서버 응답 본문은 출력하지 않습니다."""


class AudioTranscriber:
    MODEL = "gpt-transcribe"
    MAX_FILE_BYTES = 25_000_000
    CHUNK_SECONDS = 20

    def __init__(self, api_key_path: str | Path, output_dir: str | Path,
                 textbook_path: str | Path = DEFAULT_TEXTBOOK_PATH, *, course: str | None = None):
        self.api_key_path = Path(api_key_path)
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.textbook_path = Path(textbook_path)
        self.course = course

    @staticmethod
    def _timestamp(seconds: float) -> TimeStamp:
        if not math.isfinite(seconds) or seconds < 0:
            raise AudioTranscriptionError("응답에 유효하지 않은 타임스탬프가 있습니다.")
        return TimeStamp.from_milliseconds(round(seconds * 1000))

    @classmethod
    def _check_repetition(cls, segments) -> None:
        values = [vars(s) for s in segments]
        if suspect_ranges(values):
            raise AudioTranscriptionError("전사 응답에 긴 문장 반복이 감지되었습니다.")

    def transcribe(self, audio: MediaFile, *, response_file: Path | None = None) -> SubscriptFile:
        path = audio.file_path
        if not path.is_file():
            raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
        if path.suffix.lower() != ".mp3":
            raise ValueError("전사 입력은 MP3 파일이어야 합니다.")
        if not 0 < path.stat().st_size < self.MAX_FILE_BYTES:
            raise ValueError("전사 입력은 0바이트 초과, 25MB 미만이어야 합니다. 큰 파일은 먼저 나눠주세요.")

        transcript = SubscriptFile(self.output_dir / f"{path.stem}.txt")
        response_path = transcript.file_path.with_suffix(".json")
        report_path = response_path.with_suffix(".recovery.json")
        recovered_path = response_path.with_suffix(".recovered.json")
        recovery_folder = self.output_dir / f"{path.stem}_recovery"
        for destination in (transcript.file_path, response_path, report_path, recovered_path, recovery_folder):
            if destination.exists():
                raise FileExistsError(f"전사 결과가 이미 존재합니다: {destination}")

        book = Textbook.load(self.textbook_path).select_course(self.course)
        prompt = book.transcription_prompt() if response_file else book.accurate_transcription_prompt()
        activity = AudioActivity.analyze(path)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        save_report = RecoveryReportWriter(report_path)

        if not activity.has_sound(0, activity.duration):
            save_report([{"start": 0, "end": activity.duration, "status": "skipped", "reason": "silence"}])
            TranscriptWriter().write(transcript)
            audio.subscript_lines = []
            print("전체 음성이 무음입니다. API 요청 없이 빈 전사 파일을 저장합니다.", flush=True)
            return transcript
        api_key = load_api_key(self.api_key_path)

        try:
            # 구간별 실패 처리는 아래 복구기에 맡기고 숨은 SDK 재시도는 사용하지 않습니다.
            with OpenAI(
                api_key=api_key, base_url="https://api.openai.com/v1",
                timeout=90.0, max_retries=0,
            ) as client:
                def request(clip, destination, model, *, prompt_override=None):
                    options = {"response_format": "json", "language": "ko", "temperature": 0}
                    if model == "whisper-1":
                        options.update(response_format="verbose_json", timestamp_granularities=["segment"])
                    elif model == "gpt-transcribe":
                        # 공식 gpt-transcribe 형식. 현재 SDK에도 extra_body로 언어 힌트를 전달합니다.
                        options = {"extra_body": {"languages": ["ko"]}}
                    try:
                        with clip.open("rb") as source, waiting_for_response():
                            request_client = client if clip == path else client.with_options(max_retries=0, timeout=90.0)
                            response = request_client.audio.transcriptions.create(
                                model=model, file=(clip.name, source, "audio/mpeg"),
                                prompt=prompt if prompt_override is None else prompt_override, **options,
                            )
                        raw = response.model_dump()
                    except APIStatusError as exc:
                        if exc.status_code in (401, 403) or exc.status_code == 429:
                            raise
                        fallback_unavailable = model == "gpt-4o-transcribe" and exc.status_code in (400, 404)
                        # 길이 오류만 구간 복구 대상으로 처리합니다. 설정 오류는 계속 중단합니다.
                        body = exc.body if isinstance(exc.body, dict) else {}
                        error = body.get("error", body)
                        error = error if isinstance(error, dict) else {}
                        message = str(error.get("message", "")).casefold()
                        audio_too_short = exc.status_code == 400 and (
                            error.get("code") == "audio_too_short"
                            or ("audio" in message and "too short" in message)
                        )
                        if (exc.status_code < 500 and exc.status_code not in (408, 409)
                                and not fallback_unavailable and not audio_too_short):
                            raise
                        raw = {"error": "audio_too_short" if audio_too_short else f"HTTP {exc.status_code}",
                               "segments": None}
                    except APIConnectionError:
                        raw = {"error": "connection_failed", "segments": None}
                    with destination.open("x", encoding="utf-8") as output:
                        json.dump(raw, output, ensure_ascii=False, indent=2)
                    return raw

                recovery = TranscriptionRecovery(path, recovery_folder, request, save_report,
                                                 activity=activity, prompt=prompt)
                duration = activity.duration
                if response_file is None:
                    # 원본 응답은 조각별로 보관하고 병합본은 진행 중에도 별도로 저장합니다.
                    progress_writer = RecoveryReportWriter(response_path)
                    def save_progress(items, processed_until):
                        reviews = sum(e["status"] == "needs_review" for e in recovery.events)
                        progress_writer.write_data({"format": "chunked_transcription_v1", "language": "korean",
                            "model": self.MODEL, "timing": "audio_boundaries",
                            "duration": duration, "processed_until": processed_until,
                            "processing_complete": processed_until >= duration,
                            "complete": processed_until >= duration and reviews == 0,
                            "needs_review": reviews, "segments": items})
                    segments = recovery.transcribe_utterances(model=self.MODEL, max_seconds=self.CHUNK_SECONDS,
                                                              save_progress=save_progress)
                    if progress_writer.latest_path != response_path:
                        print(f"전사 병합 기록: {progress_writer.latest_path}", flush=True)
                else:
                    raw = json.loads(Path(response_file).read_text(encoding="utf-8-sig"))
                    with response_path.open("x", encoding="utf-8") as output:
                        json.dump(raw, output, ensure_ascii=False, indent=2)
                    if raw.get("format") == "chunked_transcription_v1":
                        raise ValueError("분할 전사 병합본은 원본 응답이 아닙니다. --transcription-response에는 기존 전체 전사의 원본 JSON을 지정하세요.")
                    segments = recovery.recover(raw.get("segments"), duration)
                if recovery.events:
                    with recovered_path.open("x", encoding="utf-8") as output:
                        json.dump({"duration": duration, "segments": segments}, output,
                                  ensure_ascii=False, indent=2)
                    print(f"복구 기록: {save_report.latest_path}", flush=True)
                    reviews = sum(e["status"] == "needs_review" for e in recovery.events)
                    if reviews:
                        print(f"검토 필요 {reviews}개 구간은 자막에서 제외했습니다. 나머지 구간은 전사했습니다.", flush=True)
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

        for segment in segments:
            start = self._timestamp(segment["start"])
            end = self._timestamp(segment["end"])
            if segment["end"] < segment["start"]:
                raise AudioTranscriptionError("응답에 종료 시간이 시작 시간보다 이른 구간이 있습니다.")
            text = segment["text"].strip()
            if text:
                transcript.add_subscript_line(SubscriptLine(text, start, end))
        if not transcript.subscript_lines:
            print("확인된 발화가 없어 빈 전사를 저장합니다. 검토 기록을 확인하세요.", flush=True)
        TranscriptWriter().write(transcript)
        audio.subscript_lines = list(transcript.subscript_lines)
        return transcript
