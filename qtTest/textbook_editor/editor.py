"""재사용 가능한 단어장 편집 위젯과 독립 실행 창."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QSplitter,
    QTableView, QVBoxLayout, QWidget,
)

from textbook import Textbook
from .data import TextbookDocument, TextbookRepository
from .model import TerminologyTableModel


class TextbookEditor(QWidget):
    def __init__(self, repository: TextbookRepository | None = None, parent=None):
        super().__init__(parent)
        self.repository = repository
        self.document = repository.load() if repository else TextbookDocument(Textbook([]))
        self.model = TerminologyTableModel(self.document, self)

        self.open_button = QPushButton("Open")
        self.path_display = QLineEdit(str(repository.path) if repository else "")
        self.path_display.setReadOnly(True)
        self.path_display.setPlaceholderText("텍스트북 파일을 열거나 새 내용을 작성하세요.")
        self.save_button = QPushButton("Save")
        file_toolbar = QHBoxLayout()
        file_toolbar.addWidget(self.open_button)
        file_toolbar.addWidget(self.path_display, 1)
        file_toolbar.addWidget(self.save_button)

        self.sections = QSplitter(Qt.Orientation.Vertical)
        self.rule_editors = {}
        for name, title in (("common_rules", "공통 룰"), ("whisper_rules", "Whisper 룰"),
                            ("translation_rules", "Translation 룰")):
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            editor = QPlainTextEdit()
            editor.setMinimumHeight(30)
            editor.setPlainText(self.document.rules[name])
            editor.setPlaceholderText(f"{title}을 입력하세요.")
            editor.setAccessibleName(title)
            editor.textChanged.connect(lambda name=name: self._rule_changed(name))
            panel_layout.addWidget(QLabel(title))
            panel_layout.addWidget(editor)
            self.rule_editors[name] = editor
            self.sections.addWidget(panel)
        self.sections.setChildrenCollapsible(False)

        self.course_selector = QComboBox()
        self.course_selector.setMinimumWidth(160)
        self.course_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.course_selector.addItems([c.name for c in self.document.courses])
        self.add_course_button = QPushButton("+")
        self.add_course_button.setToolTip("과목 추가")
        self.add_course_button.setAccessibleName("과목 추가")
        self.add_course_button.setFixedWidth(36)
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("단어장 · 과목"))
        toolbar.addWidget(self.course_selector, 1)
        toolbar.addWidget(self.add_course_button)

        self.table = QTableView()
        self.table.setMinimumHeight(60)
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 280)
        self.table.setColumnWidth(1, 340)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked
                                   | QAbstractItemView.EditTrigger.EditKeyPressed
                                   | QAbstractItemView.EditTrigger.AnyKeyPressed)

        self.add_term_button = QPushButton("단어 추가")
        self.remove_term_button = QPushButton("선택 단어 삭제")
        row_actions = QHBoxLayout()
        row_actions.addWidget(self.add_term_button)
        row_actions.addWidget(self.remove_term_button)
        row_actions.addStretch()
        self.status = QLabel()
        self.status.setWordWrap(True)
        terms_panel = QWidget()
        terms_layout = QVBoxLayout(terms_panel)
        terms_layout.setContentsMargins(0, 0, 0, 0)
        terms_layout.addLayout(toolbar)
        terms_layout.addWidget(self.table, 1)
        terms_layout.addLayout(row_actions)
        self.sections.addWidget(terms_panel)
        self.sections.setSizes([110, 110, 140, 280])
        layout = QVBoxLayout(self)
        layout.addLayout(file_toolbar)
        layout.addWidget(self.sections, 1)
        layout.addWidget(self.status)

        self.open_button.clicked.connect(self.open_file)
        self.course_selector.currentIndexChanged.connect(self._select_course)
        self.add_course_button.clicked.connect(self._add_course)
        self.save_button.clicked.connect(self.save)
        self.add_term_button.clicked.connect(self._add_term)
        self.remove_term_button.clicked.connect(self._remove_terms)
        self.model.edited.connect(self._show_dirty)
        save_action = QAction(self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save)
        self.addAction(save_action)
        open_action = QAction(self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        self.addAction(open_action)
        self._select_course(self.course_selector.currentIndex())
        self.status.setText("셀을 더블클릭하여 수정하세요. 과목이 없으면 + 버튼으로 추가하세요.")

    def _rule_changed(self, name):
        self.document.set_rule(name, self.rule_editors[name].toPlainText())
        self._show_dirty()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "텍스트북 열기", str(self.repository.path.parent) if self.repository else "",
            "텍스트북 (*.txt);;모든 파일 (*)",
        )
        if not path:
            return False
        # 새 파일 검증에 실패하면 현재 편집 내용을 그대로 유지합니다.
        repository = TextbookRepository(path)
        try:
            if not repository.path.is_file():
                raise ValueError("선택한 파일이 없습니다.")
            document = repository.load()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "텍스트북 열기 실패", str(exc))
            return False
        if not self.confirm_close():
            return False
        # 현재 파일을 저장한 직후 같은 파일을 다시 열 때 최신 내용을 읽습니다.
        try:
            document = repository.load()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "텍스트북 열기 실패", str(exc))
            return False
        self.repository = repository
        self.document = document
        self.model.beginResetModel()
        self.model.document = document
        self.model.course_index = -1
        self.model.endResetModel()
        self.course_selector.blockSignals(True)
        self.course_selector.clear()
        self.course_selector.addItems([c.name for c in document.courses])
        self.course_selector.blockSignals(False)
        self._select_course(self.course_selector.currentIndex())
        for name, editor in self.rule_editors.items():
            editor.blockSignals(True)
            editor.setPlainText(document.rules[name])
            editor.blockSignals(False)
        self.path_display.setText(str(repository.path))
        self.status.setText("텍스트북을 열었습니다.")
        return True

    def _select_course(self, index):
        self.model.select_course(index)
        self.add_term_button.setEnabled(index >= 0)
        self.remove_term_button.setEnabled(index >= 0)

    def _show_dirty(self):
        self.status.setText("저장하지 않은 변경 사항이 있습니다.")

    def _add_course(self):
        name, accepted = QInputDialog.getText(self, "과목 추가", "과목명")
        if not accepted:
            return
        try:
            index = self.document.add_course(name)
        except ValueError as exc:
            QMessageBox.warning(self, "과목 추가", str(exc))
            return
        self.course_selector.addItem(self.document.courses[index].name)
        self.course_selector.setCurrentIndex(index)
        self._show_dirty()

    def _add_term(self):
        self.model.append_row()
        index = self.model.index(self.model.rowCount() - 1, 0)
        self.table.setCurrentIndex(index)
        self.table.scrollTo(index)
        self.table.edit(index)

    def _remove_terms(self):
        self.model.remove_rows(index.row() for index in self.table.selectionModel().selectedRows())

    def save(self) -> bool:
        # Ctrl+S로 저장할 때도 현재 셀의 편집 값을 모델에 반영합니다.
        self.save_button.setFocus()
        try:
            self.document.to_textbook()
            repository = self.repository
            if repository is None:
                path, _ = QFileDialog.getSaveFileName(self, "텍스트북 저장", "textbook.txt", "텍스트북 (*.txt)")
                if not path:
                    return False
                repository = TextbookRepository(path)
                repository.load()
            repository.save(self.document)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return False
        self.repository = repository
        self.path_display.setText(str(repository.path))
        self.status.setText(f"저장 완료: {self.repository.path}")
        return True

    def confirm_close(self) -> bool:
        self.save_button.setFocus()
        if not self.document.dirty:
            return True
        answer = QMessageBox.question(
            self, "저장하지 않은 변경 사항", "변경 사항을 저장하시겠습니까?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard


class TextbookEditorWindow(QMainWindow):
    def __init__(self, repository: TextbookRepository | None = None, parent=None):
        super().__init__(parent)
        self.editor = TextbookEditor(repository, self)
        self.setCentralWidget(self.editor)
        self.setWindowTitle("텍스트북 편집")
        self.resize(860, 800)

    def closeEvent(self, event):
        if self.editor.confirm_close():
            event.accept()
        else:
            event.ignore()
