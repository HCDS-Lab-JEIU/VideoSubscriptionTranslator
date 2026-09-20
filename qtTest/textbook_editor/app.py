"""텍스트북 편집기의 독립 실행 진입점."""

import argparse
from pathlib import Path
import sys

# 파일 경로 직접 실행도 프로젝트의 공통 모듈을 찾을 수 있게 합니다.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication, QMessageBox

from qtTest.textbook_editor.data import TextbookRepository
from qtTest.textbook_editor.editor import TextbookEditorWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="과목별 단어장 편집기")
    parser.add_argument("--textbook-file", type=Path, help="시작할 때 열 파일 (앱의 Open으로도 선택 가능)")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    try:
        window = TextbookEditorWindow(TextbookRepository(args.textbook_file) if args.textbook_file else None)
    except (OSError, ValueError) as exc:
        QMessageBox.critical(None, "텍스트북 열기 실패", str(exc))
        window = TextbookEditorWindow()
    stylesheet = Path(__file__).resolve().parents[1] / "github_dark_replica.qss"
    if stylesheet.is_file():
        window.setStyleSheet(stylesheet.read_text(encoding="utf-8"))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
