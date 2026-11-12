"""영상 재생과 재생 컨트롤을 제공하는 위젯."""

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from subtitle_app.ui.player.audio_wave_visualizer import AudioWaveVisualizer
from subtitle_app.ui.player.subtitle_preview import SubtitleTrack, SubtitleVideoView


class QVideoPlayer(QWidget):
    error_occurred = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_path: Path | None = None
        self.subtitle_track = SubtitleTrack()

        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.video_widget = SubtitleVideoView(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget.video_item)
        self.audio_output.setVolume(0.8)

        self.play_button = QPushButton("▶")
        self.play_button.setObjectName("playButton")
        self.play_button.setToolTip("Play")
        self.play_button.setEnabled(False)
        self.play_button.setFixedSize(38, 30)
        self.play_button.clicked.connect(self.toggle_playback)

        self.wave_visualizer = AudioWaveVisualizer(self)
        self.wave_visualizer.setFixedHeight(48)
        self.wave_visualizer.seek_requested.connect(self.media_player.setPosition)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setObjectName("timeLabel")
        self.time_label.setFixedWidth(110)
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        self.volume_label = QLabel("Volume")
        self.volume_label.setObjectName("volumeLabel")
        self.volume_label.setFixedWidth(50)
        self.volume_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.valueChanged.connect(
            lambda value: self.audio_output.setVolume(value / 100)
        )

        controls_widget = QWidget(self)
        controls_widget.setObjectName("playerControls")
        controls_widget.setFixedHeight(40)
        controls = QHBoxLayout(controls_widget)
        controls.setContentsMargins(0, 5, 0, 5)
        controls.setSpacing(8)
        controls.addWidget(self.play_button)
        controls.addWidget(self.time_label)
        controls.addStretch(1)
        self.subtitle_checkbox = QCheckBox("미리보기 자막")
        self.subtitle_checkbox.setChecked(True)
        self.subtitle_checkbox.setEnabled(False)
        self.subtitle_checkbox.setToolTip("번역된 SRT가 생성되면 자동으로 표시됩니다.")
        self.subtitle_checkbox.toggled.connect(self._update_subtitle)
        controls.addWidget(self.subtitle_checkbox)
        controls.addWidget(self.volume_label)
        controls.addWidget(self.volume_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(self.video_widget, 1)
        layout.addWidget(self.wave_visualizer)
        layout.addWidget(controls_widget)

        self.media_player.positionChanged.connect(self._update_position)
        self.media_player.durationChanged.connect(self._update_duration)
        self.media_player.playbackStateChanged.connect(self._update_play_button)
        self.media_player.errorOccurred.connect(self._handle_error)

    def load_video(self, file_path: str | Path) -> None:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Video file not found: {path}")

        self.current_path = path
        self.clear_subtitles()
        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(str(path)))
        self.wave_visualizer.load_media(path)
        self.play_button.setEnabled(True)
        self.media_player.play()

    def toggle_playback(self) -> None:
        if not self.current_path:
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _update_position(self, position: int) -> None:
        self.wave_visualizer.set_position(position)
        self._update_time_label(position, self.media_player.duration())
        self._update_subtitle(position=position)

    def clear_subtitles(self):
        self.subtitle_track = SubtitleTrack()
        self.video_widget.set_caption("")
        self.subtitle_checkbox.setEnabled(False)
        self.subtitle_checkbox.setToolTip("번역된 SRT가 생성되면 자동으로 표시됩니다.")

    def load_subtitles(self, video_path, srt_path):
        if self.current_path != Path(video_path).resolve():
            return False
        self.subtitle_track = SubtitleTrack.load(srt_path)
        self.subtitle_checkbox.setEnabled(bool(self.subtitle_track.cues))
        self.subtitle_checkbox.setToolTip(f"미리보기 전용 자막: {srt_path}")
        self._update_subtitle()
        return True

    def _update_subtitle(self, _checked=None, *, position=None):
        if position is None:
            position = self.media_player.position()
        text = self.subtitle_track.text_at(position) if self.subtitle_checkbox.isChecked() else ""
        self.video_widget.set_caption(text)

    def _update_duration(self, duration: int) -> None:
        self.wave_visualizer.set_duration(duration)
        self._update_time_label(self.media_player.position(), duration)

    def _update_play_button(self, state: QMediaPlayer.PlaybackState) -> None:
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("❚❚" if is_playing else "▶")
        self.play_button.setToolTip("Pause" if is_playing else "Play")

    def _handle_error(self, _error: QMediaPlayer.Error) -> None:
        message = self.media_player.errorString() or "Unable to play this video."
        self.play_button.setEnabled(False)
        self.error_occurred.emit(message)

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        total_seconds = max(0, milliseconds) // 1000
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"

