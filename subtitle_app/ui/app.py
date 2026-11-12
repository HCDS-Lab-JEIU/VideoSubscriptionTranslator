"""PyQt6 애플리케이션 실행 진입점."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt6.QtWidgets import QApplication

from subtitle_app.ui.main_window import MyApp

def main() -> int:
    app = QApplication(sys.argv)
    window = MyApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
