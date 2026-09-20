"""오디오 파형과 현재 재생 위치를 표시하는 탐색 위젯."""

from array import array
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PyQt6.QtWidgets import QWidget


def _ffmpeg_executable() -> str:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("FFmpeg executable not found") from exc


def _downsample(samples: array, maximum_points: int) -> list[float]:
    if not samples:
        return []
    count = min(len(samples), maximum_points)
    waveform = []
    for index in range(count):
        start = index * len(samples) // count
        end = max(start + 1, (index + 1) * len(samples) // count)
        peak = max(abs(sample) for sample in samples[start:end])
        waveform.append(min(1.0, peak / 32768))
    return waveform


class _WaveformWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, file_path: Path, maximum_points: int) -> None:
        super().__init__()
        self.file_path = file_path
        self.maximum_points = maximum_points
        self._cancelled = False
        self._process: subprocess.Popen | None = None

    @pyqtSlot()
    def run(self) -> None:
        try:
            if self._cancelled:
                return
            command = [
                _ffmpeg_executable(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                str(self.file_path),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "1000",
                "-f",
                "s16le",
                "-",
            ]
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            audio_bytes, _ = self._process.communicate()
            if self._cancelled:
                return
            if self._process.returncode != 0 or not audio_bytes:
                self.failed.emit("No audio waveform available")
                return

            samples = array("h")
            samples.frombytes(audio_bytes[:len(audio_bytes) // 2 * 2])
            if sys.byteorder != "little":
                samples.byteswap()
            self.completed.emit(_downsample(samples, self.maximum_points))
        except (OSError, RuntimeError) as exc:
            if not self._cancelled:
                self.failed.emit(str(exc))
        finally:
            self._process = None
            self.finished.emit()

    def cancel(self) -> None:
        self._cancelled = True
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()


class AudioWaveVisualizer(QWidget):
    seek_requested = pyqtSignal(int)

    MAX_WAVEFORM_POINTS = 1600

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("audioWaveVisualizer")
        self.setMinimumHeight(90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._waveform: list[float] = []
        self._position = 0
        self._duration = 0
        self._message = "Open a video to display its audio waveform"
        self._thread: QThread | None = None
        self._worker: _WaveformWorker | None = None

    def load_media(self, file_path: str | Path) -> None:
        self._stop_loading()
        self._waveform = []
        self._position = 0
        self._message = "Loading waveform..."
        self.update()

        path = Path(file_path).expanduser().resolve()
        thread = QThread(self)
        worker = _WaveformWorker(path, self.MAX_WAVEFORM_POINTS)
        worker.moveToThread(thread)
        self._thread = thread
        self._worker = worker

        thread.started.connect(worker.run)
        worker.completed.connect(self.set_waveform)
        worker.failed.connect(self._show_loading_error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda: self._clear_loader(thread))
        thread.start()

    def set_position(self, position: int) -> None:
        self._position = min(max(0, position), self._duration)
        self.update()

    def set_duration(self, duration: int) -> None:
        self._duration = max(0, duration)
        self._position = min(self._position, self._duration)
        self.update()

    def set_waveform(self, waveform: list[float]) -> None:
        self._waveform = [min(1.0, max(0.0, value)) for value in waveform]
        self._message = "" if self._waveform else "No audio waveform available"
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d1117"))

        if not self._waveform:
            painter.setPen(QColor("#8b949e"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        self._draw_waveform(painter, QColor("#484f58"))
        progress_x = self._progress_x()

        painter.save()
        painter.setClipRect(0, 0, progress_x, self.height())
        self._draw_waveform(painter, QColor("#58a6ff"))
        painter.restore()

        painter.setPen(QPen(QColor("#f0f6fc"), 2))
        painter.drawLine(progress_x, 5, progress_x, self.height() - 5)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._request_seek(event.position().x())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._request_seek(event.position().x())
        super().mouseMoveEvent(event)

    def closeEvent(self, event) -> None:
        self._stop_loading()
        super().closeEvent(event)

    def _draw_waveform(self, painter: QPainter, color: QColor) -> None:
        width = max(1, self.width())
        center = self.height() / 2
        maximum_height = max(1.0, self.height() / 2 - 8)
        painter.setPen(QPen(color, 1))
        for x in range(width):
            index = min(len(self._waveform) - 1, x * len(self._waveform) // width)
            amplitude = max(0.02, self._waveform[index]) * maximum_height
            painter.drawLine(x, int(center - amplitude), x, int(center + amplitude))

    def _request_seek(self, x_position: float) -> None:
        if self._duration <= 0 or self.width() <= 0:
            return
        ratio = min(1.0, max(0.0, x_position / self.width()))
        position = round(self._duration * ratio)
        self.set_position(position)
        self.seek_requested.emit(position)

    def _progress_x(self) -> int:
        if self._duration <= 0:
            return 0
        return round(self.width() * self._position / self._duration)

    def _show_loading_error(self, message: str) -> None:
        self._waveform = []
        self._message = message
        self.update()

    def _clear_loader(self, thread: QThread) -> None:
        if thread is self._thread:
            self._thread = None
            self._worker = None

    def _stop_loading(self) -> None:
        thread = self._thread
        worker = self._worker
        self._thread = None
        self._worker = None
        if thread is None:
            return
        if worker is not None:
            worker.cancel()
        thread.quit()
        thread.wait(5000)
