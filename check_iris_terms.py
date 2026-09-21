"""Iris 영상의 짧은 원음을 기존/전용 힌트와 두 모델로 비교합니다 (유료 API)."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from openai import OpenAI

from api_config import load_api_key
from audio_transcriber import AudioTranscriber
from console_status import waiting_for_response
from ffmpeg_tools import get_ffmpeg_executable
from media_file import MediaFile
from textbook import Textbook
from transcription_recovery import extract_clip


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--start", type=float, default=1789)
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if args.start < 0 or not 0 < args.seconds <= 60:
        parser.error("시작은 0초 이상, 비교 길이는 0초 초과 60초 이하여야 합니다.")
    root = Path(__file__).resolve().parent
    output = root / "output_runs"
    output.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="iris-term-check-", dir=output))
    print(f"비교 결과: {folder}", flush=True)
    clip = folder / "sample.mp3"
    extract_clip(args.video, clip, args.start, args.start + args.seconds)
    subprocess.run([
        get_ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
        "-ss", str(args.start + args.seconds / 2), "-i", str(args.video),
        "-frames:v", "1", str(folder / "slide.png"),
    ], check=True)
    key = root / "secrets" / "openai_api_key.txt"
    results = {"source": str(args.video), "start": args.start, "seconds": args.seconds}
    for name, book in [("original_prompt", root / "secrets" / "textbook.txt"),
                       ("iris_prompt", root / "textbooks" / "aiml_iris.txt")]:
        transcript = AudioTranscriber(key, folder / name, book, course="AI/ML").transcribe(MediaFile(clip))
        results[name] = transcript.file_path.read_text(encoding="utf-8")
        print(f"{name}: {results[name]}", flush=True)
    with OpenAI(api_key=load_api_key(key), base_url="https://api.openai.com/v1",
                max_retries=2, timeout=180) as client, clip.open("rb") as source, waiting_for_response():
        response = client.audio.transcriptions.create(
            model="gpt-4o-transcribe", file=source, language="ko", response_format="json",
            prompt=Textbook.load(root / "textbooks" / "aiml_iris.txt").transcription_prompt(),
        )
    (folder / "second_model.json").write_text(response.model_dump_json(indent=2), encoding="utf-8")
    results["second_model"] = response.text
    (folder / "comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"second_model: {response.text}", flush=True)


if __name__ == "__main__":
    main()
