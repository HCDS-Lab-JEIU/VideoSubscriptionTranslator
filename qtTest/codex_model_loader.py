"""Load the Codex picker catalog without blocking Qt's event loop."""

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from codex_models import list_codex_models


class ModelSignals(QObject):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)


class CodexModelLoader(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = ModelSignals()

    def run(self):
        try:
            self.signals.loaded.emit(list_codex_models())
        except (OSError, ValueError, RuntimeError):
            self.signals.failed.emit("모델 목록 조회 실패: Codex 설치·로그인·연결을 확인하고 새로고침하세요.")
