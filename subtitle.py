"""자막 시간과 한 줄의 자막을 표현하는 모델."""

from dataclasses import dataclass


@dataclass
class TimeStamp:
    hours: int
    minutes: int
    seconds: int
    milliseconds: int

    def __str__(self) -> str:
        return f"{self.hours:02}:{self.minutes:02}:{self.seconds:02},{self.milliseconds:03}"

    def to_milliseconds(self) -> int:
        return self.hours * 3600000 + self.minutes * 60000 + self.seconds * 1000 + self.milliseconds

    @classmethod
    def from_milliseconds(cls, milliseconds: int) -> "TimeStamp":
        hours, remainder = divmod(milliseconds, 3600000)
        minutes, remainder = divmod(remainder, 60000)
        seconds, milliseconds = divmod(remainder, 1000)
        return cls(hours, minutes, seconds, milliseconds)


@dataclass
class SubscriptLine:
    text: str
    start_time: TimeStamp
    end_time: TimeStamp
