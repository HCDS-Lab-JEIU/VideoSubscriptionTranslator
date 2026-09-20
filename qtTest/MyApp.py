"""영상 파일을 선택하고 재생하는 메인 창."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from qtTest.FileDialog import FileDialog
from qtTest.videoPlayer import QVideoPlayer
from qtTest.textbook_editor.editor import TextbookEditorWindow


class MyApp(QMainWindow):
    STYLESHEET_PATH = Path(__file__).with_name("github_dark_replica.qss")

    def __init__(self) -> None:
        super().__init__()
        self.textbook_window = None
        self._init_ui()
        self._apply_stylesheet()

    def _init_ui(self) -> None:
        self.video_player = QVideoPlayer(self)
        self.video_player.error_occurred.connect(self._show_video_error)
        self.setCentralWidget(self.video_player)

        open_file_action = QAction("Open Video", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file)

        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        file_menu = menu_bar.addMenu("File")
        file_menu.addAction(open_file_action)

        self.textbook_action = QAction("텍스트북 편집기", self)
        self.textbook_action.setShortcut("Ctrl+Shift+T")
        self.textbook_action.triggered.connect(self.open_textbook_editor)
        tools_menu = menu_bar.addMenu("Tools")
        tools_menu.addAction(self.textbook_action)

        self.statusBar().showMessage("Ready")
        self.setWindowTitle("Video Player")
        self.resize(960, 600)

    def _apply_stylesheet(self) -> None:
        try:
            stylesheet = self.STYLESHEET_PATH.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Stylesheet Error", str(exc))
            self.statusBar().showMessage("Failed to load stylesheet")
            return

        self.setStyleSheet(stylesheet)

    def open_file(self) -> None:
        path = FileDialog.select_video_file(self)
        if path is None:
            return

        try:
            self.video_player.load_video(path)
        except (OSError, ValueError) as exc:
            self._show_video_error(str(exc))
            return

        self.setWindowTitle(f"Video Player — {path.name}")
        self.statusBar().showMessage(str(path))

    def _show_video_error(self, message: str) -> None:
        QMessageBox.critical(self, "Video Error", message)
        self.statusBar().showMessage("Failed to open video")

    def open_textbook_editor(self) -> None:
        if self.textbook_window is None:
            self.textbook_window = TextbookEditorWindow(parent=self)
            self.textbook_window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            self.textbook_window.destroyed.connect(self._textbook_closed)
        self.textbook_window.showNormal()
        self.textbook_window.raise_()
        self.textbook_window.activateWindow()

    def _textbook_closed(self):
        self.textbook_window = None

    def closeEvent(self, event):
        if self.textbook_window is not None and not self.textbook_window.close():
            event.ignore()
            return
        super().closeEvent(event)
