"""Bounded FFmpeg workers; concatenate video and encode original audio once."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import os
from pathlib import Path
import re
import subprocess
import threading


SEGMENT_SECONDS = 60.0
SUBTITLE_FILTER = (
    "subtitles=filename=captions.srt:charenc=UTF-8:"
    "force_style='FontName=Arial,FontSize=18,Outline=1,Shadow=1,MarginV=20'"
)


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
    count = math.ceil(duration / SEGMENT_SECONDS)
    cpus = os.cpu_count() or 1
    workers = min(count, 4, max(1, cpus // 2))
    threads = max(1, min(8, cpus // workers))
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
        start = index * SEGMENT_SECONDS
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
            args += ["-t", f"{SEGMENT_SECONDS:.9f}"]
        args += ["-progress", "pipe:1", "-stats_period", "5", "-nostats", f"part-{index:05d}.mp4"]
        return run(args, f"구간 {index + 1}-{count}")

    print(f"자막 MP4 병렬 생성 중... {count}개 구간 / 최대 {workers}개 동시 처리", flush=True)
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
            manifest.append(f"duration {SEGMENT_SECONDS:.9f}")
    (folder / "parts.ffconcat").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print("병렬 구간 연결 및 원본 음성 합치는 중...", flush=True)
    run(["-f", "concat", "-safe", "1", "-i", "parts.ffconcat", "-i", str(video),
         "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", "-progress", "pipe:1", "-stats_period", "5", "-nostats",
         str(output)], "최종 연결")
