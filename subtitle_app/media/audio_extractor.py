"""FFmpeg를 이용한 오디오 추출."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from subtitle_app.media.media_file import AudioFile, MediaFile
from subtitle_app.media.ffmpeg_tools import get_ffmpeg_executable


class AudioExtractionError(RuntimeError):
    """FFmpeg 실행 또는 오디오 변환 실패."""


class AudioExtractor:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).expanduser().resolve()

    @staticmethod
    def _ffmpeg_executable() -> str:
        try:
            return get_ffmpeg_executable()
        except RuntimeError as exc:
            raise AudioExtractionError(str(exc)) from exc

    def extract(self, video: MediaFile) -> AudioFile:
        if not video.file_path.is_file():
            raise FileNotFoundError(f"입력 파일이 없습니다: {video.file_path}")
        destination = self.output_dir / f"{video.file_path.stem}.mp3"
        if destination.exists():
            raise FileExistsError(f"출력 파일이 이미 존재합니다: {destination}")
        executable = self._ffmpeg_executable()
        try:
            from mutagen import MutagenError
            from mutagen.mp3 import MP3
        except ImportError as exc:
            raise AudioExtractionError(
                "python -m pip install -r requirements.txt 를 실행하세요."
            ) from exc
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # 변환 실패 시 불완전한 파일이 최종 출력 경로에 남지 않도록 합니다.
        with tempfile.TemporaryDirectory(prefix=".extract-", dir=self.output_dir) as temp_dir:
            temporary = Path(temp_dir) / "audio.mp3"
            result = subprocess.run(
                [
                    executable, "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-n", "-i", str(video.file_path), "-map", "0:a:0", "-vn",
                    "-map_metadata", "-1", "-c:a", "libmp3lame",
                    "-ac", "1", "-ar", "16000", "-b:a", "32k", str(temporary),
                ],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if result.returncode:
                raise AudioExtractionError(
                    "파일을 읽을 수 없거나 오디오 트랙을 추출할 수 없습니다.\n"
                    + result.stderr.strip()
                )
            try:
                info = MP3(temporary).info
                audio = AudioFile(
                    file_path=destination,
                    sample_rate=info.sample_rate,
                    channels=info.channels,
                    duration_seconds=info.length,
                    bitrate=info.bitrate,
                    file_size_bytes=temporary.stat().st_size,
                    format="mp3",
                )
            except MutagenError as exc:
                raise AudioExtractionError("추출한 MP3의 정보를 읽을 수 없습니다.") from exc
            # 독점 생성으로 기존 결과를 보호합니다.
            with destination.open("xb") as output:
                try:
                    with temporary.open("rb") as source:
                        shutil.copyfileobj(source, output)
                except BaseException:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise
        return audio
