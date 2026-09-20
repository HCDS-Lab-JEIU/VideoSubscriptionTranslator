"""로컬 FFmpeg 실행 파일 탐색."""

import shutil


def get_ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError(
            "FFmpeg를 찾을 수 없습니다. python -m pip install -r requirements.txt 를 실행하세요."
        ) from exc
