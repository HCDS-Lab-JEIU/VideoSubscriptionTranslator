"""영상 하나에서 영어 자막 영상까지 순서대로 처리합니다."""

from pathlib import Path
import json
import tempfile

from subtitle_app.common.api_config import load_api_key
from subtitle_app.media.audio_extractor import AudioExtractor
from subtitle_app.transcription.audio_transcriber import AudioTranscriber
from subtitle_app.transcription.local_transcriber import LocalTranscriber, LOCAL_DEVICES, LOCAL_MODELS
from subtitle_app.translation.codex_translator import CodexSubtitleTranslator, check_codex_login
from subtitle_app.media.media_file import MediaFile
from subtitle_app.subtitles.srt_writer import SrtWriter
from subtitle_app.translation.subtitle_translator import SubtitleTranslator
from subtitle_app.textbook.document import Textbook
from subtitle_app.rendering.video_subtitler import VideoSubtitler
from subtitle_app.pipeline.events import SUBTITLE_READY_PREFIX


def run_pipeline(video_path: Path, output_root: Path, api_key_file: Path,
                 textbook_file: Path, *, course: str | None = None,
                 parallel_render: bool = False, transcription_backend: str = "openai",
                 local_model: str = "large-v2", local_device: str = "auto",
                 translation_backend: str = "openai", codex_model: str | None = None,
                 codex_executable: str | Path | None = None, codex_reasoning: str | None = None) -> Path:
    if translation_backend not in ("openai", "codex"):
        raise ValueError("지원하지 않는 번역 방식입니다.")
    if transcription_backend not in ("openai", "local"):
        raise ValueError("지원하지 않는 전사 방식입니다.")
    if transcription_backend == "local" and (local_model not in LOCAL_MODELS or local_device not in LOCAL_DEVICES):
        raise ValueError("지원하지 않는 로컬 Whisper 모델 또는 장치입니다.")
    video = MediaFile(video_path)
    if not video.file_path.is_file():
        raise FileNotFoundError(f"입력 영상이 없습니다: {video.file_path}")
    if video.file_path.suffix.lower() not in {
        ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".ts", ".mts",
    }:
        raise ValueError("전체 파이프라인에는 MP4, MKV, MOV 등의 영상 파일을 입력하세요.")
    # 오래 걸리는 추출 전에 필수 설정을 검증합니다. 키는 출력하지 않습니다.
    if transcription_backend == "openai" or translation_backend == "openai":
        load_api_key(api_key_file)
    if translation_backend == "codex":
        check_codex_login(codex_executable)
    selected = Textbook.load(textbook_file).select_course(course)
    course = selected.course
    print(f"선택 과목: {course}", flush=True)
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=f"{video.file_path.stem}-", dir=root))
    print(f"결과 폴더: {folder}", flush=True)
    print("전사: " + ("유료 OpenAI API" if transcription_backend == "openai" else "로컬 Whisper")
          + " / 번역: " + ("유료 OpenAI API" if translation_backend == "openai"
                           else "Codex CLI (로그인 계정의 사용 한도 적용)"), flush=True)
    stage = "오디오 추출"
    try:
        print(f"[1/5] {stage}", flush=True)
        audio = AudioExtractor(folder / "audio").extract(video)
        stage = "한국어 전사"
        print(f"[2/5] {stage}", flush=True)
        if transcription_backend == "local":
            transcriber = LocalTranscriber(folder / "transcripts", textbook_file, course=course,
                                           model=local_model, device=local_device)
        else:
            transcriber = AudioTranscriber(api_key_file, folder / "transcripts", textbook_file, course=course)
        transcript = transcriber.transcribe(audio)
        if not transcript.file_path.read_text(encoding="utf-8-sig").strip():
            print("자막으로 만들 발화가 없습니다. 번역·합성을 생략하고 원본 영상을 반환합니다.", flush=True)
            return video.file_path
        stage = "영어 번역"
        print(f"[3/5] {stage}", flush=True)
        if translation_backend == "codex":
            translator = CodexSubtitleTranslator(textbook_file, course=course, model=codex_model,
                                                 executable=codex_executable, reasoning=codex_reasoning)
        else:
            translator = SubtitleTranslator(api_key_file, textbook_file, course=course)
        translated = translator.translate(transcript.file_path)
        stage = "SRT 생성"
        print(f"[4/5] {stage}", flush=True)
        srt = SrtWriter().write(translated, folder / f"{translated.stem}.srt")
        print(SUBTITLE_READY_PREFIX + json.dumps({
            "video": str(video.file_path.resolve()), "srt": str(srt.resolve()),
        }, ensure_ascii=False), flush=True)
        stage = "자막 영상 생성"
        print(f"[5/5] {stage}", flush=True)
        render_options = {"parallel": True} if parallel_render else {}
        result = VideoSubtitler().render(video.file_path, srt, folder / f"{translated.stem}.mp4",
                                        **render_options)
    except (OSError, ValueError, RuntimeError):
        print(f"중단 단계: {stage}. 완료된 중간 결과는 {folder}에 보관됩니다.", flush=True)
        raise
    return result
