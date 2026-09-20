"""Qt에 의존하지 않는 편집 데이터와 텍스트북 저장소."""

from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

from textbook import Course, Textbook


@dataclass
class CourseDraft:
    name: str
    rows: list[list[str]]


class TextbookDocument:
    """입력 중인 빈 셀도 유지하고 저장 시 전체 과목을 검증합니다."""

    def __init__(self, book: Textbook):
        self.rules = {
            "common_rules": book.common_rules,
            "whisper_rules": book.whisper_rules,
            "translation_rules": book.translation_rules,
        }
        self.courses = [CourseDraft(c.name, [[k, v] for k, v in c.terminology.items()])
                        for c in book.courses]
        self.dirty = False

    def set_rule(self, name: str, value: str) -> None:
        if name not in self.rules:
            raise ValueError(f"알 수 없는 규칙: {name}")
        if self.rules[name] != value:
            self.rules[name] = value
            self.dirty = True

    def add_course(self, name: str) -> int:
        name = name.strip()
        self._validate_line(name, "과목명")
        if any(c.name.casefold() == name.casefold() for c in self.courses):
            raise ValueError("이미 존재하는 과목명입니다.")
        self.courses.append(CourseDraft(name, [["", ""]]))
        self.dirty = True
        return len(self.courses) - 1

    @staticmethod
    def _validate_line(value: str, label: str) -> None:
        if not value or len(value.splitlines()) != 1 or value.startswith("#") or (
            value.startswith("[") and value.endswith("]")
        ):
            raise ValueError(f"{label}: 비어 있지 않은 한 줄의 값을 입력하세요. 주석/섹션 표기는 사용할 수 없습니다.")

    def to_textbook(self) -> Textbook:
        for name, value in self.rules.items():
            for line in value.splitlines():
                line = line.strip()
                if line:
                    self._validate_line(line, name)
        courses = []
        for draft in self.courses:
            terms = {}
            if not draft.rows:
                raise ValueError(f"{draft.name}: 단어를 한 개 이상 입력하세요.")
            for row, (korean, english) in enumerate(draft.rows, 1):
                korean, english = korean.strip(), english.strip()
                label = f"{draft.name} {row}행"
                self._validate_line(korean, f"{label} 한글명")
                self._validate_line(english, f"{label} 영어명")
                if "=" in korean:
                    raise ValueError(f"{label}: 한글명에는 '='를 사용할 수 없습니다.")
                if korean in terms:
                    raise ValueError(f"{label}: 중복된 한글명 '{korean}'입니다.")
                terms[korean] = english
            courses.append(Course(draft.name, terms))
        return Textbook(courses, **self.rules)


class TextbookRepository:
    """원본 변경 감지와 원자적 파일 교체를 담당합니다."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self._original: bytes | None = None

    def load(self) -> TextbookDocument:
        self._original = self.path.read_bytes() if self.path.exists() else None
        book = (Textbook.parse(self._original.decode("utf-8-sig"))
                if self._original is not None else Textbook([]))
        return TextbookDocument(book)

    def save(self, document: TextbookDocument) -> None:
        book = document.to_textbook()
        sections = [f"[{title}]\n{rules}" for title, rules in (
            ("Common Rules", book.common_rules), ("Whisper Rules", book.whisper_rules),
            ("Translation Rules", book.translation_rules),
        )]
        for course in book.courses:
            terms = "\n".join(f"{k} = {v}" for k, v in course.terminology.items())
            sections.append(f"[Course]\n{course.name}\n\n[Terminology]\n{terms}")
        content = "\n\n".join(sections) + "\n"
        Textbook.parse(content)
        current = self.path.read_bytes() if self.path.exists() else None
        if current != self._original:
            raise ValueError("파일이 다른 프로그램에서 변경되었습니다. 편집 내용을 확인하고 프로그램을 다시 열어주세요.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, suffix=".tmp", delete=False) as output:
                temporary_path = Path(output.name)
                output.write(content.encode("utf-8"))
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        self._original = content.encode("utf-8")
        document.dirty = False
