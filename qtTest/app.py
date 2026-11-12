"""기존 GUI 실행 명령 호환용 진입점."""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subtitle_app.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
