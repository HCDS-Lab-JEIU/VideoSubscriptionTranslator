"""텍스트북의 공통/단계별 규칙과 과목별 단어장을 읽습니다."""

from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_TEXTBOOK_PATH = Path(__file__).resolve().parent / "secrets" / "textbook.txt"


@dataclass
class Course:
    name: str
    terminology: dict[str, str] = field(default_factory=dict)


@dataclass
class Textbook:
    courses: list[Course]
    common_rules: str = ""
    whisper_rules: str = ""
    translation_rules: str = ""

    @property
    def course(self) -> str:
        """기존 단일 과목 접근을 지원합니다."""
        return self._single_course().name

    @property
    def terminology(self) -> dict[str, str]:
        return self._single_course().terminology

    def _single_course(self) -> Course:
        if len(self.courses) != 1:
            raise ValueError("여러 과목의 단어장은 courses에서 과목별로 확인하세요.")
        return self.courses[0]

    @property
    def translation_instructions(self) -> str:
        return self.translation_rules

    @classmethod
    def load(cls, file_path: str | Path) -> "Textbook":
        path = Path(file_path).expanduser().resolve()
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            raise ValueError(f"텍스트북을 읽을 수 없습니다. UTF-8 파일과 경로를 확인하세요: {path}") from None
        return cls.parse(content)

    @classmethod
    def parse(cls, content: str) -> "Textbook":
        """파일 접근 없이 텍스트북 형식을 검증하고 파싱합니다."""
        rules: dict[str, list[str]] = {
            "common rules": [], "whisper rules": [], "translation rules": [],
        }
        courses: list[Course] = []
        seen_rules: set[str] = set()
        section = None
        for number, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                if section == "translation instructions":
                    section = "translation rules"
                if section in rules:
                    if section in seen_rules:
                        raise ValueError(f"텍스트북 {number}행: [{section}] 규칙 항목이 중복되었습니다.")
                    seen_rules.add(section)
                elif section == "course":
                    courses.append(Course(""))
                elif section == "terminology":
                    if not courses or not courses[-1].name:
                        raise ValueError(f"텍스트북 {number}행: [Terminology] 앞에 [Course]와 과목명이 필요합니다.")
                else:
                    raise ValueError(f"텍스트북 {number}행의 항목 이름을 확인하세요: [{section}]")
            elif section in rules:
                rules[section].append(line)
            elif section == "course":
                course = courses[-1]
                course.name = f"{course.name} {line}".strip()
            elif section == "terminology":
                korean, separator, english = line.partition("=")
                if not separator or not korean.strip() or not english.strip():
                    raise ValueError(f"텍스트북 {number}행: [Terminology]는 '한국어 용어 = English term' 형식이어야 합니다.")
                terms = courses[-1].terminology
                if korean.strip() in terms:
                    raise ValueError(f"텍스트북 {number}행: '{courses[-1].name}'에 중복된 한국어 용어가 있습니다.")
                terms[korean.strip()] = english.strip()
            else:
                raise ValueError(f"텍스트북 {number}행 앞에 규칙 또는 [Course] 항목이 필요합니다.")

        if not courses or any(not course.name or not course.terminology for course in courses):
            raise ValueError("텍스트북의 각 과목에 [Course]와 한 개 이상의 [Terminology] 용어가 필요합니다.")
        names = [course.name.casefold() for course in courses]
        if len(names) != len(set(names)):
            raise ValueError("텍스트북에 중복된 과목명이 있습니다.")
        return cls(
            courses=courses,
            common_rules="\n".join(rules["common rules"]),
            whisper_rules="\n".join(rules["whisper rules"]),
            translation_rules="\n".join(rules["translation rules"]),
        )

    def transcription_prompt(self) -> str:
        contexts = [f"{course.name} 강의. " + ", ".join(course.terminology) + "."
                    for course in self.courses]
        return "\n\n".join(part for part in [self.common_rules, self.whisper_rules, *contexts]
                           if part.strip())

    def translation_prompt(self) -> str:
        if not self.translation_rules.strip():
            raise ValueError("텍스트북에 [Translation Rules] 번역 지시문을 입력하세요.")
        contexts = []
        for course in self.courses:
            terms = "\n".join(f"{korean} = {english}" for korean, english in course.terminology.items())
            contexts.append(f"Course: {course.name}\n\nTerminology:\n{terms}")
        return "\n\n".join(part for part in [self.common_rules, self.translation_rules, *contexts]
                           if part.strip())
