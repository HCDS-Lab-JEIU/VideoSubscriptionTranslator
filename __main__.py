"""전체 영상 자막 파이프라인과 개별 작업의 실행 진입점."""

import argparse
from pathlib import Path
import sys

from audio_extractor import AudioExtractionError, AudioExtractor
from media_file import MediaFile


def main() -> int:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="MP3 추출, 한국어 전사, 영어 자막 번역을 수행합니다.")
    parser.add_argument("filepath", type=Path, help="비디오/오디오 또는 한국어 자막 TXT 경로")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--pipeline", action="store_true", help="전체 파이프라인 실행 (기본, 유료 API 호출)")
    action.add_argument("--extract", action="store_true", help="오디오 추출만 수행 (로컬 작업)")
    action.add_argument("--transcribe", action="store_true", help="Whisper API로 한국어 구간 전사 (유료 API 호출)")
    action.add_argument("--translate", action="store_true", help="한국어 TXT를 영어 자막으로 번역 (유료 API 호출)")
    action.add_argument("--make-srt", action="store_true", help="자막 TXT를 SRT로 변환 (로컬 작업)")
    action.add_argument("--render", action="store_true", help="원본 영상에 영어 자막을 합성한 MP4 생성 (로컬 작업)")
    parser.add_argument("--pipeline-output-dir", type=Path, default=project_dir / "output_runs",
                        help="전체 실행 결과 폴더의 상위 경로 (실행마다 새 하위 폴더 생성)")
    parser.add_argument("--subtitle-file", type=Path,
                        default=project_dir / "output_txts" / "serial_circuits_01_en.txt",
                        help="영상에 넣을 타임스탬프 자막 TXT")
    parser.add_argument("--srt-output", type=Path, help="SRT 저장 경로")
    parser.add_argument("--video-output", type=Path, help="자막 MP4 저장 경로")
    parser.add_argument("--translation-output", type=Path,
                        help="영어 TXT 저장 경로 (기본: 입력 파일의 _kr를 _en으로 변경)")
    parser.add_argument("--api-key-file", type=Path,
                        default=project_dir / "secrets" / "openai_api_key.txt",
                        help="API 키를 한 줄로 저장한 파일 경로")
    parser.add_argument("--textbook-file", type=Path,
                        default=project_dir / "secrets" / "textbook.txt",
                        help="공통·전사·번역 규칙과 과목별 강의명·단어장을 저장한 텍스트북")
    parser.add_argument("--transcript-output-dir", type=Path,
                        default=project_dir / "output_txts",
                        help="TXT와 JSON 저장 폴더 (재전사 시 다른 폴더 지정 가능)")
    args = parser.parse_args()
    try:
        if args.pipeline or not any((args.extract, args.transcribe, args.translate, args.make_srt, args.render)):
            if any((args.srt_output, args.video_output, args.translation_output)):
                raise ValueError("전체 실행의 저장 위치는 --pipeline-output-dir로 지정하세요.")
            try:
                from pipeline import run_pipeline
            except ImportError:
                raise ValueError("python -m pip install -r requirements.txt 를 실행하세요.") from None
            result = run_pipeline(args.filepath, args.pipeline_output_dir, args.api_key_file, args.textbook_file)
            print(f"전체 파이프라인 완료: {result}", flush=True)
            return 0
        if args.make_srt or args.render:
            from srt_writer import SrtWriter
            subtitle_text = args.filepath if args.make_srt else args.subtitle_file
            srt_path = args.srt_output or project_dir / "output_subtitles" / f"{subtitle_text.stem}.srt"
            srt = SrtWriter().write(subtitle_text, srt_path)
            print(f"SRT 저장 완료: {srt}", flush=True)
            if args.render:
                from video_subtitler import VideoSubtitler, VideoSubtitleError
                video_path = args.video_output or project_dir / "output_videos" / f"{subtitle_text.stem}.mp4"
                try:
                    result = VideoSubtitler().render(args.filepath, srt, video_path)
                except VideoSubtitleError as exc:
                    print(f"영상 생성 실패: {exc}", file=sys.stderr)
                    return 1
                print(f"자막 MP4 저장 완료: {result}")
            return 0
        if args.translate:
            try:
                from subtitle_translator import SubtitleTranslator, SubtitleTranslationError
            except ImportError:
                raise ValueError("python -m pip install -r requirements.txt 를 실행하세요.") from None
            try:
                output = SubtitleTranslator(args.api_key_file, args.textbook_file).translate(
                    args.filepath, args.translation_output,
                )
            except SubtitleTranslationError as exc:
                print(f"번역 실패: {exc}", file=sys.stderr)
                return 1
            print(f"영어 자막: {output}")
            return 0
        if args.transcribe:
            # 추출만 수행할 때에는 SDK와 API 키가 필요하지 않습니다.
            try:
                from audio_transcriber import AudioTranscriber, AudioTranscriptionError
            except ImportError:
                raise ValueError("python -m pip install -r requirements.txt 를 실행하세요.") from None
            audio = MediaFile(args.filepath)
            if args.filepath.suffix.lower() != ".mp3":
                audio = AudioExtractor(project_dir / "output_audios").extract(audio)
            print("한국어 전사 요청 중: whisper-1 / segment", flush=True)
            try:
                transcript = AudioTranscriber(
                    args.api_key_file, args.transcript_output_dir, args.textbook_file,
                ).transcribe(audio)
            except AudioTranscriptionError as exc:
                print(f"전사 실패: {exc}", file=sys.stderr)
                return 1
            print(f"전사 저장 완료: {transcript.file_path}")
            print(f"구간 수: {len(transcript.subscript_lines)}")
            return 0
        extractor = AudioExtractor(project_dir / "output_audios")
        audio = extractor.extract(MediaFile(args.filepath))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"작업 실패: {exc}", file=sys.stderr)
        return 1
    print(f"오디오 저장 완료: {audio.file_path}")
    print(f"MP3 | {audio.sample_rate} Hz | {audio.channels}채널 | "
          f"{audio.bitrate // 1000} kbps | {audio.file_size_mb:.2f} MB | "
          f"{audio.duration_seconds:.1f}초")
    if audio.file_size_bytes >= 25_000_000:
        print("25 MB 이상입니다. API 업로드 전에 파일을 나눠야 합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
