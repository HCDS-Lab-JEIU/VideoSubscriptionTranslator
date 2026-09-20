"""파일 경로와 관련 자막을 보관하는 모델."""

from dataclasses import dataclass, field
from pathlib import Path
from subtitle import SubscriptLine


@dataclass
class MediaFile:
    file_path: str | Path
    subscript_lines: list[SubscriptLine] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.file_path = Path(self.file_path).expanduser().resolve()

    def add_subscript_line(self, subscript_line: SubscriptLine) -> None:
        self.subscript_lines.append(subscript_line)

    def get_subscript_lines(self) -> list[SubscriptLine]:
        return self.subscript_lines


class VideoFile(MediaFile):
    """입력 비디오 파일."""


@dataclass
class AudioFile(MediaFile):
    """추출한 음성의 경로와 메타데이터. 음성 샘플은 파일에 보관합니다."""

    sample_rate: int  # 초당 샘플 수 (Hz)
    channels: int
    duration_seconds: float
    bitrate: int  # 초당 비트 수 (bps)
    file_size_bytes: int
    format: str
    sample_width: int | None = None  # PCM 전용, MP3에는 해당하지 않음
    frame_count: int | None = None  # PCM 전용, MP3에는 해당하지 않음

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.sample_rate <= 0 or self.channels <= 0 or self.bitrate <= 0:
            raise ValueError("샘플레이트, 채널 수, 비트레이트는 양수여야 합니다.")
        if self.duration_seconds < 0 or self.file_size_bytes < 0:
            raise ValueError("재생 시간과 파일 크기는 음수일 수 없습니다.")
        if self.sample_width is not None and self.sample_width <= 0:
            raise ValueError("샘플 크기는 양수여야 합니다.")
        if self.frame_count is not None and self.frame_count < 0:
            raise ValueError("프레임 수는 음수일 수 없습니다.")

    @property
    def file_size_mb(self) -> float:
        return self.file_size_bytes / 1_000_000


class SubscriptFile(MediaFile):
    """자막 파일."""
