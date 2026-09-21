"""기존 CLI 파이프라인을 화면을 막지 않는 별도 프로세스로 실행합니다."""

import codecs
from pathlib import Path
import sys

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTemporaryDir, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from api_config import load_api_key
from textbook import DEFAULT_TEXTBOOK_PATH, Textbook


class PipelinePanel(QWidget):
    video_requested = pyqtSignal()
    busy_changed = pyqtSignal(bool)
    PROJECT_DIR = Path(__file__).resolve().parents[1]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = None
        self.textbook_path = None
        self.result_folder = None
        self.busy = False
        self._snapshot = None
        self._pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)

        layout = QVBoxLayout(self)
        self.inputs = QWidget(self)
        form = QFormLayout(self.inputs)
        self.video_field = QLineEdit()
        self.video_field.setReadOnly(True)
        self.video_button = QPushButton("영상 선택")
        self.video_button.clicked.connect(self.video_requested)
        form.addRow("입력 영상", self._row(self.video_field, self.video_button))
        self.textbook_field = QLineEdit()
        self.textbook_field.setReadOnly(True)
        self.textbook_button = QPushButton("텍스트북 불러오기")
        self.textbook_button.clicked.connect(self.choose_textbook)
        form.addRow("텍스트북", self._row(self.textbook_field, self.textbook_button))
        self.course_combo = QComboBox()
        self.course_combo.addItem("텍스트북을 불러오세요", None)
        self.course_combo.currentIndexChanged.connect(self._update_ready)
        form.addRow("과목", self.course_combo)
        self.key_field = QLineEdit(str(self.PROJECT_DIR / "secrets" / "openai_api_key.txt"))
        self.key_field.setReadOnly(True)
        key_button = QPushButton("키 파일 선택")
        key_button.clicked.connect(self.choose_key)
        form.addRow("API 키 파일", self._row(self.key_field, key_button))
        self.output_field = QLineEdit(str(self.PROJECT_DIR / "output_runs"))
        self.output_field.setReadOnly(True)
        output_button = QPushButton("저장 위치 선택")
        output_button.clicked.connect(self.choose_output)
        form.addRow("결과 저장 위치", self._row(self.output_field, output_button))
        layout.addWidget(self.inputs)
        layout.addWidget(QLabel("영상 → 한국어 전사 → 영어 번역 → 자막 영상 · 실행 시 유료 API 사용"))
        actions = QHBoxLayout()
        self.run_button = QPushButton("파이프라인 실행")
        self.run_button.clicked.connect(self.start_pipeline)
        self.folder_button = QPushButton("결과 폴더 열기")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_result_folder)
        actions.addWidget(self.run_button)
        actions.addWidget(self.folder_button)
        layout.addLayout(actions)
        self.status = QLabel("영상과 텍스트북의 과목을 선택하세요.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 5)
        self.progress.setValue(0)
        self.progress.setFormat("%v / 5 단계")
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(110)
        layout.addWidget(self.log)
        if DEFAULT_TEXTBOOK_PATH.is_file():
            self.load_textbook(DEFAULT_TEXTBOOK_PATH)
        self._update_ready()

    @staticmethod
    def _row(field, button):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return row

    def set_video(self, path):
        if not self.busy:
            self.video_path = Path(path).resolve()
            self.video_field.setText(str(self.video_path))
            self._update_ready()

    def choose_textbook(self):
        path, _ = QFileDialog.getOpenFileName(self, "텍스트북 불러오기", "", "텍스트북 (*.txt);;모든 파일 (*)")
        if path:
            self.load_textbook(Path(path))

    def load_textbook(self, path):
        if self.busy:
            return
        try:
            book = Textbook.load(path)
        except ValueError as exc:
            self.status.setText(str(exc))
            return  # 기존의 유효한 선택을 유지합니다.
        self.textbook_path = Path(path).resolve()
        self.textbook_field.setText(str(self.textbook_path))
        self.course_combo.clear()
        if len(book.courses) > 1:
            self.course_combo.addItem("과목을 선택하세요", None)
        for course in book.courses:
            self.course_combo.addItem(course.name, course.name)
        self.status.setText(f"텍스트북 로드 완료: {len(book.courses)}개 과목")
        self._update_ready()

    def choose_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "API 키 파일 선택", "", "텍스트 파일 (*.txt);;모든 파일 (*)")
        if path:
            self.key_field.setText(path)

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "결과 저장 위치", self.output_field.text())
        if path:
            self.output_field.setText(path)

    def _update_ready(self):
        self.run_button.setEnabled(not self.busy and self.video_path is not None
                                   and self.textbook_path is not None
                                   and self.course_combo.currentData() is not None)

    def _set_busy(self, busy):
        self.busy = busy
        self.inputs.setEnabled(not busy)
        self.run_button.setText("파이프라인 실행 중…" if busy else "파이프라인 실행")
        self._update_ready()
        self.busy_changed.emit(busy)

    def start_pipeline(self):
        if self.busy:
            return
        try:
            if self.video_path is None or not self.video_path.is_file():
                raise ValueError("존재하는 입력 영상을 선택하세요.")
            if self.video_path.suffix.lower() not in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".wmv", ".ts", ".mts"}:
                raise ValueError("전체 파이프라인에 사용할 영상 파일을 선택하세요.")
            if self.textbook_path is None or self.course_combo.currentData() is None:
                raise ValueError("텍스트북과 과목을 선택하세요.")
            content = self.textbook_path.read_text(encoding="utf-8-sig")
            book = Textbook.parse(content).select_course(self.course_combo.currentData())
            book.translation_prompt()  # 전사 비용을 쓰기 전에 번역 규칙도 검증합니다.
            load_api_key(Path(self.key_field.text()))
            # 실행 도중 편집기에서 저장해도 이 실행의 규칙과 과목은 바뀌지 않습니다.
            self._snapshot = QTemporaryDir()
            if not self._snapshot.isValid():
                raise OSError("실행 설정을 보관할 임시 폴더를 만들 수 없습니다.")
            snapshot = Path(self._snapshot.path()) / "textbook.txt"
            snapshot.write_text(content, encoding="utf-8")
        except (OSError, ValueError, UnicodeError) as exc:
            self._snapshot = None
            self.status.setText(f"실행 준비 실패: {exc}")
            return

        self.result_folder = None
        self.folder_button.setEnabled(False)
        self.log.clear()
        self.progress.setValue(0)
        self._pending = ""
        self._decoder.reset()
        self.status.setText("파이프라인을 시작합니다…")
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUTF8", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self.process.setProcessEnvironment(env)
        self.process.setWorkingDirectory(str(self.PROJECT_DIR))
        self._set_busy(True)
        self.process.start(sys.executable, [
            "-u", str(self.PROJECT_DIR / "__main__.py"), str(self.video_path), "--pipeline",
            "--textbook-file", str(snapshot), "--course", book.course,
            "--api-key-file", self.key_field.text(), "--pipeline-output-dir", self.output_field.text(),
        ])

    def _read_output(self):
        self._consume(self._decoder.decode(bytes(self.process.readAllStandardOutput())))

    def _consume(self, text):
        self._pending += text.replace("\r", "\n")
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            self._handle_line(line)

    def _handle_line(self, line):
        if not line:
            return
        self.log.appendPlainText(line)
        if line.startswith("결과 폴더: "):
            self.result_folder = Path(line.removeprefix("결과 폴더: "))
            self.folder_button.setEnabled(True)
        for stage in range(1, 6):
            if line.startswith(f"[{stage}/5]"):
                self.progress.setValue(stage - 1)
                self.status.setText(line)
        if line.startswith(("전체 파이프라인 완료:", "작업 실패:", "중단 단계:", "자막으로 만들 발화가 없습니다.")):
            self.status.setText(line)

    def _finished(self, exit_code, exit_status):
        self._read_output()
        self._consume(self._decoder.decode(b"", final=True))
        self._handle_line(self._pending)
        self._pending = ""
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self.progress.setValue(5)
            if not self.status.text().startswith("전체 파이프라인 완료:"):
                self.status.setText("파이프라인이 완료되었습니다. 실행 로그와 결과 폴더를 확인하세요.")
        elif not self.status.text().startswith(("작업 실패:", "중단 단계:")):
            self.status.setText("파이프라인이 중단되었습니다. 실행 로그를 확인하세요. 중간 결과는 결과 폴더에 보관됩니다.")
        self._snapshot = None
        self._set_busy(False)

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.status.setText("파이프라인 실행 실패: " + self.process.errorString())
            self._snapshot = None
            self._set_busy(False)

    def open_result_folder(self):
        if self.result_folder is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.result_folder)))
