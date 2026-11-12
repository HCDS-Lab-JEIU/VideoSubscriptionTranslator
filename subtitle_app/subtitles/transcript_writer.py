"""시간 구간을 포함하는 UTF-8 텍스트 저장."""

from subtitle_app.media.media_file import SubscriptFile
from subtitle_app.subtitles.subtitle import TimeStamp


class TranscriptWriter:
    @staticmethod
    def format_time(timestamp: TimeStamp) -> str:
        return str(timestamp).replace(",", ".")

    def write(self, transcript: SubscriptFile) -> None:
        transcript.file_path.parent.mkdir(parents=True, exist_ok=True)
        with transcript.file_path.open("x", encoding="utf-8", newline="\n") as output:
            try:
                for line in transcript.subscript_lines:
                    text = " ".join(line.text.split())
                    output.write(
                        f"[{self.format_time(line.start_time)}, "
                        f"{self.format_time(line.end_time)}] {text}\n"
                    )
            except BaseException:
                output.close()
                transcript.file_path.unlink(missing_ok=True)
                raise
