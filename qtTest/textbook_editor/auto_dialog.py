"""Multi-PPT terminology generation and review without blocking the editor."""

from pathlib import Path
from threading import Event

from PyQt6.QtCore import Qt, QThread, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_paths import app_directory
from textbook_auto import GenerationCancelled, generate_terms, validate_term
from qtTest.codex_model_loader import CodexModelLoader
from .data import TextbookDocument


class PresentationList(QListWidget):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        self.files_dropped.emit([url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()])
        event.acceptProposedAction()


class GenerationWorker(QThread):
    progress = pyqtSignal(str)
    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.options = options
        self.cancel = Event()

    def run(self):
        try:
            result = generate_terms(**self.options, cancel=self.cancel, progress=self.progress.emit)
            if self.cancel.is_set():
                raise GenerationCancelled("생성을 취소했습니다. 편집 내용은 변경하지 않았습니다.")
            self.succeeded.emit(result)
        except (OSError, ValueError, RuntimeError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit("단어장을 생성하지 못했습니다. PPT 파일과 생성 서비스 연결을 확인하세요.")


class AutoTextbookDialog(QDialog):
    def __init__(self, document, course_index=-1, parent=None):
        super().__init__(parent)
        self.document = document
        self.selected_terms = []
        self.target_course = ""
        self.worker = None
        self.models = {}
        self.loading_models = False
        self.setWindowTitle("Auto · PPT에서 단어장 생성")
        self.resize(920, 850)
        layout = QVBoxLayout(self)
        info = QLabel("PPT 파일을 아래로 드래그하거나 Open으로 여러 파일을 선택하세요.\n"
                      "슬라이드의 텍스트·표를 읽습니다. 이미지 속 글자·발표자 노트는 제외하며, 구형 .ppt는 PowerPoint 설치가 필요합니다.")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.files = PresentationList()
        self.files.setMinimumHeight(90)
        self.files.setMaximumHeight(140)
        self.files.files_dropped.connect(self.add_files)
        layout.addWidget(self.files)
        files_actions = QHBoxLayout()
        self.open_button = QPushButton("Open · PPT 파일 추가")
        self.open_button.clicked.connect(self.open_files)
        self.remove_button = QPushButton("선택 파일 제거")
        self.remove_button.clicked.connect(self.remove_files)
        files_actions.addWidget(self.open_button)
        files_actions.addWidget(self.remove_button)
        files_actions.addStretch()
        layout.addLayout(files_actions)

        self.settings = QWidget()
        form = QFormLayout(self.settings)
        form.setContentsMargins(0, 0, 0, 0)
        self.course_combo = QComboBox()
        self.course_combo.setEditable(True)
        self.course_combo.addItems([course.name for course in document.courses])
        self.course_combo.setCurrentIndex(course_index)
        self.course_combo.lineEdit().setPlaceholderText("기존 과목을 선택하거나 새 과목명을 입력하세요")
        self.course_combo.currentTextChanged.connect(self._invalidate_results)
        form.addRow("추가할 과목", self.course_combo)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("OpenAI API · gpt-4.1", "openai")
        self.backend_combo.addItem("Codex CLI · 로그인 계정", "codex")
        form.addRow("생성 방식", self.backend_combo)
        self.key_field = QLineEdit(str(app_directory() / "secrets" / "openai_api_key.txt"))
        key_button = QPushButton("키 파일 선택")
        key_button.clicked.connect(self.choose_key)
        self.key_row = self._row(self.key_field, key_button)
        form.addRow("API 키 파일", self.key_row)
        self.model_combo = QComboBox()
        self.model_combo.addItem("Codex 선택 시 모델 목록을 불러옵니다", None)
        self.refresh_button = QPushButton("목록 새로고침")
        self.refresh_button.clicked.connect(self.refresh_models)
        form.addRow("Codex 모델", self._row(self.model_combo, self.refresh_button))
        self.reasoning_combo = QComboBox()
        form.addRow("추론 수준", self.reasoning_combo)
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        self.note = QLabel()
        self.note.setWordWrap(True)
        form.addRow(self.note)
        layout.addWidget(self.settings)
        self.backend_combo.currentIndexChanged.connect(self._backend_changed)
        self.generate_button = QPushButton("단어장 생성")
        self.generate_button.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_button)
        self.status = QLabel("생성 후 필요한 단어를 선택·수정하고 편집기에 추가하세요. 기존 규칙과 단어는 유지됩니다.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["추가", "한글명", "영어명", "출처 / 상태"])
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((45, 200, 220)):
            self.table.setColumnWidth(column, width)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        layout.addWidget(self.log)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("선택 단어를 편집기에 추가")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_selection)
        self.close_button = QPushButton("닫기")
        self.close_button.clicked.connect(self.reject)
        actions.addStretch()
        actions.addWidget(self.apply_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)
        self._backend_changed()

    @staticmethod
    def _row(field, button):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(field, 1)
        layout.addWidget(button)
        return widget

    @property
    def busy(self):
        return self.worker is not None

    def add_files(self, paths):
        if self.busy:
            return
        seen = {self.files.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.files.count())}
        rejected = []
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            if not path.is_file() or path.suffix.lower() not in {".ppt", ".pptx"}:
                rejected.append(path.name)
                continue
            if str(path) in seen:
                continue
            seen.add(str(path))
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.files.addItem(item)
        self._invalidate_results()
        self.status.setText(f"PPT {self.files.count()}개 선택" + (" · 제외: " + ", ".join(rejected) if rejected else ""))

    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "PPT 파일 추가", "", "PowerPoint (*.pptx *.ppt)")
        if paths:
            self.add_files(paths)

    def remove_files(self):
        for item in self.files.selectedItems():
            self.files.takeItem(self.files.row(item))
        self._invalidate_results()

    def choose_key(self):
        path, _ = QFileDialog.getOpenFileName(self, "API 키 파일", "", "텍스트 파일 (*.txt)")
        if path:
            self.key_field.setText(path)

    def _invalidate_results(self, *_):
        if hasattr(self, "table"):
            self.table.setRowCount(0)
            self.apply_button.setEnabled(False)

    def _backend_changed(self):
        codex = self.backend_combo.currentData() == "codex"
        self.key_row.setEnabled(not codex)
        self.model_combo.setEnabled(codex and not self.loading_models)
        self.reasoning_combo.setEnabled(codex and not self.loading_models)
        self.refresh_button.setEnabled(codex and not self.loading_models)
        self.note.setText("PPT 추출 텍스트와 현재 규칙·선택 과목의 단어장을 전송합니다. " + (
            "Codex 로그인 계정의 사용 한도가 적용됩니다. API 키는 필요 없습니다."
            if codex else "OpenAI API 요금이 발생합니다."))
        if codex and not self.models and not self.loading_models:
            self.refresh_models()

    def refresh_models(self):
        if self.loading_models or self.busy:
            return
        self.loading_models = True
        self._backend_changed()
        self.status.setText("Codex 모델 목록을 불러오는 중…")
        self.loader = CodexModelLoader()
        self.loader.signals.loaded.connect(self._models_loaded)
        self.loader.signals.failed.connect(self._models_failed)
        QThreadPool.globalInstance().start(self.loader)

    def _models_loaded(self, models):
        old_model, old_effort = self.model_combo.currentData(), self.reasoning_combo.currentData()
        self.models = {model["model"]: model for model in models}
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model in models:
            self.model_combo.addItem(model["model"] + (" · Codex 기본 선택" if model["isDefault"] else ""), model["model"])
        selected = old_model if old_model in self.models else next(
            (model["model"] for model in models if model["isDefault"]), models[0]["model"])
        self.model_combo.setCurrentIndex(self.model_combo.findData(selected))
        self.model_combo.blockSignals(False)
        self.loading_models = False
        self._model_changed()
        if selected == old_model and self.reasoning_combo.findData(old_effort) >= 0:
            self.reasoning_combo.setCurrentIndex(self.reasoning_combo.findData(old_effort))
        self._backend_changed()
        self.status.setText("Codex 모델과 추론 수준을 선택하세요.")

    def _models_failed(self, message):
        self.loading_models = False
        codex = self.backend_combo.currentData() == "codex"
        self.model_combo.setEnabled(codex and bool(self.models))
        self.reasoning_combo.setEnabled(codex and bool(self.models))
        self.refresh_button.setEnabled(codex)
        self.status.setText(message)

    def _model_changed(self):
        self.reasoning_combo.clear()
        model = self.models.get(self.model_combo.currentData())
        if model:
            for option in model["supportedReasoningEfforts"]:
                effort = option["reasoningEffort"]
                self.reasoning_combo.addItem(effort + (" · 모델 기본 수준" if effort == model["defaultReasoningEffort"] else ""), effort)
            self.reasoning_combo.setCurrentIndex(self.reasoning_combo.findData(model["defaultReasoningEffort"]))

    def _existing_terms(self, course):
        return {ko.strip(): en.strip() for draft in self.document.courses if draft.name.casefold() == course.casefold()
                for ko, en in draft.rows if ko.strip() and en.strip()}

    def start_generation(self):
        if self.busy:
            return
        try:
            course = self.course_combo.currentText().strip()
            TextbookDocument._validate_line(course, "과목명")
            if not self.files.count():
                raise ValueError("PPT 파일을 추가하세요.")
            codex = self.backend_combo.currentData() == "codex"
            if codex and (self.loading_models or not self.model_combo.currentData() or not self.reasoning_combo.currentData()):
                raise ValueError("Codex 모델 목록을 불러온 뒤 모델과 추론 수준을 선택하세요.")
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.target_course = course
        self._invalidate_results()
        self.log.clear()
        self.status.setText("PPT를 읽고 단어장을 생성합니다…")
        options = dict(paths=[self.files.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.files.count())],
                       course=course, rules=dict(self.document.rules), existing=self._existing_terms(course),
                       backend=self.backend_combo.currentData(), api_key_path=self.key_field.text(),
                       model=self.model_combo.currentData(), reasoning=self.reasoning_combo.currentData())
        self.worker = GenerationWorker(options, self)
        self.worker.progress.connect(self._progress)
        self.worker.succeeded.connect(self._show_candidates)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(self._finished)
        self._set_running(True)
        self.worker.start()

    def _set_running(self, running):
        for widget in (self.files, self.open_button, self.remove_button, self.settings, self.generate_button, self.table):
            widget.setEnabled(not running)
        self.close_button.setText("생성 취소" if running else "닫기")
        self.close_button.setEnabled(True)

    def _progress(self, message):
        self.status.setText(message)
        self.log.appendPlainText(message)

    def _show_candidates(self, candidates):
        if self.worker and self.worker.cancel.is_set():
            self._failed("생성을 취소했습니다. 편집 내용은 변경하지 않았습니다.")
            return
        existing, seen = self._existing_terms(self.target_course), set()
        self.table.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            ko, en = candidate.korean, candidate.english
            state = ("기존 단어" if existing.get(ko) == en else f"충돌 · 기존: {existing[ko]}") if ko in existing else (
                "중복 후보 · 하나만 선택하세요" if ko in seen else "새 단어")
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(Qt.CheckState.Checked if ko not in existing and ko not in seen else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, check)
            self.table.setItem(row, 1, QTableWidgetItem(ko))
            self.table.setItem(row, 2, QTableWidgetItem(en))
            source = QTableWidgetItem(state + " · " + candidate.sources)
            source.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            source.setToolTip(source.text())
            self.table.setItem(row, 3, source)
            seen.add(ko)
        self.status.setText(f"후보 {len(candidates)}개 생성. 필요한 단어를 선택·수정한 뒤 추가하세요. 기존 단어는 덮어쓰지 않습니다.")

    def _failed(self, message):
        self.status.setText(message)
        self.log.appendPlainText(message)

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker.cancel.is_set():
            self._invalidate_results()
            self.status.setText("생성을 취소했습니다. 편집 내용은 변경하지 않았습니다.")
        worker.deleteLater()
        self._set_running(False)
        self.apply_button.setEnabled(self.table.rowCount() > 0)

    def apply_selection(self):
        if self.busy:
            return
        self.apply_button.setFocus()  # Commit any currently edited table cell.
        selected = {}
        existing = self._existing_terms(self.target_course)
        try:
            for row in range(self.table.rowCount()):
                if self.table.item(row, 0).checkState() != Qt.CheckState.Checked:
                    continue
                ko, en = validate_term(self.table.item(row, 1).text(), self.table.item(row, 2).text())
                if ko in existing:
                    raise ValueError(f"'{ko}'은 이미 있는 단어입니다. 선택을 해제하거나 한글명을 수정하세요.")
                if ko in selected and selected[ko] != en:
                    raise ValueError(f"'{ko}'의 영어명이 서로 다릅니다. 후보 하나만 선택하세요.")
                selected[ko] = en
            if not selected:
                raise ValueError("추가할 새 단어를 선택하세요.")
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.selected_terms = list(selected.items())
        self.accept()

    def reject(self):
        if self.busy:
            self.worker.cancel.set()
            self.status.setText("취소 요청됨: 현재 파일 처리·요청이 끝나면 중단합니다 (최대 약 3분).")
            self.close_button.setEnabled(False)
            return
        super().reject()

    def closeEvent(self, event):
        if self.busy:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
