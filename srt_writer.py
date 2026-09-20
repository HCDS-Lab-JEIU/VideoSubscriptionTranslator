"""타임스탬프 TXT를 표준 SRT로 변환합니다."""

from pathlib import Path
import textwrap

from transcript_reader import TranscriptReader


class SrtWriter:
    def write(self, text_path: str | Path, output_path: str | Path) -> Path:
        source = Path(text_path).expanduser().resolve()
        destination = Path(output_path).expanduser().resolve()
        if destination.suffix.lower() != ".srt":
            raise ValueError("SRT 출력 경로의 확장자는 .srt여야 합니다.")
        lines = TranscriptReader().read(source)
        blocks = []
        for number, line in enumerate(lines, start=1):
            start, end = line.timestamp[1:-1].split(", ")
            wrapped = textwrap.fill(line.text, width=64, break_long_words=False, break_on_hyphens=False)
            blocks.append(f"{number}\n{start.replace('.', ',')} --> {end.replace('.', ',')}\n{wrapped}\n\n")
        content = "".join(blocks)
        if destination.exists():
            if destination.read_text(encoding="utf-8-sig") == content:
                return destination
            raise FileExistsError(f"다른 내용의 SRT가 이미 존재합니다: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8", newline="\n") as output:
            try:
                output.write(content)
            except BaseException:
                output.close()
                destination.unlink(missing_ok=True)
                raise
        return destination
