"""기존 텍스트북 편집기 파일 실행 경로 호환용 진입점."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from subtitle_app.ui.textbook_editor.app import main

if __name__ == "__main__":
    raise SystemExit(main())
