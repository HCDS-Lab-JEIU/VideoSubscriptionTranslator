"""Exercise the frozen app without sending audio or text to an API."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile


def check_bundle(bundle: Path) -> None:
    bundle = bundle.resolve()
    cli = bundle / "VideoSubtitleTranslator-CLI.exe"
    env = os.environ.copy()
    # Ensure the test cannot accidentally use a developer's system FFmpeg.
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    env.pop("IMAGEIO_FFMPEG_EXE", None)
    env["QT_QPA_PLATFORM"] = "offscreen"

    def run(*args):
        result = subprocess.run([str(arg) for arg in args], env=env,
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=90)
        if result.returncode:
            raise RuntimeError(f"{args[0]} failed: {result.stdout}\n{result.stderr}")
        return result.stdout

    assert "--pipeline" in run(cli, "--help")
    assert "Circuits" in run(cli, "--list-courses")
    ffmpeg, = (bundle / "_internal" / "imageio_ffmpeg" / "binaries").glob("*.exe")
    with tempfile.TemporaryDirectory(prefix="자막 앱 검증 ") as directory:
        root = Path(directory)
        video = root / "강의.mp4"
        run(ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
            "color=c=black:s=320x240:d=1", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=1", "-c:v", "libx264", "-c:a", "aac", video)
        # Extraction is directed to the bundle's public default output directory.
        # Use a unique source name so an existing result is never overwritten.
        unique_video = root / f"{root.name}.mp4"
        video.rename(unique_video)
        audio = bundle / "output_audios" / f"{unique_video.stem}.mp3"
        try:
            run(cli, unique_video, "--extract")
            assert audio.stat().st_size > 0
        finally:
            audio.unlink(missing_ok=True)
            if audio.parent.is_dir() and not any(audio.parent.iterdir()):
                audio.parent.rmdir()
        transcript = root / "영어.txt"
        transcript.write_text("[00:00:00.000, 00:00:00.900] Test subtitle.\n", encoding="utf-8")
        srt = root / "영어.srt"
        output = root / "자막.mp4"
        run(cli, unique_video, "--render", "--subtitle-file", transcript,
            "--srt-output", srt, "--video-output", output)
        assert "Test subtitle." in srt.read_text(encoding="utf-8-sig")
        assert output.stat().st_size > 0
    run(bundle / "VideoSubtitleTranslator.exe", "--smoke-test")
    print("PASS: bundled CLI, textbook, FFmpeg extraction/render and GUI startup")


if __name__ == "__main__":
    check_bundle(Path(sys.argv[1]))
