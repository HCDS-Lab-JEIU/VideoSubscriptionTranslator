"""SRT를 영상 화면에 합성한 MP4 생성. 외부 API를 사용하지 않습니다."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from ffmpeg_tools import get_ffmpeg_executable


class VideoSubtitleError(RuntimeError):
    """자막 영상 생성 실패."""


class VideoSubtitler:
    def render(self, video_path: str | Path, srt_path: str | Path,
               output_path: str | Path, *, parallel: bool = False) -> Path:
        video = Path(video_path).expanduser().resolve()
        subtitles = Path(srt_path).expanduser().resolve()
        destination = Path(output_path).expanduser().resolve()
        for source in (video, subtitles):
            if not source.is_file():
                raise FileNotFoundError(f"입력 파일이 없습니다: {source}")
        if destination.suffix.lower() != ".mp4" or destination == video:
            raise ValueError("원본과 다른 .mp4 출력 경로를 지정하세요.")
        if destination.exists():
            raise FileExistsError(f"출력 영상이 이미 존재합니다: {destination}")
        try:
            executable = get_ffmpeg_executable()
        except RuntimeError as exc:
            raise VideoSubtitleError(str(exc)) from exc
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".render-", dir=destination.parent) as temporary_dir:
            folder = Path(temporary_dir)
            # 고정된 상대 파일명으로 Windows 드라이브 문자와 특수문자 필터 이스케이프를 피합니다.
            shutil.copyfile(subtitles, folder / "captions.srt")
            temporary_video = folder / "rendered.mp4"
            if parallel:
                from parallel_video_renderer import render_parallel
                try:
                    render_parallel(executable, video, folder, temporary_video)
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    raise VideoSubtitleError(f"병렬 자막 영상 생성에 실패했습니다.\n{exc}") from exc
            else:
                log_path = folder / "ffmpeg.log"
                command = [
                    executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                    "-i", str(video), "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", "subtitles=filename=captions.srt:charenc=UTF-8:"
                    "force_style='FontName=Arial,FontSize=18,Outline=1,Shadow=1,MarginV=20',"
                    "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    "-progress", "pipe:1", "-stats_period", "5", "-nostats", str(temporary_video),
                ]
                print("자막 MP4 생성 중... (로컬 FFmpeg)", flush=True)
                with log_path.open("w", encoding="utf-8") as log:
                    with subprocess.Popen(command, cwd=folder, stdout=subprocess.PIPE, stderr=log,
                                          text=True, encoding="utf-8", errors="replace") as process:
                        try:
                            for progress in process.stdout:
                                if progress.startswith("out_time="):
                                    print(f"영상 처리 위치: {progress.strip().split('=', 1)[1]}", flush=True)
                            returncode = process.wait()
                        except BaseException:
                            process.terminate()
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            raise
                if returncode:
                    details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise VideoSubtitleError(f"FFmpeg 자막 영상 생성에 실패했습니다.\n{details}")
            with destination.open("xb") as output:
                try:
                    with temporary_video.open("rb") as source:
                        shutil.copyfileobj(source, output)
                except BaseException:
                    output.close()
                    destination.unlink(missing_ok=True)
                    raise
        return destination
