"""Shared frozen entry point for the GUI and console executables."""

from pathlib import Path
import runpy
import sys


if Path(sys.executable).stem.endswith("-CLI"):
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    runpy.run_path(str(Path(__file__).with_name("cli.py")), run_name="__main__")
else:
    from qtTest.app import main

    if "--smoke-test" in sys.argv:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        from qtTest.MyApp import MyApp

        app = QApplication(sys.argv[:1])
        window = MyApp()
        window.show()
        QTimer.singleShot(1000, app.quit)
        raise SystemExit(app.exec())
    raise SystemExit(main())
