"""External SRT timeline and video overlay used only by the preview player."""

from bisect import bisect_right
from pathlib import Path
import re

from PyQt6.QtCore import QRectF, QSizeF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtMultimediaWidgets import QGraphicsVideoItem
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsTextItem, QGraphicsView


class SubtitleTrack:
    def __init__(self, cues=()):
        self.cues = sorted(cues, key=lambda cue: cue[0])
        self.starts = [cue[0] for cue in self.cues]
        self.max_ends = []
        end = 0
        for cue in self.cues:
            end = max(end, cue[1])
            self.max_ends.append(end)

    @classmethod
    def load(cls, path):
        stamp = r"(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})"
        timing = re.compile(rf"{stamp}\s+-->\s+{stamp}")
        cues = []
        content = Path(path).read_text(encoding="utf-8-sig").strip()
        for block in re.split(r"\n\s*\n", content) if content else []:
            lines = block.splitlines()
            if lines and lines[0].strip().isdigit():
                lines = lines[1:]
            match = timing.fullmatch(lines[0].strip()) if lines else None
            if match is None or len(lines) < 2:
                raise ValueError("미리보기 SRT의 시간 또는 자막 내용이 올바르지 않습니다.")
            values = list(map(int, match.groups()))
            start, end = (values[i] * 3600000 + values[i + 1] * 60000
                          + values[i + 2] * 1000 + values[i + 3] for i in (0, 4))
            if end <= start:
                raise ValueError("미리보기 SRT의 종료 시간은 시작 시간보다 늦어야 합니다.")
            cues.append((start, end, "\n".join(lines[1:])))
        return cls(cues)

    def text_at(self, milliseconds):
        # Prefix maxima keep overlap handling correct even after backward seeks.
        index = bisect_right(self.starts, milliseconds) - 1
        active = []
        while index >= 0 and self.max_ends[index] > milliseconds:
            start, end, text = self.cues[index]
            if start <= milliseconds < end:
                active.append(text)
            index -= 1
        return "\n".join(reversed(active))


class _CaptionItem(QGraphicsTextItem):
    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 175))
        painter.drawRoundedRect(self.boundingRect(), 4, 4)
        painter.restore()
        super().paint(painter, option, widget)


class SubtitleVideoView(QGraphicsView):
    """Video and caption share a scene, avoiding native video overlay stacking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("black"))
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setMinimumSize(160, 90)
        self.video_item = QGraphicsVideoItem()
        self.scene().addItem(self.video_item)
        self.caption = _CaptionItem()
        self.caption.setDefaultTextColor(QColor("white"))
        self.caption.setZValue(1)
        self.caption.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        option = self.caption.document().defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.document().setDefaultTextOption(option)
        self.scene().addItem(self.caption)
        self.caption.hide()
        self.video_item.nativeSizeChanged.connect(self._layout_items)

    def set_caption(self, text):
        if self.caption.toPlainText() != text:
            self.caption.setPlainText(text)
            self._layout_items()
        self.caption.setVisible(bool(text))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_items()

    def _layout_items(self, *_):
        size = QSizeF(self.viewport().size())
        self.setSceneRect(QRectF(0, 0, size.width(), size.height()))
        native = self.video_item.nativeSize()
        fitted = native.scaled(size, Qt.AspectRatioMode.KeepAspectRatio) if not native.isEmpty() else size
        x, y = (size.width() - fitted.width()) / 2, (size.height() - fitted.height()) / 2
        self.video_item.setSize(fitted)
        self.video_item.setPos(x, y)
        font = QFont("Arial")
        font.setPixelSize(max(12, min(32, round(fitted.height() * 0.045))))
        self.caption.setFont(font)
        self.caption.setTextWidth(max(1, fitted.width() * 0.9))
        self.caption.setPos(x + fitted.width() * 0.05,
                            y + max(0, fitted.height() - self.caption.boundingRect().height()
                                    - max(5, fitted.height() * 0.04)))
