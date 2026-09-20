"""기존 실행 경로 호환용 진입점. 구현은 textbook_editor 패키지에 있습니다."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qtTest.textbook_editor.app import main

if __name__ == "__main__":
    raise SystemExit(main())
