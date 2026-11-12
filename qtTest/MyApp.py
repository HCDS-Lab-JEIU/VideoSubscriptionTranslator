"""영상 파일을 선택하고 재생하는 메인 창."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QSplitter

from qtTest.FileDialog import FileDialog
from qtTest.videoPlayer import QVideoPlayer
from qtTest.textbook_editor.editor import TextbookEditorWindow
from qtTest.pipeline_panel import PipelinePanel


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
        self.pipeline_panel = PipelinePanel(self)
        self.pipeline_panel.video_requested.connect(self.open_file)
        self.pipeline_panel.preview_reset.connect(self.video_player.clear_subtitles)
        self.pipeline_panel.subtitles_ready.connect(self._preview_subtitles)
        self.preview_splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(6)
        self.preview_splitter.addWidget(self.video_player)
        self.preview_splitter.addWidget(self.pipeline_panel.console)
        self.preview_splitter.setStretchFactor(0, 1)
        self.preview_splitter.setStretchFactor(1, 0)
        self.preview_splitter.setSizes([640, 210])

        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(6)
        self.workspace_splitter.addWidget(self.preview_splitter)
        self.workspace_splitter.addWidget(self.pipeline_panel)
        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 0)
        self.workspace_splitter.setSizes([940, 380])
        self.setCentralWidget(self.workspace_splitter)

        open_file_action = QAction("Open Video", self)
        open_file_action.setShortcut("Ctrl+O")
        open_file_action.triggered.connect(self.open_file)
        self.pipeline_panel.busy_changed.connect(lambda busy: open_file_action.setEnabled(not busy))

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
        self.resize(1320, 880)

    def _apply_stylesheet(self) -> None:
        try:
            stylesheet = self.STYLESHEET_PATH.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Stylesheet Error", str(exc))
            self.statusBar().showMessage("Failed to load stylesheet")
            return

        self.setStyleSheet(stylesheet)

    def open_file(self) -> None:
        if self.pipeline_panel.busy:
            return
        path = FileDialog.select_video_file(self)
        if path is None:
            return

        try:
            self.video_player.load_video(path)
        except (OSError, ValueError) as exc:
            self._show_video_error(str(exc))
            return

        self.setWindowTitle(f"Video Player — {path.name}")
        self.pipeline_panel.set_video(path)
        self.statusBar().showMessage(str(path))

    def _show_video_error(self, message: str) -> None:
        QMessageBox.critical(self, "Video Error", message)
        self.statusBar().showMessage("Failed to open video")

    def _preview_subtitles(self, video_path, srt_path):
        try:
            if self.video_player.load_subtitles(video_path, srt_path):
                message = "미리보기 자막을 불러왔습니다. 인코딩 중에도 재생·탐색할 수 있습니다."
                self.statusBar().showMessage(message)
                self.pipeline_panel.log.appendPlainText(message)
        except (OSError, ValueError) as exc:
            message = f"미리보기 자막 로드 실패 (인코딩은 계속됩니다): {exc}"
            self.statusBar().showMessage(message)
            self.pipeline_panel.log.appendPlainText(message)

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
        if self.pipeline_panel.busy:
            self.statusBar().showMessage("파이프라인 실행 중입니다. 작업이 끝난 뒤 창을 닫아주세요.")
            event.ignore()
            return
        if self.textbook_window is not None and not self.textbook_window.close():
            event.ignore()
            return
        super().closeEvent(event)
