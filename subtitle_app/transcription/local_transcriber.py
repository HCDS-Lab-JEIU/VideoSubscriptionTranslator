"""Optional, entirely local Whisper transcription with conservative GPU settings."""

import gc
import importlib.util
import math
import os
from pathlib import Path
import subprocess

from subtitle_app.common.app_paths import app_directory
from subtitle_app.media.media_file import MediaFile, SubscriptFile
from subtitle_app.transcription.recovery_report import RecoveryReportWriter
from subtitle_app.subtitles.subtitle import SubscriptLine, TimeStamp
from subtitle_app.textbook.document import DEFAULT_TEXTBOOK_PATH, Textbook
from subtitle_app.subtitles.transcript_writer import TranscriptWriter


LOCAL_MODELS = ("large-v2", "medium", "small")
LOCAL_DEVICES = ("auto", "cuda", "cpu")
_DLL_HANDLES = []


def configure_cuda_libraries():
    """Make optional NVIDIA pip wheels visible to Windows' dynamic DLL loader."""
    if os.name != "nt" or _DLL_HANDLES:
        return
    for package in ("nvidia.cuda_nvrtc", "nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(package)
        except (ImportError, ModuleNotFoundError):
            continue
        for location in (spec.submodule_search_locations or []) if spec else []:
            for folder in (Path(location) / "bin", Path(location) / "lib"):
                if folder.is_dir():
                    _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
                    os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")


def gpu_free_memory_mib() -> int | None:
    """Check physical GPU 0; fail closed when memory cannot be queried."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--id=0", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def _gpu_error(exc: Exception) -> bool:
    message = str(exc).casefold()
    return any(word in message for word in (
        "out of memory", "cuda", "cudnn", "cublas", "insufficient memory",
        "int8_float16", "driver version",
    ))


class LocalTranscriber:
    # Headroom check, NOT a hard allocation limit. Other apps may allocate later.
    MIN_FREE_MIB = 4096

    def __init__(self, output_dir: str | Path,
                 textbook_path: str | Path = DEFAULT_TEXTBOOK_PATH, *,
                 course: str | None = None, model: str = "large-v2", device: str = "auto"):
        if model not in LOCAL_MODELS or device not in LOCAL_DEVICES:
            raise ValueError("지원하지 않는 로컬 Whisper 모델 또는 장치입니다.")
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.textbook_path = Path(textbook_path)
        self.course = course
        self.model_name = model
        self.device = device

    def _select_device(self):
        if self.device == "cpu":
            return "cpu"
        free = gpu_free_memory_mib()
        if free is None or free < self.MIN_FREE_MIB:
            print("GPU 여유 메모리 4GiB를 확인할 수 없어 로컬 CPU INT8로 실행합니다.", flush=True)
            return "cpu"
        return "cuda"

    def _run(self, model_class, path, prompt, device, report):
        compute = "int8_float16" if device == "cuda" else "int8"
        raw = {"format": "local_whisper_v1", "backend": "faster-whisper",
               "model": self.model_name, "device": device, "compute_type": compute,
               "language": "ko", "complete": False, "segments": []}
        report.write_data(raw)
        model = None
        stream = None
        try:
            print(f"로컬 Whisper 로드: {self.model_name} / {device} / {compute}. "
                  "첫 실행은 공개 가중치를 다운로드합니다.", flush=True)
            model = model_class(
                self.model_name, device=device, device_index=0, compute_type=compute,
                num_workers=1, cpu_threads=4,
                download_root=str(app_directory() / "models" / "whisper"),
            )
            # Standard WhisperModel streams 30-second windows, without batching.
            stream, info = model.transcribe(
                str(path), language="ko", task="transcribe", beam_size=1, best_of=1,
                temperature=0, condition_on_previous_text=False,
                initial_prompt=prompt, vad_filter=True, word_timestamps=False,
            )
            raw["duration"] = info.duration
            for segment in stream:
                start, end = float(segment.start), float(segment.end)
                if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end):
                    raise ValueError("로컬 전사에 잘못된 타임스탬프가 있습니다.")
                # Whisper/VAD can put the last timestamp just past the decoded audio.
                end = min(end, info.duration)
                if start >= end:
                    continue
                text = segment.text.strip()
                if text:
                    raw["segments"].append({"start": start, "end": end, "text": text})
                    raw["processed_until"] = end
                    report.write_data(raw)
                    print(f"로컬 전사 진행: {end:.1f} / {info.duration:.1f}초", flush=True)
            raw["complete"] = True
            raw["processed_until"] = info.duration
            report.write_data(raw)
            return raw["segments"]
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()
            if model is not None:
                try:
                    model.model.unload_model()
                except (RuntimeError, OSError):
                    pass  # Preserve the original inference error; release references below.
            del stream, model
            gc.collect()

    def transcribe(self, audio: MediaFile) -> SubscriptFile:
        path = audio.file_path
        if not path.is_file():
            raise FileNotFoundError(f"입력 파일이 없습니다: {path}")
        if path.suffix.lower() != ".mp3" or path.stat().st_size == 0:
            raise ValueError("로컬 전사 입력은 비어 있지 않은 MP3 파일이어야 합니다.")
        transcript = SubscriptFile(self.output_dir / f"{path.stem}.txt")
        response_path = transcript.file_path.with_suffix(".json")
        for destination in (transcript.file_path, response_path):
            if destination.exists():
                raise FileExistsError(f"전사 결과가 이미 존재합니다: {destination}")
        prompt = Textbook.load(self.textbook_path).select_course(self.course).transcription_prompt()
        configure_cuda_libraries()
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "로컬 Whisper 의존성이 없습니다. translator 환경에서 "
                "-m pip install -r requirements-local.txt 를 실행하세요."
            ) from None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report = RecoveryReportWriter(response_path)
        device = self._select_device()
        retry_cpu = False
        try:
            segments = self._run(WhisperModel, path, prompt, device, report)
        except (RuntimeError, OSError) as exc:
            if device != "cuda" or not _gpu_error(exc):
                raise
            # Retry outside the except block so the traceback releases GPU objects.
            retry_cpu = True
            print("GPU 메모리 또는 CUDA 실행 오류: GPU를 해제하고 로컬 CPU INT8로 "
                  "처음부터 재시도합니다. API는 호출하지 않습니다.", flush=True)
        if retry_cpu:
            gc.collect()
            segments = self._run(WhisperModel, path, prompt, "cpu", report)
        for segment in segments:
            transcript.add_subscript_line(SubscriptLine(
                segment["text"], TimeStamp.from_milliseconds(round(segment["start"] * 1000)),
                TimeStamp.from_milliseconds(round(segment["end"] * 1000)),
            ))
        TranscriptWriter().write(transcript)
        audio.subscript_lines = list(transcript.subscript_lines)
        return transcript
