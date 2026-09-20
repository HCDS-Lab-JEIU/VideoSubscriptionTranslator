"""기존 타임스탬프 표기를 그대로 보존하며 자막 TXT를 읽습니다."""

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class SubtitleTextLine:
    timestamp: str
    text: str


class TranscriptReader:
    TIME = r"\d{2,}:[0-5]\d:[0-5]\d\.\d{3}"
    LINE = re.compile(rf"^(\[({TIME}), ({TIME})\])\s+(.+)$")

    @staticmethod
    def _seconds(timestamp: str) -> float:
        hours, minutes, seconds = timestamp.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def read(self, file_path: str | Path) -> list[SubtitleTextLine]:
        path = Path(file_path).expanduser().resolve()
        if path.suffix.lower() != ".txt":
            raise ValueError("입력은 타임스탬프가 포함된 자막 TXT 파일이어야 합니다.")
        lines = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            if not line.strip():
                continue
            match = self.LINE.fullmatch(line.strip())
            if not match or not match[4].strip():
                raise ValueError(f"자막 {number}행의 '[HH:MM:SS.mmm, HH:MM:SS.mmm] 텍스트' 형식을 확인하세요.")
            if self._seconds(match[3]) < self._seconds(match[2]):
                raise ValueError(f"자막 {number}행의 종료 시간이 시작 시간보다 이릅니다.")
            lines.append(SubtitleTextLine(match[1], match[4].strip()))
        if not lines:
            raise ValueError("처리할 자막이 없습니다.")
        return lines
