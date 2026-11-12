"""Render contiguous subtitle groups; concatenate video and encode audio once."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
from pathlib import Path
import re
import subprocess
import threading
from dataclasses import dataclass


SUBTITLE_FILTER = (
    "subtitles=filename=captions.srt:charenc=UTF-8:"
    "force_style='FontName=Arial,FontSize=18,Outline=1,Shadow=1,MarginV=20'"
)


def physical_core_count() -> int:
    """Count physical cores without estimating from logical processor count."""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            query = ctypes.WinDLL("kernel32", use_last_error=True).GetLogicalProcessorInformationEx
            query.argtypes = [wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
            query.restype = wintypes.BOOL
            size = wintypes.DWORD()
            query(0, None, ctypes.byref(size))  # RelationProcessorCore, all processor groups.
            if not size.value:
                return 1
            buffer = ctypes.create_string_buffer(size.value)
            if not query(0, buffer, ctypes.byref(size)):
                return 1
            offset, cores = 0, 0
            while offset + 8 <= size.value:
                relation = wintypes.DWORD.from_buffer(buffer, offset).value
                length = wintypes.DWORD.from_buffer(buffer, offset + 4).value
                if length < 8 or offset + length > size.value:
                    return 1
                cores += relation == 0
                offset += length
            return max(1, cores)
        topology = Path("/sys/devices/system/cpu")
        if topology.is_dir():
            cores = {
                ((cpu / "topology/physical_package_id").read_text().strip(),
                 (cpu / "topology/core_id").read_text().strip())
                for cpu in topology.glob("cpu[0-9]*")
            }
            return max(1, len(cores))
        result = subprocess.run(["sysctl", "-n", "hw.physicalcpu"],
                                capture_output=True, text=True, timeout=5, check=True)
        return max(1, int(result.stdout))
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1


@dataclass(frozen=True)
class SubtitleSegment:
    first: int  # One-based subtitle positions in chronological order.
    last: int
    start: float
    end: float


def subtitle_segments(path: Path, duration: float, cores: int) -> list[SubtitleSegment]:
    """Balance subtitle counts into consecutive groups, keeping the full timeline."""
    timestamp = r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})"
    timing = re.compile(rf"^{timestamp}\s+-->\s+{timestamp}(?:\s+.*)?$", re.MULTILINE)
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        match = timing.search(block)
        if match is None:
            raise RuntimeError("SRT 자막의 시간 구간을 확인할 수 없습니다.")
        values = list(map(int, match.groups()))
        start, end = (values[i] * 3600 + values[i + 1] * 60 + values[i + 2]
                      + values[i + 3] / 1000 for i in (0, 4))
        if end < start:
            raise RuntimeError("SRT 자막의 종료 시간이 시작 시간보다 이릅니다.")
        cues.append((start, end))
    cues.sort()
    workers = min(len(cues), max(1, cores))
    width, remainder = divmod(len(cues), workers)
    boundaries = [(0, 0.0)]
    position = 0
    for index in range(workers - 1):
        position += width + (index < remainder)
        cut = cues[position][0]
        cut_position = position
        while cut_position > 0 and cues[cut_position - 1][0] == cut:
            cut_position -= 1
        # Simultaneous starts must stay together; never produce empty intervals.
        if cut_position > boundaries[-1][0] and boundaries[-1][1] < cut < duration:
            boundaries.append((cut_position, cut))
    return [SubtitleSegment(first + 1, boundaries[i + 1][0] if i + 1 < len(boundaries)
                            else len(cues), start,
                            boundaries[i + 1][1] if i + 1 < len(boundaries) else duration)
            for i, (first, start) in enumerate(boundaries)]


def render_parallel(executable: str, video: Path, folder: Path, output: Path) -> None:
    """Render video-only pieces, preserving subtitle time on the source timeline."""
    probe = subprocess.run(
        [executable, "-hide_banner", "-nostdin", "-i", str(video)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    # FFmpeg reports input metadata and exits nonzero when no output is specified.
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if match is None:
        raise RuntimeError("영상 길이를 확인할 수 없습니다. 병렬 처리를 끄고 다시 실행하세요.")
    hours, minutes, seconds = map(float, match.groups())
    duration = hours * 3600 + minutes * 60 + seconds
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("병렬 처리에 사용할 영상 길이가 올바르지 않습니다.")
    cores = physical_core_count()
    segments = subtitle_segments(folder / "captions.srt", duration, cores)
    count = len(segments)
    workers = count
    threads = max(1, cores // workers)
    cancelled = threading.Event()
    lock = threading.Lock()
    processes = set()

    def stop_workers():
        with lock:
            cancelled.set()
            for process in processes:
                if process.poll() is None:
                    process.terminate()

    def run(arguments, label):
        log_path = folder / f"{label}.log"
        with log_path.open("w", encoding="utf-8") as log:
            with lock:
                if cancelled.is_set():
                    raise RuntimeError("병렬 렌더링이 중단되었습니다.")
                process = subprocess.Popen(
                    [executable, "-hide_banner", "-loglevel", "error", "-nostdin", "-n"] + arguments,
                    cwd=folder, stdout=subprocess.PIPE, stderr=log,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                processes.add(process)
            try:
                frames = 0
                for line in process.stdout:
                    if line.startswith("frame="):
                        frames = int(line.split("=", 1)[1])
                    if line.startswith("out_time="):
                        print(f"{label} 처리 위치: {line.strip().split('=', 1)[1]}", flush=True)
                code = process.wait()
                if code:
                    details = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                    raise RuntimeError(f"{label} FFmpeg 처리 실패:\n{details}")
                return frames
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                process.stdout.close()
                with lock:
                    processes.discard(process)

    def segment(index):
        piece = segments[index]
        start = piece.start
        # Keep fractional frame offsets after accurate input seeking. The first
        # setpts restores source time for libass; the second restores local time.
        filters = (
            f"setpts=PTS+{start:.9f}/TB,{SUBTITLE_FILTER},"
            f"setpts=PTS-{start:.9f}/TB,pad=ceil(iw/2)*2:ceil(ih/2)*2"
        )
        args = ["-threads", str(threads), "-ss", f"{start:.9f}", "-i", str(video),
                "-map", "0:v:0", "-an", "-filter_threads", "1", "-vf", filters,
                "-c:v", "libx264", "-threads", str(threads), "-preset", "medium",
                "-crf", "20", "-pix_fmt", "yuv420p", "-fps_mode", "passthrough",
                "-video_track_timescale", "90000"]
        # Do not truncate the last piece to rounded container metadata duration.
        if index < count - 1:
            args += ["-t", f"{piece.end - start:.9f}"]
        args += ["-progress", "pipe:1", "-stats_period", "5", "-nostats", f"part-{index:05d}.mp4"]
        return run(args, f"구간 {index + 1}-{count} (자막 {piece.first}~{piece.last})")

    print(f"자막 MP4 병렬 생성 중... 물리 코어 {cores}개 / 자막 기준 {count}개 연속 구간", flush=True)
    for piece in segments:
        print(f"자막 {piece.first}~{piece.last}: {piece.start:.3f}~{piece.end:.3f}초", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(segment, index): index for index in range(count)}
        frame_counts = [0] * count
        try:
            for completed, future in enumerate(as_completed(futures), 1):
                frame_counts[futures[future]] = future.result()
                print(f"병렬 렌더링 완료: {completed}/{count}", flush=True)
        except BaseException:
            stop_workers()
            for future in futures:
                future.cancel()
            raise

    # Container duration may include audio longer than video, or be rounded up
    # just past a cut. Empty trailing pieces must not enter the concat demuxer.
    while frame_counts and frame_counts[-1] == 0:
        frame_counts.pop()
    if not frame_counts or any(frames == 0 for frames in frame_counts):
        raise RuntimeError("병렬 처리한 영상 구간에 프레임이 없습니다. 기존 방식으로 다시 실행하세요.")
    count = len(frame_counts)

    manifest = ["ffconcat version 1.0"]
    for index in range(count):
        manifest.append(f"file 'part-{index:05d}.mp4'")
        # Default concat inpoint is the first PTS, which would erase the
        # fractional frame gap between a cut and its first decoded frame.
        manifest.append("inpoint 0")
        if index < count - 1:
            # Fixed offsets prevent rounding error accumulating across pieces.
            manifest.append(f"duration {segments[index].end - segments[index].start:.9f}")
    (folder / "parts.ffconcat").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print("병렬 구간 연결 및 원본 음성 합치는 중...", flush=True)
    run(["-f", "concat", "-safe", "1", "-i", "parts.ffconcat", "-i", str(video),
         "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-progress", "pipe:1", "-stats_period", "5", "-nostats",
         str(output)], "최종 연결")
