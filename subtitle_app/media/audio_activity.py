"""보수적인 로컬 무음 검사. 음성 인식이나 VAD 판정은 아닙니다."""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from subtitle_app.media.ffmpeg_tools import get_ffmpeg_executable


@dataclass
class AudioActivity:
    duration: float
    silence: list[tuple[float, float]]
    pauses: list[tuple[float, float]] | None = None

    @classmethod
    def analyze(cls, path: Path):
        from mutagen.mp3 import MP3
        duration = MP3(path).info.length
        result = subprocess.run([
            get_ffmpeg_executable(), "-hide_banner", "-nostdin", "-i", str(path),
            "-map", "0:a:0", "-af",
            "silencedetect@quiet=noise=-60dB:d=0.3,silencedetect@pause=noise=-40dB:d=0.3",
            "-vn", "-f", "null", "-",
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        if result.returncode:
            raise RuntimeError("무음 검사에 실패했습니다. API 요청 전에 입력 음성을 확인하세요.")
        # MP3 헤더 길이에는 인코더 패딩이 포함될 수 있습니다. 실제 디코딩 길이를 사용합니다.
        times = re.findall(r"time=(\d+):(\d+):([\d.]+)", result.stderr)
        if times:
            h, m, s = times[-1]
            decoded = int(h) * 3600 + int(m) * 60 + float(s)
            if decoded > 0:
                duration = min(duration, decoded)
        def intervals_for(tag):
            intervals, start = [], None
            for line in result.stderr.splitlines():
                if "silencedetect@" in line and f"silencedetect@{tag}" not in line:
                    continue
                for kind, value in re.findall(r"silence_(start|end):\s*([0-9.eE+-]+)", line):
                    if kind == "start":
                        start = max(0, float(value))
                    elif start is not None:
                        intervals.append((start, min(duration, float(value))))
                        start = None
            if start is not None:
                intervals.append((start, duration))
            return intervals
        return cls(duration, intervals_for("quiet"), intervals_for("pause"))

    def utterance_ranges(self, *, max_seconds=20.0, pause_seconds=0.6):
        """쉼의 중심에서 나누되 작은 음성을 버리지 않고 확실한 무음만 제외합니다."""
        if max_seconds <= 0 or pause_seconds <= 0:
            raise ValueError("분할 길이와 무음 길이는 양수여야 합니다.")
        # 더 높은 임계값은 경계 후보에만 사용합니다. 작은 실제 발화를 버리지 않습니다.
        pauses = self.silence if self.pauses is None else self.pauses
        quiet = [(a, b) for a, b in self.silence if b - a >= pause_seconds]
        # 작은 목소리 때문에 여러 무음이 하나의 긴 쉼으로 묶여도 실제 무음 경계를 보존합니다.
        candidates = quiet + [(a, b) for a, b in pauses
                              if not any(a < d and b > c for c, d in quiet)]
        boundaries = sorted({0.0, self.duration, *(
            (max(0, a) + min(self.duration, b)) / 2
            for a, b in candidates if b - a >= pause_seconds and a < self.duration and b > 0
        )})
        result = []
        for left, right in zip(boundaries, boundaries[1:]):
            bounds = self.sound_bounds(left, right)
            if bounds is None:
                continue
            start, end = bounds
            # 문장 끝이 검출되지 않는 긴 발화도 무한정 큰 요청으로 만들지 않습니다.
            while end - start > max_seconds:
                result.append((start, start + max_seconds))
                start += max_seconds
            if end > start:
                result.append((start, end))
        return result

    def has_sound(self, start: float, end: float) -> bool:
        start, end = max(0, start), min(self.duration, end)
        if end <= start:
            return False
        quiet = sum(max(0, min(end, b) - max(start, a)) for a, b in self.silence)
        return end - start - quiet > 0.05

    def sound_bounds(self, start: float, end: float):
        if not self.has_sound(start, end):
            return None
        start, end = max(0, start), min(self.duration, end)
        for a, b in self.silence:
            if a <= start < b:
                start = min(end, b)
        for a, b in reversed(self.silence):
            if a < end <= b:
                end = max(start, a)
        return start, end
