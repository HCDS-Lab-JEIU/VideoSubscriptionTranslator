"""과목 편집 데이터를 QTableView에 연결하는 모델."""

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, pyqtSignal

from .data import TextbookDocument


class TerminologyTableModel(QAbstractTableModel):
    edited = pyqtSignal()

    def __init__(self, document: TextbookDocument, parent=None):
        super().__init__(parent)
        self.document = document
        self.course_index = -1

    @property
    def rows(self):
        return self.document.courses[self.course_index].rows if self.course_index >= 0 else []

    def select_course(self, index):
        self.beginResetModel()
        self.course_index = index if 0 <= index < len(self.document.courses) else -1
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self.rows[index.row()][index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return ("한글명", "영어명")[section] if orientation == Qt.Orientation.Horizontal else section + 1
        return None

    def flags(self, index):
        flags = super().flags(index)
        return flags | Qt.ItemFlag.ItemIsEditable if index.isValid() else flags

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        value = str(value)
        if self.rows[index.row()][index.column()] != value:
            self.rows[index.row()][index.column()] = value
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
            self._mark_edited()
        return True

    def append_row(self):
        if self.course_index < 0:
            return
        row = len(self.rows)
        self.beginInsertRows(QModelIndex(), row, row)
        self.rows.append(["", ""])
        self.endInsertRows()
        self._mark_edited()

    def remove_rows(self, rows):
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.rows):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self.rows[row]
                self.endRemoveRows()
                self._mark_edited()

    def _mark_edited(self):
        self.document.dirty = True
        self.edited.emit()
