"""텍스트북의 공통/단계별 규칙과 과목별 단어장을 읽습니다."""

from dataclasses import dataclass, field
from pathlib import Path
from subtitle_app.common.app_paths import app_directory


DEFAULT_TEXTBOOK_PATH = app_directory() / "secrets" / "textbook.txt"


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
        self._single_course()
        contexts = [f"{course.name} 강의. " + ", ".join(course.terminology) + "."
                    for course in self.courses]
        # 전사 전용 힌트를 마지막에 두어 긴 단어장에서도 우선 보존합니다.
        return "\n\n".join(part for part in [self.common_rules, *contexts, self.whisper_rules]
                           if part.strip())

    def accurate_transcription_prompt(self) -> str:
        course = self._single_course()
        terms = ", ".join(f"{ko} ({en})" for ko, en in course.terminology.items())
        return "\n\n".join(part for part in (
            self.common_rules, f"과목: {course.name}\n전문 용어 표기 참고: {terms}", self.whisper_rules,
            "현재 음성 구간에서 실제로 들리는 발화만 한국어로 전사하세요. "
            "영어 전문 용어와 코드 식별자는 실제 표기를 보존하세요. "
            "들리는 내용의 의미와 순서를 유지하며 띄어쓰기와 문장부호를 자연스럽게 정리하세요. "
            "구간이 문장 중간에서 끊겨도 들리지 않은 단어, 설명, 수치나 문장 끝을 추측해 채우지 마세요. "
            "잡음이나 무음에 내용을 만들지 말고, 알아들을 수 없는 부분은 생략하세요. "
            "과목명, 용어 목록, 지시문을 발화로 복사하거나 해설하지 마세요. "
            "들리는 말이 없으면 빈 텍스트를 반환하세요."
        ) if part.strip())

    def translation_prompt(self) -> str:
        self._single_course()
        if not self.translation_rules.strip():
            raise ValueError("텍스트북에 [Translation Rules] 번역 지시문을 입력하세요.")
        contexts = []
        for course in self.courses:
            terms = "\n".join(f"{korean} = {english}" for korean, english in course.terminology.items())
            contexts.append(f"Course: {course.name}\n\nTerminology:\n{terms}")
        return "\n\n".join(part for part in [self.common_rules, self.translation_rules, *contexts]
                           if part.strip())

    def select_course(self, selector: str | None = None) -> "Textbook":
        """번호 또는 유일하게 일치하는 이름으로 한 과목을 선택합니다."""
        choices = "\n".join(f"{i}. {c.name}" for i, c in enumerate(self.courses, 1))
        if selector is None:
            matches = self.courses if len(self.courses) == 1 else []
        else:
            value = selector.strip().casefold()
            if value.isdecimal():
                index = int(value) - 1
                matches = self.courses[index:index + 1] if 0 <= index < len(self.courses) else []
            else:
                matches = [c for c in self.courses if c.name.casefold() == value]
                if not matches and value:
                    matches = [c for c in self.courses if value in c.name.casefold()]
        if len(matches) != 1:
            raise ValueError("--course에 과목 번호 또는 유일하게 일치하는 과목명을 지정하세요.\n" + choices)
        selected = matches[0]
        return Textbook([Course(selected.name, dict(selected.terminology))],
                        self.common_rules, self.whisper_rules, self.translation_rules)
