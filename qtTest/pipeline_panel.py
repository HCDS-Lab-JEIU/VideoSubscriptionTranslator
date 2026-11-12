"""기존 CLI 파이프라인을 화면을 막지 않는 별도 프로세스로 실행합니다."""

import codecs
import json
from pathlib import Path
import sys

from PyQt6.QtCore import QProcess, QProcessEnvironment, QTemporaryDir, QThreadPool, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from api_config import load_api_key
from app_paths import app_directory
from textbook import DEFAULT_TEXTBOOK_PATH, Textbook
from qtTest.codex_model_loader import CodexModelLoader
from pipeline_events import SUBTITLE_READY_PREFIX


class PipelinePanel(QWidget):
    video_requested = pyqtSignal()
    busy_changed = pyqtSignal(bool)
    preview_reset = pyqtSignal()
    subtitles_ready = pyqtSignal(str, str)
    PROJECT_DIR = app_directory()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.video_path = None
        self.textbook_path = None
        self.result_folder = None
        self.busy = False
        self._codex_models = {}
        self._models_loading = False
        self._snapshot = None
        self._pending = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)

        layout = QVBoxLayout(self)
        self.setMinimumWidth(340)
        title = QLabel("인스펙터 · 설정")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.inputs = QWidget(self)
        form = QFormLayout(self.inputs)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setContentsMargins(6, 6, 6, 6)
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
        self.transcription_backend_combo = QComboBox()
        self.transcription_backend_combo.addItem("OpenAI API (기존 방식)", "openai")
        self.transcription_backend_combo.addItem("로컬 Whisper (음성 업로드 없음)", "local")
        form.addRow("전사 방식", self.transcription_backend_combo)
        self.local_model_combo = QComboBox()
        self.local_model_combo.addItem("large-v2 · INT8 · VRAM 약 3–4GB 목표", "large-v2")
        self.local_model_combo.addItem("medium · INT8 · 메모리 절약", "medium")
        self.local_model_combo.addItem("small · INT8 · 속도 우선", "small")
        form.addRow("로컬 모델", self.local_model_combo)
        self.local_device_combo = QComboBox()
        self.local_device_combo.addItem("GPU 우선 / 부족·오류 시 CPU", "auto")
        self.local_device_combo.addItem("CPU 전용 (느림)", "cpu")
        form.addRow("로컬 실행 장치", self.local_device_combo)
        self.transcription_note = QLabel()
        self.transcription_note.setWordWrap(True)
        form.addRow(self.transcription_note)
        self.transcription_backend_combo.currentIndexChanged.connect(self._update_transcription_options)
        self.translation_backend_combo = QComboBox()
        self.translation_backend_combo.addItem("OpenAI API (기존 방식)", "openai")
        self.translation_backend_combo.addItem("Codex CLI (로그인 계정 사용)", "codex")
        form.addRow("번역 방식", self.translation_backend_combo)
        self.codex_model_combo = QComboBox()
        self.codex_model_combo.addItem("Codex 번역을 선택하면 목록을 불러옵니다", None)
        self.codex_refresh_button = QPushButton("목록 새로고침")
        self.codex_refresh_button.clicked.connect(self.refresh_codex_models)
        form.addRow("Codex 모델", self._row(self.codex_model_combo, self.codex_refresh_button))
        self.codex_reasoning_combo = QComboBox()
        form.addRow("추론 수준", self.codex_reasoning_combo)
        self.codex_selection_note = QLabel("모델과 추론 수준을 확인한 뒤 실행합니다.")
        self.codex_selection_note.setWordWrap(True)
        form.addRow(self.codex_selection_note)
        self.codex_model_combo.currentIndexChanged.connect(self._codex_model_changed)
        self.codex_reasoning_combo.currentIndexChanged.connect(self._codex_selection_changed)
        self.translation_note = QLabel()
        self.translation_note.setWordWrap(True)
        form.addRow(self.translation_note)
        self.translation_backend_combo.currentIndexChanged.connect(self._update_translation_options)
        self.key_field = QLineEdit(str(self.PROJECT_DIR / "secrets" / "openai_api_key.txt"))
        self.key_field.setReadOnly(True)
        key_button = QPushButton("키 파일 선택")
        key_button.clicked.connect(self.choose_key)
        self.key_row = self._row(self.key_field, key_button)
        form.addRow("API 키 파일", self.key_row)
        self._update_transcription_options()
        self._update_translation_options()
        self.output_field = QLineEdit(str(self.PROJECT_DIR / "output_runs"))
        self.output_field.setReadOnly(True)
        output_button = QPushButton("저장 위치 선택")
        output_button.clicked.connect(self.choose_output)
        form.addRow("결과 저장 위치", self._row(self.output_field, output_button))
        self.parallel_render_checkbox = QCheckBox("영상 자막 합성 자막 기준 병렬 처리")
        self.parallel_render_checkbox.setToolTip(
            "체크하면 전체 자막을 물리 코어 수에 맞춰 연속 묶음으로 나눠 동시 처리합니다. "
            "CPU·메모리·임시 디스크 사용량이 증가하며, 해제하면 기존 방식으로 처리합니다."
        )
        form.addRow("렌더링", self.parallel_render_checkbox)
        for combo in self.inputs.findChildren(QComboBox):
            combo.setMinimumContentsLength(12)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.input_scroll = QScrollArea()
        self.input_scroll.setWidgetResizable(True)
        self.input_scroll.setMinimumHeight(260)
        self.input_scroll.setWidget(self.inputs)
        layout.addWidget(self.input_scroll, 1)
        actions = QHBoxLayout()
        self.run_button = QPushButton("파이프라인 실행")
        self.run_button.clicked.connect(self.start_pipeline)
        self.folder_button = QPushButton("결과 폴더 열기")
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_result_folder)
        actions.addWidget(self.run_button)
        actions.addWidget(self.folder_button)
        layout.addLayout(actions)
        # The main window moves this widget below the preview; controls stay here.
        self.console = QWidget(self)
        console_layout = QVBoxLayout(self.console)
        console_layout.setContentsMargins(12, 8, 12, 8)
        console_layout.setSpacing(6)
        console_title = QLabel("진행 과정 콘솔")
        console_title.setObjectName("sectionTitle")
        console_layout.addWidget(console_title)
        self.status = QLabel("영상과 텍스트북의 과목을 선택하세요.")
        self.status.setWordWrap(True)
        console_layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 5)
        self.progress.setValue(0)
        self.progress.setFormat("%v / 5 단계")
        console_layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(70)
        console_layout.addWidget(self.log, 1)
        layout.addWidget(self.console)
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
                                   and self.course_combo.currentData() is not None
                                   and (self.translation_backend_combo.currentData() != "codex"
                                        or (not self._models_loading and self.codex_model_combo.currentData() is not None
                                            and self.codex_reasoning_combo.currentData() is not None)))

    def _update_transcription_options(self):
        local = self.transcription_backend_combo.currentData() == "local"
        self.local_model_combo.setEnabled(local)
        self.local_device_combo.setEnabled(local)
        self.transcription_note.setText(
            "로컬 전사: 첫 실행에 모델 다운로드가 필요합니다. INT8·순차 처리로 VRAM을 절약하며 "
            "3–4GB는 목표치입니다. GPU 여유 4GiB 미만이면 CPU로 실행합니다."
            if local else "기존 OpenAI API 전사와 구간 복구를 사용합니다. 전사에 API 요금이 발생합니다."
        )
        self._update_translation_options()

    def _update_translation_options(self):
        codex = self.translation_backend_combo.currentData() == "codex"
        self.codex_model_combo.setEnabled(codex and not self._models_loading)
        self.codex_reasoning_combo.setEnabled(codex and not self._models_loading)
        self.codex_refresh_button.setEnabled(codex and not self._models_loading)
        self.key_row.setEnabled(not codex or self.transcription_backend_combo.currentData() == "openai")
        self.translation_note.setText(
            "Codex CLI 설치와 로그인이 필요합니다. 자막·용어장을 온라인으로 전송하며 "
            "로그인 계정의 사용 한도를 따릅니다. 로컬 전사와 함께 쓰면 API 키 파일이 필요 없습니다."
            if codex else "영어 번역에 인터넷과 API 키가 필요하며 OpenAI API 요금이 발생합니다."
        )
        if codex and not self._codex_models and not self._models_loading:
            self.refresh_codex_models()
        if hasattr(self, "run_button"):
            self._update_ready()

    def refresh_codex_models(self):
        if self.busy or self._models_loading:
            return
        self._models_loading = True
        self.codex_selection_note.setText("Codex에서 사용 가능한 모델과 추론 수준을 불러오는 중…")
        self._update_translation_options()
        self._model_loader = CodexModelLoader()
        self._model_loader.signals.loaded.connect(self._apply_codex_models)
        self._model_loader.signals.failed.connect(self._codex_models_failed)
        QThreadPool.globalInstance().start(self._model_loader)

    def _apply_codex_models(self, models):
        old_model = self.codex_model_combo.currentData()
        old_effort = self.codex_reasoning_combo.currentData()
        self._codex_models = {model["model"]: model for model in models}
        self.codex_model_combo.blockSignals(True)
        self.codex_model_combo.clear()
        for model in models:
            label = f"{model['displayName']} ({model['model']})"
            if model["isDefault"]:
                label += " · Codex 기본 선택"
            self.codex_model_combo.addItem(label, model["model"])
        selected = old_model if old_model in self._codex_models else next(
            (model["model"] for model in models if model["isDefault"]), models[0]["model"])
        self.codex_model_combo.setCurrentIndex(self.codex_model_combo.findData(selected))
        self.codex_model_combo.blockSignals(False)
        self._models_loading = False
        self._codex_model_changed()
        if selected == old_model and self.codex_reasoning_combo.findData(old_effort) >= 0:
            self.codex_reasoning_combo.setCurrentIndex(self.codex_reasoning_combo.findData(old_effort))
        self._update_translation_options()

    def _codex_models_failed(self, message):
        self._models_loading = False
        codex = self.translation_backend_combo.currentData() == "codex"
        self.codex_refresh_button.setEnabled(codex)
        self.codex_model_combo.setEnabled(codex and bool(self._codex_models))
        self.codex_reasoning_combo.setEnabled(codex and bool(self._codex_models))
        self.codex_selection_note.setText(message + (" 이전에 불러온 선택은 유지합니다." if self._codex_models else ""))
        self._update_ready()

    def _codex_model_changed(self):
        self.codex_reasoning_combo.blockSignals(True)
        self.codex_reasoning_combo.clear()
        model = self._codex_models.get(self.codex_model_combo.currentData())
        names = {"none": "없음", "minimal": "최소", "low": "낮음", "medium": "보통",
                 "high": "높음", "xhigh": "매우 높음", "max": "최대", "ultra": "울트라"}
        if model:
            for option in model["supportedReasoningEfforts"]:
                effort = option["reasoningEffort"]
                label = f"{names.get(effort, effort)} ({effort})"
                if effort == model["defaultReasoningEffort"]:
                    label += " · 모델 기본 수준"
                self.codex_reasoning_combo.addItem(label, effort)
            self.codex_reasoning_combo.setCurrentIndex(
                self.codex_reasoning_combo.findData(model["defaultReasoningEffort"]))
        self.codex_reasoning_combo.blockSignals(False)
        self._codex_selection_changed()

    def _codex_selection_changed(self):
        model, effort = self.codex_model_combo.currentData(), self.codex_reasoning_combo.currentData()
        if model and effort:
            self.codex_selection_note.setText(
                f"실행 설정: {model} / 추론 {effort}. 높은 수준은 응답 시간과 사용량이 늘어날 수 있습니다.")
        if hasattr(self, "run_button"):
            self._update_ready()

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
            if self.translation_backend_combo.currentData() == "codex" and (
                    self._models_loading or self.codex_model_combo.currentData() is None
                    or self.codex_reasoning_combo.currentData() is None):
                raise ValueError("Codex 모델 목록을 불러온 뒤 모델과 추론 수준을 선택하세요.")
            if (self.transcription_backend_combo.currentData() == "openai"
                    or self.translation_backend_combo.currentData() == "openai"):
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
        self.preview_reset.emit()
        program = sys.executable
        prefix = ["-u", str(self.PROJECT_DIR / "__main__.py")]
        if getattr(sys, "frozen", False):
            program = str(self.PROJECT_DIR / "VideoSubtitleTranslator-CLI.exe")
            prefix = []
        if self.parallel_render_checkbox.isChecked():
            prefix += ["--parallel-render"]
        if self.transcription_backend_combo.currentData() == "local":
            prefix += ["--transcription-backend", "local", "--local-model", self.local_model_combo.currentData(),
                       "--local-device", self.local_device_combo.currentData()]
        if self.translation_backend_combo.currentData() == "codex":
            prefix += ["--translation-backend", "codex", "--codex-model", self.codex_model_combo.currentData(),
                       "--codex-reasoning", self.codex_reasoning_combo.currentData()]
        self.process.start(program, prefix + [
            str(self.video_path), "--pipeline",
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
        if line.startswith(SUBTITLE_READY_PREFIX):
            try:
                event = json.loads(line.removeprefix(SUBTITLE_READY_PREFIX))
                if not isinstance(event, dict) or not all(isinstance(event.get(key), str) for key in ("video", "srt")):
                    raise ValueError("잘못된 자막 알림")
                video, srt = Path(event["video"]).resolve(), Path(event["srt"]).resolve()
                if (not self.busy or video != self.video_path or self.result_folder is None
                        or not srt.is_relative_to(self.result_folder.resolve()) or srt.suffix.lower() != ".srt"):
                    raise ValueError("현재 실행과 일치하지 않는 자막 알림")
                self.subtitles_ready.emit(str(video), str(srt))
            except (OSError, ValueError) as exc:
                self.log.appendPlainText(f"미리보기 자막 알림을 읽지 못했습니다: {exc}")
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
