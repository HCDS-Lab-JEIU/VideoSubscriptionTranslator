"""Shared frozen entry point for the GUI and console executables."""

from pathlib import Path
import sys


if "--runtime-checks" in sys.argv:
    from runtime_checks import check_runtime
    check_runtime()
    raise SystemExit(0)

if Path(sys.executable).stem.endswith("-CLI"):
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    from subtitle_app.cli import main
    raise SystemExit(main())
else:
    from subtitle_app.ui.app import main

    if "--smoke-test" in sys.argv:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        from subtitle_app.ui.main_window import MyApp

        app = QApplication(sys.argv[:1])
        window = MyApp()
        window.show()
        QTimer.singleShot(1000, app.quit)
        raise SystemExit(app.exec())
    raise SystemExit(main())
